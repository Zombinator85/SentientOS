"""Temporary Windows-side mTLS edge for the supervised local dev session."""
from __future__ import annotations
import base64, dataclasses, errno, hashlib, hmac, json, os, socket, subprocess, sys, threading, time
from pathlib import Path

ROOT = (Path(sys.argv[1]).resolve() if __name__ == "__main__"
       else Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))

from terminate_owned_process_tree import terminate_owned_process_tree
from avatar_state import AvatarStateEmitter
from godot_avatar_receiver import AvatarStateForwarder, available_loopback_udp_port
from sentientos.gaming_companion_avatar_output import (
    WindowsEdgeAvatarCommandDispatchOwner, WindowsGodotAvatarStateQueue,
)
from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
from sentientos.gaming_companion_bridge_runtime import CompanionBridgeLoopbackClient
from sentientos.foreground_game_bridge import (
    WindowsForegroundBridgePublisher, WindowsForegroundObservationPump,
)
from sentientos.foreground_game_detection import ForegroundGameDetector
from sentientos.gaming_companion_tls_transport import (
    MIN_TLS_VERSION, CompanionBridgeMutualTLSRuntime,
)

def _readline(stream, target):
    for line in stream:
        target.put(line.rstrip())

def _godot_command(executable, project, *, headless, companion_api_port=5000, opaque_observation_window=False):
    if type(companion_api_port) is not int or not 1 <= companion_api_port <= 65535:
        raise ValueError("companion_api_port_out_of_range")
    command=[executable]
    if headless:
        command.append("--headless")
    command.extend(["--path",project])
    user_args=["--sentientos-api-port="+str(companion_api_port)]
    if opaque_observation_window:
        user_args.append("--sentientos-opaque-observation-window")
    command.extend(["--", *user_args])
    return command

