#!/usr/bin/env python3
"""Run the loopback-only, GPU-backed local companion development service.

Requires SENTIENTOS_MODEL_CONFIG to point at a digest-pinned Ollama candidate.
All transcripts, invocation receipts, and process coordination stay in --state-dir.
This process is a supervised development composition, never production serving.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import hmac
import json
import os
import queue
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _TemporaryCompanionEdge:
    """Own test-only Windows mTLS edge, Godot process, and sender."""

    def __init__(self, *, windows_python: Path, windows_checkout: Path,
                 godot_executable: Path, godot_project: Path) -> None:
        from scripts.gaming_companion_cross_host_smoke import (
            _addresses, _contexts, _test_identities, _win_path, _win_temp,
            _secret_free_environment,
        )
        from sentientos.gaming_companion_avatar_output import (
            BridgeChatAvatarOutputEmitter, MutualTLSAvatarCommandSender,
        )
        from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
        from sentientos.gaming_companion_tls_transport import (
            CompanionBridgeMutualTLSClient,
        )

        self._temporary = tempfile.TemporaryDirectory(
            prefix="sentientos-companion-dev-", dir=_win_temp())
        root = Path(self._temporary.name)
        self._edge_process: subprocess.Popen[str] | None = None
        self._sender: Any | None = None
        self._lines: queue.Queue[str] = queue.Queue()
        self._report_file: Path | None = None
        try:
            identities = _test_identities(root)
            wsl, edge, ca = identities["wsl"], identities["windows"], identities["ca"]
            wsl_ip, windows_ip = _addresses()
            avatar_key, avatar_ack, receipt_key = (
                secrets.token_bytes(32) for _ in range(3))
            worker = root / "local_companion_edge_dev_worker.py"
            shutil.copyfile(ROOT / "scripts/local_companion_edge_dev_worker.py", worker)
            config = {
                "bind": windows_ip,
                "peer_pin": wsl["pin"],
                "ca": _win_path(ca),
                "cert": _win_path(edge["cert"]),
                "key": _win_path(edge["key"]),
                "avatar_key": base64.b64encode(avatar_key).decode("ascii"),
                "avatar_ack": base64.b64encode(avatar_ack).decode("ascii"),
                "receipt_key": base64.b64encode(receipt_key).decode("ascii"),
                "runtime_root": _win_path(root / "edge-runtime"),
                "godot_executable": _win_path(godot_executable),
                "godot_project": _win_path(godot_project),
            }
            self._edge_process = subprocess.Popen(
                [str(windows_python), _win_path(worker), _win_path(windows_checkout)],
                cwd=str(ROOT), env=_secret_free_environment(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", bufsize=1)
            assert self._edge_process.stdin is not None
            assert self._edge_process.stdout is not None
            self._edge_process.stdin.write(json.dumps(config, separators=(",", ":")) + "\n")
            self._edge_process.stdin.flush()
            self._report_file = root / "renderer-reports.jsonl"
            self.report_file = self._report_file
            threading.Thread(target=self._forward_lines,
                args=(self._edge_process.stdout, self._lines, self._report_file),
                daemon=True).start()
            ready = self._lines.get(timeout=20)
            if not ready.startswith("READY "):
                raise RuntimeError("temporary_windows_edge_failed:" + ready[:128])
            port = int(ready.split()[1])
            _server_context, client_context = _contexts(ca, wsl["cert"], wsl["key"])
            client = CompanionBridgeMutualTLSClient(
                address=windows_ip, port=port, server_hostname="windows-edge.test",
                tls_context=client_context,
                acknowledgment_receiver=CompanionBridgeReceiver(
                    source_keys={"windows-edge-dev": avatar_ack},
                    expected_generations={"windows-edge-dev":
                        "windows-avatar-ack-dev-1"}),
                expected_server_certificate_sha256=edge["pin"],
                timeout_seconds=4.0)
            def receipt_builder(_authorization: Any) -> dict[str, str]:
                receipt_id = "dev-" + uuid.uuid4().hex
                digest = hmac.new(receipt_key, receipt_id.encode("utf-8"),
                                  hashlib.sha256).hexdigest()
                return {"receipt_id": receipt_id, "semantic_digest": digest}
            self._sender = MutualTLSAvatarCommandSender(
                client=client, source_id="wsl-core-dev", session_id=None,
                generation_id="wsl-avatar-dev-1", source_key=avatar_key,
                admission_receipt_builder=receipt_builder)
            self.emitter = BridgeChatAvatarOutputEmitter(self._sender)
            self.state_file = root / "edge-runtime" / "avatar_state.json"
            self.identity_posture = "temporary_test_mtls_identities"
        except Exception:
            self.close()
            raise

    @staticmethod
    def _forward_lines(stream, target: queue.Queue[str], report_file: Path) -> None:
        for line in stream:
            rendered = line.rstrip()
            if rendered.startswith("RENDERER_REPORT "):
                try:
                    report = json.loads(rendered[len("RENDERER_REPORT "):])
                    with report_file.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(report, separators=(",", ":")))
                        handle.write(chr(10))
                        handle.flush()
                except (OSError, ValueError, TypeError):
                    pass
            target.put(rendered)

    def close(self) -> None:
        process = self._edge_process
        self._edge_process = None
        if self._sender is not None:
            self._sender.close()
            self._sender = None
        if process is not None:
            try:
                if process.stdin is not None:
                    process.stdin.write("STOP\n")
                    process.stdin.flush()
                    process.stdin.close()
                process.wait(timeout=10)
            except Exception:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        self._temporary.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--windows-python", type=Path)
    parser.add_argument("--windows-checkout", type=Path)
    parser.add_argument("--godot-exe", type=Path)
    parser.add_argument("--godot-project", type=Path)
    args = parser.parse_args()
    if args.host != "127.0.0.1" or not 1 <= args.port <= 65535:
        parser.error("development chat must bind only to 127.0.0.1")
    edge_args = (args.windows_python, args.windows_checkout, args.godot_exe,
                 args.godot_project)
    if any(value is not None for value in edge_args) and not all(
            value is not None for value in edge_args):
        parser.error("the temporary edge requires Windows Python, checkout, Godot, and project")
    config_path = os.environ.get("SENTIENTOS_MODEL_CONFIG")
    if not config_path or not Path(config_path).is_file():
        parser.error("SENTIENTOS_MODEL_CONFIG must identify the pinned local Ollama model")
    state = args.state_dir.expanduser().resolve()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    lock_path = state / "active-chat.lock"
    lock_handle = lock_path.open("a+", encoding="utf-8")
    os.chmod(lock_path, 0o600)
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("another local companion development process holds this state directory")

    runtime = state / "runtime"
    chat_state = state / "chat"
    memory = state / "memory"
    for directory in (runtime, chat_state, memory):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    os.environ["SENTIENTOS_DATA_DIR"] = str(runtime)
    os.environ["MEMORY_DIR"] = str(memory)
    os.environ["SENTIENTOS_RUNTIME_STATE_ROOT"] = str(state / "runtime-state")
    os.environ["SENTIENTOS_CONTROL_KERNEL_ROOT"] = str(state / "control-kernel")
    os.environ["SENTIENTOS_GOVERNOR_ROOT"] = str(state / "governor")
    os.environ["SENTIENTOS_FEDERATION_ROOT"] = str(state / "federation")
    os.environ["SENTIENTOS_REPO_ROOT"] = str(ROOT)
    pulse_root = state / "pulse-trust"
    pulse_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_key = pulse_root / "ed25519_private.key"
    public_key = pulse_root / "ed25519_public.key"
    if not private_key.is_file() or not public_key.is_file():
        from nacl.signing import SigningKey
        signing_key = SigningKey.generate()
        for path, value in ((private_key, signing_key.encode()),
                            (public_key, signing_key.verify_key.encode())):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
    os.environ["PULSE_TRUST_EPOCH_ROOT"] = str(pulse_root)
    os.environ["PULSE_TRUST_EPOCH_STATE"] = str(pulse_root / "epoch_state.json")
    os.environ["PULSE_SIGNING_KEY"] = str(private_key)
    os.environ["PULSE_VERIFY_KEY"] = str(public_key)
    # Persistent, machine-local development trust keys only; no commissioning or
    # production authority. Control-plane evidence stays outside the repository.
    os.environ["CONTROL_PLANE_LOG"] = str(state / "control-plane.jsonl")

    from sentientos.chat_service import configure_development_chat, run
    from sentientos.config import load_model_config
    from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
    from sentientos.local_model import LocalModel
    from sentientos.local_model_authority import (
        atomic_write_json, build_local_model_authority_map,
    )

    config = load_model_config()
    if len(config.candidates) != 1 or config.candidates[0].engine != "ollama":
        parser.error("development composition requires exactly one Ollama candidate")
    candidate = config.candidates[0]
    if candidate.path is None:
        parser.error("Ollama development candidate requires a local manifest path")
    authority = build_local_model_authority_map(
        config, allowed_roots=[candidate.path.parent])
    record = authority.records[0]
    if (record.disposition != "development_only"
            or record.runtime_eligibility_status != "eligible"
            or record.allowed_invocation_purposes != ("local_user_chat",)):
        parser.error("Ollama model authority is not eligible for local chat")
    model = LocalModel.autoload()
    if model.active_identity.posture != "development_only" or model.active_identity.fallback:
        parser.error("the exact local development model did not load")
    if authority.record_for_active_identity(model.active_identity, "local_user_chat") is None:
        parser.error("loaded model does not match its local-chat authority record")
    atomic_write_json(state / "model-authority-map.json", authority.to_dict())
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        runtime_root=state / "invocations")
    edge: _TemporaryCompanionEdge | None = None
    try:
        if all(value is not None for value in edge_args):
            if (not args.windows_python.is_file()
                    or not args.windows_checkout.is_dir()
                    or not args.godot_exe.is_file()
                    or not (args.godot_project / "project.godot").is_file()):
                parser.error("a temporary companion edge executable or project is missing")
            edge = _TemporaryCompanionEdge(
                windows_python=args.windows_python, windows_checkout=args.windows_checkout,
                godot_executable=args.godot_exe, godot_project=args.godot_project)
        configure_development_chat(invoker=invoker, data_root=chat_state,
            avatar_output_emitter=edge.emitter if edge else None)
        print(json.dumps({
            "state": "running",
            "posture": "development_only",
            "host": args.host,
            "port": args.port,
            "engine": model.active_identity.engine,
            "model": candidate.options.get("model"),
            "model_identity": model.active_identity.semantic_artifact_identity,
            "companion_output": ("temporary_mtls_windows_edge_and_godot"
                                 if edge else "not_configured"),
            "companion_identity_posture": (
                edge.identity_posture if edge else "unavailable"),
            "production_serving": False,
            "transcript_directory": str(chat_state / "conversations"),
            "godot_state_file": str(edge.state_file) if edge else None,
            "renderer_report_capture": str(edge.report_file) if edge else None,
        }), flush=True)
        run(host=args.host, port=args.port)
    finally:
        try:
            from sentientos.chat_service import close_production_chat
            close_production_chat()
        finally:
            if edge is not None:
                edge.close()
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
