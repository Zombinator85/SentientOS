"""Opt-in WSL/Windows mTLS smoke using disposable test identities only."""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import platform
import queue
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from avatar_state import AvatarStateEmitter
from godot_avatar_receiver import AvatarStateForwarder
from sentientos.avatar_renderer_report_ingress import (
    RendererReportCaptureOwner,
    RendererReportEvidenceStore,
)
from sentientos.avatar_renderer_report_relay import WindowsRendererReportRelay
from sentientos.gaming_companion_avatar_output import (
    BridgeChatAvatarOutputEmitter,
    MutualTLSAvatarCommandSender,
    WindowsEdgeAvatarCommandDispatchOwner,
    WindowsGodotAvatarStateQueue,
)
from sentientos.game_performance_bridge import (
    GamePerformanceBridgeDetector,
    WindowsGamePerformanceBridgePublisher,
)
from sentientos.gaming_companion_bridge import (
    CompanionBridgeReceiver,
    VerifiedBridgeMessage,
)
from sentientos.gaming_companion_tls_transport import (
    MIN_TLS_VERSION,
    CompanionBridgeMutualTLSClient,
    CompanionBridgeMutualTLSRuntime,
)
from sentientos.windows_game_performance import WindowsGamePerformanceObserver


def _private_ip(value: str) -> str:
    address = ipaddress.ip_address(value)
    if (not address.is_private or address.is_loopback or address.is_link_local
            or address.is_unspecified or address.is_multicast or address.is_global):
        raise ValueError("private_host_address_unavailable")
    return str(address)


def _addresses() -> tuple[str, str]:
    route = subprocess.run(["ip", "-4", "route", "get", "192.0.2.1"],
        check=True, capture_output=True, text=True, timeout=3).stdout.split()
    default = subprocess.run(["ip", "-4", "route", "show", "default"],
        check=True, capture_output=True, text=True, timeout=3).stdout.split()
    try:
        return (_private_ip(route[route.index("src") + 1]),
                _private_ip(default[default.index("via") + 1]))
    except (IndexError, ValueError) as exc:
        raise ValueError("private_wsl_windows_route_unavailable") from exc


def _write(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


TEMPORARY_TEST_IDENTITY_LIFETIME = timedelta(hours=12)


def _test_identities(directory: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
        "SentientOS temporary smoke CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + TEMPORARY_TEST_IDENTITY_LIFETIME)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256()))
    ca_path = directory / "ca.pem"
    _write(ca_path, ca.public_bytes(serialization.Encoding.PEM))
    result: dict[str, Any] = {"ca": ca_path}
    for role, hostname in (("wsl", "wsl-core.test"),
                           ("windows", "windows-edge.test")):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
            .issuer_name(ca_name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + TEMPORARY_TEST_IDENTITY_LIFETIME)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
        cert_path, key_path = directory / f"{role}.pem", directory / f"{role}-key.pem"
        _write(cert_path, cert.public_bytes(serialization.Encoding.PEM))
        _write(key_path, key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        result[role] = {"cert": cert_path, "key": key_path,
            "pin": hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()}
    return result


def _contexts(ca: Path, cert: Path, key: Path) -> tuple[ssl.SSLContext, ssl.SSLContext]:
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version = MIN_TLS_VERSION
    server.verify_mode = ssl.CERT_REQUIRED
    server.load_verify_locations(cafile=str(ca))
    server.load_cert_chain(str(cert), str(key))
    client = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
    client.minimum_version = MIN_TLS_VERSION
    client.load_cert_chain(str(cert), str(key))
    return server, client


def _win_path(path: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(path)], check=True,
        capture_output=True, text=True, timeout=3).stdout.strip()


def _win_temp() -> Path:
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise ValueError("windows_interop_unavailable")
    raw = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command",
        "[IO.Path]::GetTempPath()"], check=True, capture_output=True,
        text=True, timeout=5).stdout.strip()
    path = Path(subprocess.run(["wslpath", "-u", raw], check=True,
        capture_output=True, text=True, timeout=3).stdout.strip())
    if not path.is_dir():
        raise ValueError("windows_temp_unavailable")
    return path


def _secret_free_environment() -> dict[str, str]:
    blocked = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH",
               "PRIVATE_KEY", "BEARER")
    return {key: value for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in blocked)}


