"""Temporary Windows-side mTLS edge for the supervised local dev session."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, socket, subprocess, sys, threading, time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))

from avatar_state import AvatarStateEmitter
from godot_avatar_receiver import AvatarStateForwarder
from sentientos.gaming_companion_avatar_output import (
    WindowsEdgeAvatarCommandDispatchOwner, WindowsGodotAvatarStateQueue,
)
from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
from sentientos.gaming_companion_tls_transport import (
    MIN_TLS_VERSION, CompanionBridgeMutualTLSRuntime,
)

def _readline(stream, target):
    for line in stream:
        target.put(line.rstrip())

def main():
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
    runtime=CompanionBridgeMutualTLSRuntime(
        bind_address=cfg["bind"],port=0,tls_context=server,
        expected_peer_certificate_sha256=cfg["peer_pin"],
        receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core-dev":source_key},
            expected_generations={"wsl-core-dev":"wsl-avatar-dev-1"}),
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
    dispatcher=WindowsEdgeAvatarCommandDispatchOwner(
        runtime=runtime,receipt_verifier=verify_receipt,renderer_sink=render)
    godot=None;forwarder=None
    try:
        port=runtime.start();dispatcher.start()
        env={key:value for key,value in os.environ.items()
             if not any(marker in key.upper() for marker in
                ("API_KEY","TOKEN","SECRET","PASSWORD","CREDENTIAL","AUTH","PRIVATE_KEY","BEARER"))}
        profile=root/"profile"
        for name in ("APPDATA","LOCALAPPDATA","TEMP","TMP"):
            target=profile/name;target.mkdir(parents=True,exist_ok=True);env[name]=str(target)
        env["HOME"]=str(profile)
        env["SENTIENTOS_RENDERER_GENERATION_ID"]="godot-dev-"+str(os.getpid())
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
        godot=subprocess.Popen([executable,"--path",project],env=env,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        forwarder=AvatarStateForwarder(state_path,host="127.0.0.1",port=18188,poll_interval=0.05)
        forwarder.start()
        time.sleep(1.0)
        if godot.poll() is not None:
            raise RuntimeError("godot_scene_exited_on_startup")
        print("READY "+str(port),flush=True)
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
        if forwarder: forwarder.stop()
        if "report_stop" in locals():
            report_stop.set()
            report_socket.close()
            report_thread.join(timeout=1.0)
        dispatcher.close()
        runtime.close()
        if godot and godot.poll() is None:
            godot.terminate()
            try: godot.wait(timeout=8)
            except subprocess.TimeoutExpired:
                godot.kill();godot.wait(timeout=3)
    return 0

if __name__=="__main__": raise SystemExit(main())
