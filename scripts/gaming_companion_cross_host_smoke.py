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
import ssl
import subprocess
import sys
import tempfile
import threading
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

from sentientos.gaming_companion_avatar_output import (
    BridgeChatAvatarOutputEmitter,
    MutualTLSAvatarCommandSender,
    WindowsEdgeAvatarCommandDispatchOwner,
)
from sentientos.gaming_companion_bridge import (
    CompanionBridgeReceiver,
    VerifiedBridgeMessage,
    encode_message,
)
from sentientos.gaming_companion_tls_transport import (
    MIN_TLS_VERSION,
    CompanionBridgeMutualTLSClient,
    CompanionBridgeMutualTLSRuntime,
)


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


def _test_identities(directory: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
        "SentientOS temporary smoke CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
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
            .not_valid_after(now + timedelta(hours=1))
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
    try:
        port = runtime.start()
        print(f"READY {port}", flush=True)
        client = CompanionBridgeMutualTLSClient(address=cfg["wsl_ip"],
            port=cfg["wsl_port"], server_hostname="wsl-core.test",
            tls_context=client_ctx,
            acknowledgment_receiver=CompanionBridgeReceiver(
                source_keys={"wsl-core": base64.b64decode(cfg["observation_ack"])},
                expected_generations={"wsl-core": "wsl-observation-ack-test-1"}),
            expected_server_certificate_sha256=cfg["wsl_pin"], timeout_seconds=3.0)
        observation = encode_message(kind="observation", source_id="windows-edge",
            session_id="cross-host-test", generation_id="windows-observation-test-1",
            sequence=1, payload={"schema_version": "sentientos.cross_host_smoke:v1",
                "direction": "windows_to_wsl", "fixture": True},
            key=base64.b64decode(cfg["observation_key"]),
            created_at=datetime.now(timezone.utc).isoformat())
        client.send(observation)
        incoming = runtime.receive(timeout=10.0)
        delivered: list[dict[str, object]] = []

        def render(payload: Mapping[str, object],
                   _message: VerifiedBridgeMessage) -> bool:
            delivered.append(dict(payload))
            return True

        owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=runtime,
            receipt_verifier=lambda receipt, digest, _message:
                receipt == "smoke-admission" and digest == "a" * 64,
            renderer_sink=render)
        accepted = owner.dispatch_one(incoming)
        print("RESULT " + json.dumps({"accepted": accepted,
            "renderer_effect_proven": owner.status().renderer_effect_proven,
            "phrase": delivered[0].get("phrase") if delivered else None}), flush=True)
        return 0 if accepted and delivered else 2
    except Exception as exc:
        print("ERROR " + type(exc).__name__, flush=True)
        return 2
    finally:
        runtime.close()


def _read_line(lines: queue.Queue[str], timeout: float) -> str:
    try:
        return lines.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError("windows_edge_process_timeout") from exc


def _forward_lines(stream: TextIO, lines: queue.Queue[str]) -> None:
    for line in stream:
        lines.put(line.rstrip())


def run(*, windows_checkout: Path, windows_python: Path) -> dict[str, object]:
    if platform.system() != "Linux" or not (
            os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP")):
        raise ValueError("wsl2_required")
    windows_script = windows_checkout / "scripts" / Path(__file__).name
    if not windows_script.is_file() or not windows_python.is_file():
        raise ValueError("windows_smoke_runtime_missing")
    wsl_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
        check=True, capture_output=True, text=True, timeout=3).stdout.strip()
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
    observation_key, observation_ack, avatar_key, avatar_ack = (
        secrets.token_bytes(32) for _ in range(4))
    process: subprocess.Popen[str] | None = None
    core: CompanionBridgeMutualTLSRuntime | None = None
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
            cfg = {"bind": windows_ip, "peer_pin": wsl["pin"], "wsl_ip": wsl_ip,
                "wsl_port": core_port, "wsl_pin": wsl["pin"],
                "ca": _win_path(ca), "cert": _win_path(edge["cert"]),
                "key": _win_path(edge["key"]),
                "observation_key": base64.b64encode(observation_key).decode(),
                "observation_ack": base64.b64encode(observation_ack).decode(),
                "avatar_key": base64.b64encode(avatar_key).decode(),
                "avatar_ack": base64.b64encode(avatar_ack).decode()}
            python = subprocess.run(["wslpath", "-u", str(windows_python)],
                check=True, capture_output=True, text=True, timeout=3).stdout.strip()
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
            observation = core.receive(timeout=10.0)
            if observation.payload.get("direction") != "windows_to_wsl":
                raise RuntimeError("windows_to_wsl_observation_invalid")
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
            process.wait(timeout=5)
            if process.returncode != 0:
                raise RuntimeError("windows_edge_child_failed")
            return {"schema_version": "sentientos.gaming_companion_cross_host_smoke:v1",
                "status": "passed" if edge_result["accepted"] else "blocked",
                "source_sha": wsl_sha, "windows_to_wsl": "passed",
                "wsl_to_windows_queue": "passed" if edge_result["accepted"] else "blocked",
                "chat_emitter": emitted["status"],
                "renderer_effect_proven": edge_result["renderer_effect_proven"],
                "credentials": "ephemeral test-only credentials",
                "firewall_changed": False, "services_installed": False,
                "production_commissioning_claimed": False,
                "host_mutation_performed": False}
    finally:
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
            windows_python=args.windows_python)
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