def _available_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _windows_child() -> int:
    cfg = json.loads(sys.stdin.read())
    ca, cert, key = Path(cfg["ca"]), Path(cfg["cert"]), Path(cfg["key"])
    server_ctx, client_ctx = _contexts(ca, cert, key)
    runtime = CompanionBridgeMutualTLSRuntime(bind_address=cfg["bind"], port=0,
        tls_context=server_ctx, expected_peer_certificate_sha256=cfg["peer_pin"],
        receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": base64.b64decode(cfg["avatar_key"])},
            expected_generations={"wsl-core": "wsl-avatar-test-1"}),
        acknowledgment_source_id="windows-edge",
        acknowledgment_generation_id="windows-avatar-ack-test-1",
        acknowledgment_key=base64.b64decode(cfg["avatar_ack"]),
        socket_timeout_seconds=2.0)
    client = None
    renderer_client = None
    relay = None
    state_queue = None
    state_path: Path | None = None
    godot_process: subprocess.Popen[str] | None = None
    try:
        port = runtime.start()
        if cfg.get("godot_executable"):
            state_path = Path(cfg["godot_temp"]) / "avatar_state.json"
            state_queue = WindowsGodotAvatarStateQueue(
                state_emitter=AvatarStateEmitter(state_path))
        print(f"READY {port}", flush=True)
        client = CompanionBridgeMutualTLSClient(address=cfg["wsl_ip"],
            port=cfg["wsl_port"], server_hostname="wsl-core.test",
            tls_context=client_ctx,
            acknowledgment_receiver=CompanionBridgeReceiver(
                source_keys={"wsl-core": base64.b64decode(cfg["observation_ack"])},
                expected_generations={"wsl-core": "wsl-observation-ack-test-1"}),
            expected_server_certificate_sha256=cfg["wsl_pin"], timeout_seconds=3.0)
        publisher = WindowsGamePerformanceBridgePublisher(
            observer=WindowsGamePerformanceObserver(), client=client,
            source_id="windows-edge", session_id="cross-host-test",
            generation_id="windows-observation-test-1",
            source_key=base64.b64decode(cfg["observation_key"]),
            process_id=os.getpid())
        publisher.publish_once()
        incoming = runtime.receive(timeout=10.0)
        delivered: list[dict[str, object]] = []

        def render(payload: Mapping[str, object],
                   message: VerifiedBridgeMessage) -> bool:
            delivered.append(dict(payload))
            if state_queue is not None:
                return state_queue.enqueue(payload, message)
            return True

        owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=runtime,
            receipt_verifier=lambda receipt, digest, _message:
                receipt == "smoke-admission" and digest == "a" * 64,
            renderer_sink=render)
        accepted = owner.dispatch_one(incoming)
        print("RESULT " + json.dumps({"accepted": accepted,
            "renderer_effect_proven": owner.status().renderer_effect_proven,
            "phrase": delivered[0].get("phrase") if delivered else None}), flush=True)
        if not accepted or not delivered:
            return 2
        if cfg.get("godot_executable"):
            if state_queue is None or state_path is None or state_queue.accepted_count != 1:
                raise RuntimeError("godot_avatar_state_queue_rejected")
            queued_state = json.loads(state_path.read_text(encoding="utf-8"))
            metadata = queued_state.get("metadata")
            if (not isinstance(metadata, dict)
                    or metadata.get("session_id") != "cross-host-test"
                    or metadata.get("turn_id") != "smoke-turn"
                    or metadata.get("workload_mode") != "gaming"
                    or metadata.get("output_mode") != "chat_response_visual_only"
                    or queued_state.get("workload_mode") != "gaming"):
                raise RuntimeError("godot_avatar_state_lineage_invalid")
            temp_root = Path(cfg["godot_temp"])
            temp_root.mkdir(parents=True, exist_ok=True)
            project = temp_root / "godot_avatar_demo"
            shutil.copytree(Path(cfg["godot_project"]), project,
                ignore=shutil.ignore_patterns(".godot", "*.uid"))
            renderer_client = CompanionBridgeMutualTLSClient(
                address=cfg["wsl_ip"], port=cfg["renderer_port"],
                server_hostname="wsl-core.test", tls_context=client_ctx,
                acknowledgment_receiver=CompanionBridgeReceiver(
                    source_keys={"wsl-renderer-core": base64.b64decode(
                        cfg["renderer_ack_key"])},
                    expected_generations={"wsl-renderer-core":
                        "wsl-renderer-ack-test-1"}),
                expected_server_certificate_sha256=cfg["wsl_pin"],
                timeout_seconds=4.0)
            relay = WindowsRendererReportRelay(client=renderer_client,
                source_id="windows-renderer-relay", session_id="godot-renderer-smoke",
                generation_id="windows-renderer-test-1",
                source_key=base64.b64decode(cfg["renderer_source_key"]),
                renderer_generation_id="godot-demo-cross-host-test-1")
            relay_port = relay.start()
            environment = _secret_free_environment()
            isolated_profile = temp_root / "profile"
            environment.update({
                "SENTIENTOS_RENDERER_GENERATION_ID": "godot-demo-cross-host-test-1",
                "SENTIENTOS_RENDERER_REPORT_RELAY_PORT": str(relay_port),
                "XDG_CACHE_HOME": str(temp_root / "cache"),
                "XDG_CONFIG_HOME": str(temp_root / "config"),
                "XDG_DATA_HOME": str(temp_root / "data"),
                "APPDATA": str(isolated_profile / "AppData" / "Roaming"),
                "LOCALAPPDATA": str(isolated_profile / "AppData" / "Local"),
                "HOME": str(isolated_profile),
                "TEMP": str(temp_root / "temp"),
                "TMP": str(temp_root / "temp"),
            })
            for name in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                         "APPDATA", "LOCALAPPDATA", "HOME", "TEMP"):
                Path(environment[name]).mkdir(parents=True, exist_ok=True)
            listen_port = _available_udp_port()
            environment["SENTIENTOS_GODOT_LISTEN_PORT"] = str(listen_port)
            godot_process = subprocess.Popen([cfg["godot_executable"], "--headless",
                "--path", str(project), "--script",
                "res://tests/avatar_state_udp_probe.gd"], stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", env=environment, bufsize=1)
            assert godot_process.stdout is not None
            godot_lines: queue.Queue[str] = queue.Queue()
            threading.Thread(target=_forward_lines,
                args=(godot_process.stdout, godot_lines), daemon=True).start()
            ready_deadline = time.monotonic() + 15.0
            ready = ""
            while time.monotonic() < ready_deadline:
                ready = _read_line(godot_lines,
                    max(0.1, ready_deadline - time.monotonic()))
                if ready.startswith("godot_avatar_state_listener_ready:"):
                    break
                if ready.startswith("SCRIPT ERROR:"):
                    raise RuntimeError("godot_avatar_state_listener_failed")
            if not ready.startswith("godot_avatar_state_listener_ready:"):
                raise RuntimeError("godot_avatar_state_listener_failed")
            forwarder = AvatarStateForwarder(state_path, host="127.0.0.1",
                port=listen_port, poll_interval=0.02)
            forwarded_state = forwarder._read_state()
            if forwarded_state is None:
                raise RuntimeError("godot_avatar_state_forwarder_rejected")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as state_sender:
                state_sender.sendto(json.dumps(forwarded_state,
                    ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                    ("127.0.0.1", listen_port))
            godot_output: list[str] = []
            while True:
                line = _read_line(godot_lines, 15.0)
                godot_output.append(line)
                if line == "godot_avatar_state_queue_probe_passed":
                    break
                if line.startswith("SCRIPT ERROR:"):
                    raise RuntimeError("godot_avatar_state_probe_failed")
            godot_process.wait(timeout=5.0)
            if godot_process.returncode != 0:
                raise RuntimeError("godot_avatar_state_probe_failed")
            deadline = time.monotonic() + 8.0
            while relay.status().forwarded == 0 and time.monotonic() < deadline:
                time.sleep(0.02)
            if relay.status().forwarded != 1:
                raise RuntimeError("renderer_report_mtls_forward_failed")
            report_line = next((line for line in godot_output
                if line.startswith("sentientos_renderer_report_json:")), None)
            if report_line is None:
                raise RuntimeError("godot_renderer_report_missing")
            report = json.loads(report_line.split(":", 1)[1])
            if (report.get("session_id") != metadata["session_id"]
                    or report.get("turn_id") != metadata["turn_id"]
                    or report.get("output_digest") != metadata["output_digest"]
                    or report.get("output_mode") != metadata["output_mode"]
                    or report.get("commanded_state", {}).get("workload_mode") != "gaming"):
                raise RuntimeError("godot_renderer_command_lineage_mismatch")
            print("RENDERER_RESULT " + json.dumps({"godot_headless": "passed",
                "relay_forwarded": 1, "avatar_state_queue": "accepted",
                "command_lineage": "verified", "workload_mode": "gaming",
                "renderer_effect_proven": False}), flush=True)
        return 0
    except Exception as exc:
        print("ERROR " + type(exc).__name__, flush=True)
        return 2
    finally:
        if relay:
            relay.close()
        if godot_process and godot_process.poll() is None:
            godot_process.kill()
            try:
                godot_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                pass
        runtime.close()


def _read_line(lines: queue.Queue[str], timeout: float) -> str:
    try:
        return lines.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError("windows_edge_process_timeout") from exc


def _forward_lines(stream: TextIO, lines: queue.Queue[str]) -> None:
    for line in stream:
        lines.put(line.rstrip())


def run(*, windows_checkout: Path, windows_python: Path,
       godot_executable: Path | None = None) -> dict[str, object]:
    if platform.system() != "Linux" or not (
            os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP")):
        raise ValueError("wsl2_required")
    windows_script = windows_checkout / "scripts" / Path(__file__).name
    if not windows_script.is_file() or not windows_python.is_file():
        raise ValueError("windows_smoke_runtime_missing")
    if godot_executable is not None and not godot_executable.is_file():
        raise ValueError("godot_executable_unavailable")
    windows_godot_project = windows_checkout / "godot_avatar_demo"
    if godot_executable is not None and not (windows_godot_project / "project.godot").is_file():
        raise ValueError("windows_godot_project_unavailable")
    wsl_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
        check=True, capture_output=True, text=True, timeout=3).stdout.strip()
    wsl_dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
        check=True, capture_output=True, text=True, timeout=3).stdout.strip()
    if wsl_dirty:
        raise ValueError("wsl_checkout_must_be_clean")
    git_exe = Path("/mnt/c/Program Files/Git/cmd/git.exe")
    windows_checkout_arg = _win_path(windows_checkout)
    try:
        win_sha = subprocess.run([str(git_exe), "-C", windows_checkout_arg,
            "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
            timeout=5).stdout.strip()
        dirty = subprocess.run([str(git_exe), "-C", windows_checkout_arg,
            "status", "--porcelain"], check=True, capture_output=True, text=True,
            timeout=5).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError("windows_checkout_git_verification_failed") from exc
    if dirty:
        raise ValueError("windows_checkout_must_be_clean")
    if win_sha != wsl_sha:
        raise ValueError("source_sha_mismatch")
    wsl_ip, windows_ip = _addresses()
    observation_key, observation_ack, avatar_key, avatar_ack, renderer_key, renderer_ack = (
        secrets.token_bytes(32) for _ in range(6))
    process: subprocess.Popen[str] | None = None
    core: CompanionBridgeMutualTLSRuntime | None = None
    renderer_owner: RendererReportCaptureOwner | None = None
    renderer_store: RendererReportEvidenceStore | None = None
    renderer_temp: tempfile.TemporaryDirectory[str] | None = None
    sender: MutualTLSAvatarCommandSender | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="sentientos-bridge-smoke-",
                dir=_win_temp()) as temp:
            ids = _test_identities(Path(temp))
            wsl, edge, ca = ids["wsl"], ids["windows"], ids["ca"]
            wsl_server, wsl_client = _contexts(ca, wsl["cert"], wsl["key"])
            core = CompanionBridgeMutualTLSRuntime(bind_address=wsl_ip, port=0,
                tls_context=wsl_server, expected_peer_certificate_sha256=edge["pin"],
                receiver=CompanionBridgeReceiver(
                    source_keys={"windows-edge": observation_key},
                    expected_generations={"windows-edge": "windows-observation-test-1"}),
                acknowledgment_source_id="wsl-core",
                acknowledgment_generation_id="wsl-observation-ack-test-1",
                acknowledgment_key=observation_ack, socket_timeout_seconds=2.0)
            core_port = core.start()
            renderer_port: int | None = None
            if godot_executable is not None:
                renderer_temp = tempfile.TemporaryDirectory(
                    prefix="sentientos-renderer-smoke-")
                renderer_core = CompanionBridgeMutualTLSRuntime(bind_address=wsl_ip, port=0,
                    tls_context=wsl_server,
                    expected_peer_certificate_sha256=edge["pin"],
                    receiver=CompanionBridgeReceiver(
                        source_keys={"windows-renderer-relay": renderer_key},
                        expected_generations={"windows-renderer-relay":
                            "windows-renderer-test-1"}),
                    acknowledgment_source_id="wsl-renderer-core",
                    acknowledgment_generation_id="wsl-renderer-ack-test-1",
                    acknowledgment_key=renderer_ack, socket_timeout_seconds=2.0)
                renderer_store = RendererReportEvidenceStore(
                    Path(renderer_temp.name) / "captures")
                renderer_owner = RendererReportCaptureOwner(
                    runtime=renderer_core, store=renderer_store)
                renderer_owner.start()
                renderer_port = renderer_core.status().port
                if renderer_port is None:
                    raise RuntimeError("renderer_core_listener_failed")
            cfg = {"bind": windows_ip, "peer_pin": wsl["pin"], "wsl_ip": wsl_ip,
                "wsl_port": core_port, "wsl_pin": wsl["pin"],
                "ca": _win_path(ca), "cert": _win_path(edge["cert"]),
                "key": _win_path(edge["key"]),
                "observation_key": base64.b64encode(observation_key).decode(),
                "observation_ack": base64.b64encode(observation_ack).decode(),
                "avatar_key": base64.b64encode(avatar_key).decode(),
                "avatar_ack": base64.b64encode(avatar_ack).decode()}
            if godot_executable is not None and renderer_port is not None:
                cfg.update({"renderer_port": renderer_port,
                    "renderer_source_key": base64.b64encode(renderer_key).decode(),
                    "renderer_ack_key": base64.b64encode(renderer_ack).decode(),
                    "godot_executable": _win_path(godot_executable),
                    "godot_project": _win_path(windows_godot_project),
                    "godot_temp": _win_path(Path(temp) / "godot-run")})
            python = str(windows_python)
            script = _win_path(windows_script)
            process = subprocess.Popen([python, script, "--windows-edge-child"],
                cwd=str(ROOT), env=_secret_free_environment(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", bufsize=1)
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps(cfg, separators=(",", ":")))
            process.stdin.close()
            lines: queue.Queue[str] = queue.Queue()
            stdout = process.stdout
            assert stdout is not None
            threading.Thread(target=_forward_lines, args=(stdout, lines),
                daemon=True).start()
            ready = _read_line(lines, 12.0)
            if not ready.startswith("READY "):
                raise RuntimeError("windows_listener_failed")
            edge_port = int(ready.split()[1])
            performance = GamePerformanceBridgeDetector(
                receiver=core, source_id="windows-edge",
                generation_provider=lambda: "windows-observation-test-1",
            ).receive_once(timeout=10.0)
            if performance.process_cpu_percent is None or performance.process_rss_bytes is None:
                raise RuntimeError("windows_process_observation_unavailable")
            client = CompanionBridgeMutualTLSClient(address=windows_ip,
                port=edge_port, server_hostname="windows-edge.test",
                tls_context=wsl_client,
                acknowledgment_receiver=CompanionBridgeReceiver(
                    source_keys={"windows-edge": avatar_ack},
                    expected_generations={"windows-edge": "windows-avatar-ack-test-1"}),
                expected_server_certificate_sha256=edge["pin"], timeout_seconds=3.0)
            sender = MutualTLSAvatarCommandSender(client=client,
                source_id="wsl-core", session_id="cross-host-test",
                generation_id="wsl-avatar-test-1", source_key=avatar_key,
                admission_receipt_builder=lambda _auth: {
                    "receipt_id": "smoke-admission", "semantic_digest": "a" * 64})
            from control_plane import Decision, ReasonCode, RequestType
            from control_plane.records import AuthorizationRecord
            auth = AuthorizationRecord.create(request_type=RequestType.AVATAR_EMISSION,
                requester_id="cross-host-test", intent_hash="b" * 64,
                context_hash="c" * 64, policy_version="smoke-fixture",
                decision=Decision.ALLOW, reason=ReasonCode.OK,
                metadata={"session_id": "cross-host-test"})
            emitted = BridgeChatAvatarOutputEmitter(sender).emit_display_text(
                "Cross-host test output.", authorization=auth,
                metadata={"session_id": "cross-host-test", "turn_id": "smoke-turn",
                    "output_digest": "d" * 64, "workload_mode": "gaming"})
            result = _read_line(lines, 12.0)
            if not result.startswith("RESULT "):
                raise RuntimeError("windows_dispatch_failed")
            edge_result = json.loads(result[len("RESULT "):])
            renderer_result: dict[str, object] | None = None
            renderer_capture: dict[str, object] | None = None
            if godot_executable is not None:
                renderer_line = _read_line(lines, 45.0)
                if not renderer_line.startswith("RENDERER_RESULT "):
                    raise RuntimeError("godot_renderer_report_failed")
                renderer_result = json.loads(renderer_line[len("RENDERER_RESULT "):])
                if renderer_owner is None or renderer_store is None:
                    raise RuntimeError("renderer_report_capture_unavailable")
                deadline = time.monotonic() + 10.0
                while renderer_owner.status()["captured"] == 0 and time.monotonic() < deadline:
                    time.sleep(0.02)
                if renderer_owner.status()["captured"] != 1:
                    raise RuntimeError("renderer_report_not_captured_by_wsl_core")
                records = renderer_store.world_state_records(max_records=4)
                if len(records) != 1:
                    raise RuntimeError("renderer_report_durable_record_missing")
                renderer_capture = records[0]
                payload = renderer_capture.get("payload")
                if (not isinstance(payload, dict)
                        or payload.get("transport_authentication_principal") !=
                            "windows-renderer-relay"
                        or payload.get("renderer_source_independently_authenticated") is not False
                        or payload.get("renderer_state_independently_observed") is not False
                        or renderer_capture.get("effect_proven") is not False):
                    raise RuntimeError("renderer_report_evidence_boundary_invalid")
            process.wait(timeout=5)
            if process.returncode != 0:
                raise RuntimeError("windows_edge_child_failed")
            return {"schema_version": "sentientos.gaming_companion_cross_host_smoke:v1",
                "status": "passed" if edge_result["accepted"] else "blocked",
                "source_sha": wsl_sha, "windows_to_wsl": "passed",
                "windows_process_cpu_percent": performance.process_cpu_percent,
                "windows_process_rss_bytes": performance.process_rss_bytes,
                "windows_frame_time_source": "unsupported",
                "windows_process_id_exposed": False,
                "godot_headless": (renderer_result.get("godot_headless")
                    if renderer_result else "not_run"),
                "godot_avatar_state_queue": (renderer_result.get("avatar_state_queue")
                    if renderer_result else "not_run"),
                "godot_command_lineage": (renderer_result.get("command_lineage")
                    if renderer_result else "not_run"),
                "godot_workload_mode": (renderer_result.get("workload_mode")
                    if renderer_result else "not_run"),
                "renderer_report_mtls": ("passed" if renderer_result else "not_run"),
                "renderer_report_wsl_capture": ("passed" if renderer_capture else "not_run"),
                "renderer_report_effect_proven": False,
                "renderer_report_capture_temporary": renderer_result is not None,
                "wsl_to_windows_queue": "passed" if edge_result["accepted"] else "blocked",
                "chat_emitter": emitted["status"],
                "renderer_effect_proven": edge_result["renderer_effect_proven"],
                "credentials": "ephemeral test-only credentials",
                "ephemeral_listeners_started": 4 if renderer_result else 2,
                "firewall_changed": False, "services_installed": False,
                "persistent_host_configuration_changed": False,
                "production_commissioning_claimed": False,
                "host_mutation_performed": False}
    finally:
        if renderer_owner:
            renderer_owner.close()
        if renderer_temp:
            renderer_temp.cleanup()
        if sender:
            sender.close()
        if core:
            core.close()
        if process and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-edge-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--windows-checkout", type=Path)
    parser.add_argument("--windows-python", type=Path)
    parser.add_argument("--godot-executable", type=Path,
        help="optionally run the Windows Godot renderer-report probe headlessly")
    args = parser.parse_args(argv)
    if args.windows_edge_child:
        try:
            return _windows_child()
        except Exception as exc:
            print("ERROR " + type(exc).__name__, flush=True)
            return 2
    if args.windows_checkout is None or args.windows_python is None:
        parser.error("--windows-checkout and --windows-python are required")
    try:
        result = run(windows_checkout=args.windows_checkout,
            windows_python=args.windows_python,
            godot_executable=args.godot_executable)
    except subprocess.CalledProcessError as exc:
        command = Path(str(exc.cmd[0])).name if exc.cmd else "command"
        result = {"schema_version": "sentientos.gaming_companion_cross_host_smoke:v1",
            "status": "blocked", "reason_code": f"{command}_failed_{exc.returncode}",
            "host_mutation_performed": False, "production_commissioning_claimed": False}
    except Exception as exc:
        result = {"schema_version": "sentientos.gaming_companion_cross_host_smoke:v1",
            "status": "blocked", "reason_code": (
                str(exc.args[0])[:128] if isinstance(exc, ValueError) and exc.args
                else type(exc).__name__),
            "host_mutation_performed": False, "production_commissioning_claimed": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