def _udp_port_is_bound(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE or getattr(exc, "winerror", None) == 10048:
                return True
            raise
        return False

def _wait_for_udp_listener(port, process, *, timeout_seconds=5.0):
    deadline=time.monotonic()+timeout_seconds
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise RuntimeError("godot_scene_exited_on_startup")
        if _udp_port_is_bound(port):
            return
        time.sleep(0.05)
    raise RuntimeError("godot_avatar_listener_startup_timeout")

def main():
    print("EDGE_STARTUP phase=worker_started",flush=True)
    cfg=json.loads(sys.stdin.readline())
    ca,cert,key=(Path(cfg[name]) for name in ("ca","cert","key"))
    server=__import__("ssl").SSLContext(__import__("ssl").PROTOCOL_TLS_SERVER)
    server.minimum_version=MIN_TLS_VERSION
    server.verify_mode=__import__("ssl").CERT_REQUIRED
    server.load_verify_locations(cafile=str(ca))
    server.load_cert_chain(str(cert),str(key))
    root=Path(cfg["runtime_root"]);root.mkdir(parents=True,exist_ok=True)
    state_path=root/"avatar_state.json"
    state_queue=WindowsGodotAvatarStateQueue(state_emitter=AvatarStateEmitter(state_path))
    source_key=base64.b64decode(cfg["avatar_key"])
    ack_key=base64.b64decode(cfg["avatar_ack"])
    receipt_key=base64.b64decode(cfg["receipt_key"])
    screen_cfg=cfg.get("screen_observation")
    trusted_sources={"wsl-core-dev":source_key}
    trusted_generations={"wsl-core-dev":"wsl-avatar-dev-1"}
    if isinstance(screen_cfg,dict):
        request_key=base64.b64decode(screen_cfg["request_key"])
        trusted_sources[screen_cfg["request_source_id"]]=request_key
        trusted_generations[screen_cfg["request_source_id"]]=screen_cfg["request_generation_id"]
        avatar_cfg=screen_cfg.get("avatar_consequence")
        if isinstance(avatar_cfg,dict):
            avatar_request_key=base64.b64decode(avatar_cfg["request_key"])
            trusted_sources[avatar_cfg["request_source_id"]]=avatar_request_key
            trusted_generations[avatar_cfg["request_source_id"]]=avatar_cfg["request_generation_id"]
    runtime=CompanionBridgeMutualTLSRuntime(
        bind_address=cfg["bind"],port=0,tls_context=server,
        expected_peer_certificate_sha256=cfg["peer_pin"],
        receiver=CompanionBridgeReceiver(
            source_keys=trusted_sources,expected_generations=trusted_generations),
        acknowledgment_source_id="windows-edge-dev",
        acknowledgment_generation_id="windows-avatar-ack-dev-1",
        acknowledgment_key=ack_key,socket_timeout_seconds=2.0)
    def verify_receipt(receipt_id,semantic_digest,_message):
        expected=hmac.new(receipt_key,receipt_id.encode("utf-8"),hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected,semantic_digest)
    def render(payload,message):
        accepted=state_queue.enqueue(payload,message)
        if accepted:
            print("AVATAR_ACCEPTED "+json.dumps({
                "session_id":message.session_id,"turn_id":payload.get("turn_id"),
                "output_digest":payload.get("output_digest")}),flush=True)
        return accepted
    screen_dispatch_state={}
    def capture_screen_request(message):
        if (not isinstance(screen_cfg,dict)
                or message.source_id!=screen_cfg.get("request_source_id")
                or message.generation_id!=screen_cfg.get("request_generation_id")
                or message.kind!="screen_capture_request"
                or message.admission is not None):
            print("SCREEN_CAPTURE_DISPATCH result=rejected reason=request_contract",flush=True)
            return False
        capture=screen_dispatch_state.get("capture")
        if not callable(capture):
            print("SCREEN_CAPTURE_DISPATCH result=rejected reason=owner_unavailable",flush=True)
            return False
        request_payload=message.payload
        question=request_payload.get("question")
        if (set(request_payload) not in ({"capture_request_id"},
                                         {"capture_request_id","question"})
                or not isinstance(request_payload.get("capture_request_id"),str)
                or (question is not None and
                    (not isinstance(question,str) or not question.strip()
                     or len(question)>2048))):
            print("SCREEN_CAPTURE_DISPATCH result=rejected reason=request_payload",flush=True)
            return False
        try:
            accepted=capture(request_payload["capture_request_id"],question=question)
        except Exception as exc:
            safe_error_types={"ScreenObservationBridgeError", "ScreenCaptureError"}
            reason=(str(exc.args[0]) if type(exc).__name__ in safe_error_types
                    and exc.args else getattr(exc,"code",type(exc).__name__))
            if not isinstance(reason,str) or not reason.isascii() or not reason.replace("_", "").isalnum():
                reason=type(exc).__name__
            phase=getattr(exc,"failure_phase",None)
            phase=(phase if isinstance(phase,str) and phase.isascii()
                   and phase.replace("_", "").isalnum() else "unknown")
            delivery=getattr(exc,"delivery_state",None)
            delivery=(delivery if isinstance(delivery,str) and delivery.isascii()
                      and delivery.replace("_", "").isalnum() else "unknown")
            failure_type=getattr(exc,"failure_type",None)
            failure_type=(failure_type if isinstance(failure_type,str)
                and failure_type.isascii() and failure_type.replace("_", "").isalnum()
                else "unknown")
            failure_reason=getattr(exc,"failure_reason",None)
            failure_reason=(failure_reason if isinstance(failure_reason,str)
                and failure_reason.isascii()
                and failure_reason.replace("_", "").isalnum()
                else "unknown")
            print("SCREEN_CAPTURE_DISPATCH result=error failure_code=" +
                reason[:96]+" phase="+phase[:48]+" delivery="+delivery[:32]+
                " cause="+failure_type[:48]+" cause_code="+failure_reason[:96],flush=True)
            return False
        print("SCREEN_CAPTURE_DISPATCH result=" +
            ("published" if accepted else "no_observation"),flush=True)
        return accepted
    def capture_avatar_consequence_request(message):
        if (not isinstance(screen_cfg,dict)
                or not isinstance(screen_cfg.get("avatar_consequence"),dict)
                or message.source_id!=screen_cfg["avatar_consequence"].get("request_source_id")
                or message.generation_id!=screen_cfg["avatar_consequence"].get("request_generation_id")
                or message.kind!="avatar_consequence_request"
                or message.admission is not None):
            print("AVATAR_MEASUREMENT_DISPATCH result=rejected reason=request_contract",flush=True)
            return False
        handler=screen_dispatch_state.get("avatar_consequence")
        if not callable(handler):
            print("AVATAR_MEASUREMENT_DISPATCH result=rejected reason=owner_unavailable",flush=True)
            return False
        try:
            accepted=handler(message)
        except Exception as exc:
            reason=(str(exc.args[0]) if exc.args and isinstance(exc.args[0],str)
                    and exc.args[0].isascii() else type(exc).__name__)
            reason=reason if reason.replace("_", "").isalnum() else type(exc).__name__
            print("AVATAR_MEASUREMENT_DISPATCH result=error code="+reason[:96],flush=True)
            return False
        print("AVATAR_MEASUREMENT_DISPATCH result="+("published" if accepted else "rejected"),flush=True)
        return bool(accepted)
    def report_dispatch_outcome(outcome):
        if outcome.get("kind") == "avatar_command":
            print("AVATAR_DISPATCH "+json.dumps(
                outcome,separators=(",",":"),sort_keys=True),flush=True)
    dispatcher=WindowsEdgeAvatarCommandDispatchOwner(
        runtime=runtime,receipt_verifier=verify_receipt,renderer_sink=render,
        additional_message_handlers=(
            ({"screen_capture_request":capture_screen_request,
              **({"avatar_consequence_request":capture_avatar_consequence_request}
                 if isinstance(screen_cfg.get("avatar_consequence"),dict) else {})})
            if isinstance(screen_cfg,dict) else None),
        dispatch_outcome_observer=report_dispatch_outcome)
    godot=None;forwarder=None;foreground_pump=None
    try:
        print("EDGE_STARTUP phase=bridge_runtime",flush=True)
        port=runtime.start()
        observer=cfg.get("foreground_observation")
        if isinstance(observer,dict):
            source_key=base64.b64decode(observer["source_key"])
            observer_ack_key=base64.b64decode(observer["ack_key"])
            acknowledgment_receiver=CompanionBridgeReceiver(
                source_keys={observer["ack_source_id"]:observer_ack_key},
                expected_generations={observer["ack_source_id"]:
                    observer["ack_generation_id"]})
            observation_client=CompanionBridgeLoopbackClient(
                port=int(observer["port"]),
                acknowledgment_receiver=acknowledgment_receiver,
                timeout_seconds=1.5)
            publisher=WindowsForegroundBridgePublisher(
                detector=ForegroundGameDetector(),client=observation_client,
                source_id=observer["source_id"],session_id="windows-game-observer-dev",
                generation_id=observer["source_generation_id"],source_key=source_key)
            foreground_pump=WindowsForegroundObservationPump(
                publisher=publisher,process_names=observer["process_names"],
                interval_seconds=1.0)
            foreground_pump.start()
        if isinstance(screen_cfg,dict):
            from sentientos.screen_observation_bridge import (
                WindowsScreenObservationBridgePublisher,
            )
            from sentientos.perception.game_screen_capture import (
                GameScreenCaptureConsent, build_windows_game_screen_ocr,
            )
            from sentientos.perception.screen_ocr import ScreenConfig
            if (not isinstance(screen_cfg.get("process_names"),list)
                    or not screen_cfg["process_names"]
                    or not isinstance(screen_cfg.get("consent_id"),str)
                    or not isinstance(screen_cfg.get("consent_expires_at"),str)):
                raise RuntimeError("screen_observation_configuration_invalid")
            tesseract_executable=screen_cfg.get("tesseract_executable","tesseract")
            if (not isinstance(tesseract_executable,str) or not tesseract_executable
                    or len(tesseract_executable)>1024 or "\0" in tesseract_executable):
                raise RuntimeError("screen_observation_ocr_executable_invalid")
            consent=GameScreenCaptureConsent(
                consent_id=screen_cfg["consent_id"],
                allowed_process_names=tuple(screen_cfg["process_names"]),
                expires_at=screen_cfg["consent_expires_at"])
            vision_model=screen_cfg.get("vision_model")
            if vision_model is not None and not isinstance(vision_model,str):
                raise RuntimeError("screen_observation_vision_model_invalid")
            screen_owner=build_windows_game_screen_ocr(
                config=ScreenConfig(enable=True,interval_s=0.0,ocr_backend="tesseract",
                    refresh_unchanged_observation=True,
                    visual_change_threshold=0.035),
                consent_provider=lambda: consent,
                tesseract_executable=tesseract_executable,
                vision_model=vision_model,
                foreground_wait_seconds=float(
                    screen_cfg.get("foreground_wait_seconds", 0.0)))
            screen_ack_key=base64.b64decode(screen_cfg["ack_key"])
            screen_source_key=base64.b64decode(screen_cfg["source_key"])
            screen_ack_receiver=CompanionBridgeReceiver(
                source_keys={screen_cfg["ack_source_id"]:screen_ack_key},
                expected_generations={screen_cfg["ack_source_id"]:
                    screen_cfg["ack_generation_id"]})
            screen_client=CompanionBridgeLoopbackClient(
                port=int(screen_cfg["port"]),
                acknowledgment_receiver=screen_ack_receiver,timeout_seconds=5.0)
            screen_publisher=WindowsScreenObservationBridgePublisher(
                observe=screen_owner.snapshot,observe_question=screen_owner.snapshot,
                client=screen_client,
                source_id=screen_cfg["source_id"],session_id="windows-game-screen-dev",
                generation_id=screen_cfg["source_generation_id"],
                source_key=screen_source_key)
            screen_dispatch_state["capture"] = screen_publisher.publish_request
            avatar_cfg=screen_cfg.get("avatar_consequence")
            if isinstance(avatar_cfg,dict):
                if vision_model is None:
                    raise RuntimeError("avatar_consequence_vision_model_required")
                from sentientos.avatar_consequence_bridge import (
                    AvatarConsequenceCaptureRequestHandler,
                )
                from sentientos.perception.game_screen_capture import (
                    build_windows_game_screen_avatar_observer,
                )
                avatar_observer=build_windows_game_screen_avatar_observer(
                    consent_provider=lambda: consent, vision_model=vision_model,
                    foreground_wait_seconds=float(
                        screen_cfg.get("foreground_wait_seconds", 0.0)))
                consequence_ack_key=base64.b64decode(avatar_cfg["ack_key"])
                consequence_ack_receiver=CompanionBridgeReceiver(
                    source_keys={avatar_cfg["ack_source_id"]:consequence_ack_key},
                    expected_generations={avatar_cfg["ack_source_id"]:
                        avatar_cfg["ack_generation_id"]})
                consequence_client=CompanionBridgeLoopbackClient(
                    port=int(avatar_cfg["port"]),
                    acknowledgment_receiver=consequence_ack_receiver,timeout_seconds=5.0)
                screen_dispatch_state["avatar_consequence"]=(
                    AvatarConsequenceCaptureRequestHandler(
                        observe=avatar_observer, client=consequence_client,
                        request_source_id=avatar_cfg["request_source_id"],
                        request_generation_id=avatar_cfg["request_generation_id"],
                        observer_id=avatar_cfg["source_id"],
                        observer_generation_id=avatar_cfg["source_generation_id"],
                        session_id="windows-avatar-consequence-dev",
                        observer_source_key=base64.b64decode(
                            avatar_cfg["source_key"])))
                print("AVATAR_MEASUREMENT_READY policy=per-request raw_frame_retained=false",flush=True)
            print("SCREEN_CAPTURE_READY policy=per-message raw_frame_retained=false",flush=True)
        dispatcher.start()
        env={key:value for key,value in os.environ.items()
             if not any(marker in key.upper() for marker in
                ("API_KEY","TOKEN","SECRET","PASSWORD","CREDENTIAL","AUTH","PRIVATE_KEY","BEARER"))}
        profile=root/"profile"
        # Persist user-facing overlay preferences across disposable dev runner profiles.
        local_app_data=Path(os.environ.get("LOCALAPPDATA", str(profile/"LOCALAPPDATA")))
        persistent_config=local_app_data/"SentientOS"/"companion_overlay.cfg"
        persistent_config.parent.mkdir(parents=True,exist_ok=True)
        env["SENTIENTOS_OVERLAY_CONFIG_PATH"]=str(persistent_config)
        for name in ("APPDATA","LOCALAPPDATA","TEMP","TMP"):
            target=profile/name;target.mkdir(parents=True,exist_ok=True);env[name]=str(target)
        env["HOME"]=str(profile)
        env["SENTIENTOS_RENDERER_GENERATION_ID"]="godot-dev-"+str(os.getpid())
        avatar_listen_port=available_loopback_udp_port()
        env["SENTIENTOS_GODOT_LISTEN_PORT"]=str(avatar_listen_port)
        report_socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        report_socket.bind(("127.0.0.1",0));report_socket.settimeout(0.2)
        env["SENTIENTOS_RENDERER_REPORT_RELAY_PORT"]=str(report_socket.getsockname()[1])
        report_stop=threading.Event()
        def report_receiver():
            while not report_stop.is_set():
                try: raw,_address=report_socket.recvfrom(60001)
                except socket.timeout: continue
                except OSError: return
                if len(raw)>60000: continue
                try: report=json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError,json.JSONDecodeError): continue
                if isinstance(report,dict) and report.get("schema_version")=="sentientos.avatar_renderer_report:v2":
                    print("RENDERER_REPORT "+json.dumps(report,separators=(",",":")),flush=True)
        report_thread=threading.Thread(target=report_receiver,name="godot-renderer-report",daemon=True)
        report_thread.start()
        env["XDG_CACHE_HOME"]=str(profile/"cache")
        env["XDG_CONFIG_HOME"]=str(profile/"config")
        env["XDG_DATA_HOME"]=str(profile/"data")
        for name in ("XDG_CACHE_HOME","XDG_CONFIG_HOME","XDG_DATA_HOME"):
            Path(env[name]).mkdir(parents=True,exist_ok=True)
        executable=cfg["godot_executable"];project=cfg["godot_project"]
        print("EDGE_STARTUP phase=godot_process_create",flush=True)
        godot=subprocess.Popen(_godot_command(
            executable,project,headless=cfg.get("godot_headless") is True,
            companion_api_port=cfg.get("companion_api_port", 5000),
            opaque_observation_window=(
                cfg.get("godot_opaque_observation_window") is True)),env=env,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        print("EDGE_STARTUP phase=godot_process_started pid="+str(godot.pid)
            +" avatar_listen_port="+str(avatar_listen_port),flush=True)
        _wait_for_udp_listener(avatar_listen_port,godot)
        print("AVATAR_LISTENER_READY port="+str(avatar_listen_port),flush=True)
        forwarder=AvatarStateForwarder(state_path,host="127.0.0.1",
            port=avatar_listen_port,poll_interval=0.05)
        forwarder.start()
        time.sleep(1.0)
        if godot.poll() is not None:
            raise RuntimeError("godot_scene_exited_on_startup")
        print("READY "+str(port)+" "+str(godot.pid),flush=True)
        status_stop=threading.Event()
        status_thread=None
        if foreground_pump is not None:
            def report_foreground_status():
                while not status_stop.wait(15.0):
                    print("FOREGROUND_PUMP "+json.dumps(
                        dataclasses.asdict(foreground_pump.status()),
                        separators=(",",":")),flush=True)
            status_thread=threading.Thread(target=report_foreground_status,
                name="foreground-publisher-status",daemon=True)
            status_thread.start()
        while True:
            line=sys.stdin.readline()
            if not line or line.strip()=="STOP": break
            if line.strip()=="STATUS":
                print("STATUS "+json.dumps({
                    "dispatch":dispatcher.status().__dict__ if hasattr(dispatcher.status(),"__dict__") else {
                        "accepted":dispatcher.status().accepted,
                        "rejected":dispatcher.status().rejected},
                    "state_file":str(state_path),"state_file_exists":state_path.is_file(),
                    "godot_running":godot.poll() is None}),flush=True)
    finally:
        if "status_stop" in locals():
            status_stop.set()
            if status_thread is not None:
                status_thread.join(timeout=1.0)
        if forwarder: forwarder.stop()
        if "report_stop" in locals():
            report_stop.set()
            report_socket.close()
            report_thread.join(timeout=1.0)
        try:
            if foreground_pump is not None:
                foreground_pump.close()
        finally:
            try:
                dispatcher.close()
            finally:
                try:
                    runtime.close()
                finally:
                    if godot is not None:
                        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
                        terminate_owned_process_tree(
                            godot, taskkill_executable=system_root / "System32" / "taskkill.exe")
    return 0

if __name__=="__main__": raise SystemExit(main())
