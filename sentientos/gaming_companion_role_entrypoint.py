"""Foreground executable entrypoint for one Windows-edge or WSL-core role.

The installed platform provider owns OS-specific custody and authority
integration. This module validates the deployment contract, selects the exact
role, accepts only its corresponding runtime owner, supervises health for the
process lifetime, and closes it on shutdown. It does not mint credentials,
generations, admissions, firewall rules, or OS persistence.
"""
from __future__ import annotations

import argparse
import importlib
import json
import platform
import re
import signal
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence, cast

from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_core_runtime import WSLCoreGamingCompanionRuntime
from .gaming_companion_deployment import SCHEMA_MUTUAL_TLS_REVERSE, validate_manifest
from .gaming_companion_edge_runtime import WindowsEdgeAvatarRuntime


class RoleRuntimeProvider(Protocol):
    def __call__(self, role: str, manifest: Mapping[str, Any]) -> object: ...


class RoleLaunchAuthorizer(Protocol):
    def __call__(self, role: str, manifest: Mapping[str, Any]) -> bool: ...


def load_role_manifest(path: Path | str) -> dict[str, Any]:
    manifest_path = Path(path)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise CompanionBridgeError("companion_role_manifest_path_invalid")
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompanionBridgeError("companion_role_manifest_unreadable") from exc
    if not isinstance(value, dict):
        raise CompanionBridgeError("companion_role_manifest_object_required")
    normalized = validate_manifest(value)
    if normalized.get("schema_version") != SCHEMA_MUTUAL_TLS_REVERSE:
        raise CompanionBridgeError("companion_role_manifest_v3_required")
    return normalized


def resolve_provider(reference: str) -> RoleRuntimeProvider:
    if (not isinstance(reference, str) or len(reference) > 512
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*", reference)):
        raise CompanionBridgeError("companion_role_provider_reference_invalid")
    module_name, attribute = reference.split(":", 1)
    try:
        provider = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise CompanionBridgeError("companion_role_provider_unavailable") from exc
    if not callable(provider):
        raise CompanionBridgeError("companion_role_provider_not_callable")
    return cast(RoleRuntimeProvider, provider)


def runtime_is_healthy(role: str, runtime: object) -> bool:
    status_method = getattr(runtime, "status", None)
    if not callable(status_method):
        return False
    status = status_method()
    if role == "windows_edge":
        return (type(runtime) is WindowsEdgeAvatarRuntime
            and status.state == "running" and status.listener_port is not None
            and status.dispatch.state == "running")
    if role == "wsl_core":
        return (type(runtime) is WSLCoreGamingCompanionRuntime
            and status.get("state") == "running"
            and status.get("forward_listener_running") is True)
    return False


def run_role(*, role: str, manifest: Mapping[str, Any],
        runtime_provider: RoleRuntimeProvider,
        launch_authorizer: RoleLaunchAuthorizer,
        stop_event: threading.Event,
        poll_interval_seconds: float = 0.25,
        system_name: str | None = None, is_wsl: bool | None = None) -> int:
    """Run one already-authorized role until stop or a health failure.

    ``runtime_provider`` is installed platform code and must call the existing
    role composition factory with OS custody readers and authority verifiers.
    Actual generation, admission, certificate, and key checks remain in those
    factories. Recovery is left to the outer process supervisor so each restart
    obtains a new, verified generation pair rather than replaying state here.
    """
    if role not in {"windows_edge", "wsl_core"}:
        raise CompanionBridgeError("companion_role_invalid")
    if not callable(runtime_provider) or not callable(launch_authorizer):
        raise CompanionBridgeError("companion_role_authority_callbacks_required")
    if (isinstance(poll_interval_seconds, bool)
            or not isinstance(poll_interval_seconds, (int, float))
            or not 0.05 <= poll_interval_seconds <= 10):
        raise CompanionBridgeError("companion_role_poll_interval_invalid")
    normalized = validate_manifest(manifest)
    if normalized.get("schema_version") != SCHEMA_MUTUAL_TLS_REVERSE:
        raise CompanionBridgeError("companion_role_manifest_v3_required")
    for field in ("installation_identity_ref", "runtime_handoff_ref",
                  "software_generation_digest"):
        value = normalized.get(field)
        if not isinstance(value, str) or not value.strip():
            raise CompanionBridgeError("companion_role_authority_reference_missing")
    current_system = system_name or platform.system()
    if role == "windows_edge" and current_system != "Windows":
        raise CompanionBridgeError("companion_role_windows_required")
    if role == "wsl_core":
        if current_system != "Linux":
            raise CompanionBridgeError("companion_role_linux_required")
        if is_wsl is None:
            is_wsl = "microsoft" in Path("/proc/version").read_text(
                encoding="utf-8", errors="replace").lower()
        if is_wsl is not True:
            raise CompanionBridgeError("companion_role_wsl2_required")

    if launch_authorizer(role, normalized) is not True:
        raise CompanionBridgeError("companion_role_launch_authority_denied")

    runtime: object | None = None
    try:
        runtime = runtime_provider(role, normalized)
        expected_type = (WindowsEdgeAvatarRuntime if role == "windows_edge"
                         else WSLCoreGamingCompanionRuntime)
        if type(runtime) is not expected_type:
            raise CompanionBridgeError("companion_role_runtime_type_mismatch")
        runtime.start()
        while not stop_event.wait(float(poll_interval_seconds)):
            if not runtime_is_healthy(role, runtime):
                return 3
        return 0
    finally:
        close = getattr(runtime, "close", None)
        if callable(close):
            close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("windows_edge", "wsl_core"), required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--provider", required=True,
        help="installed platform provider as package.module:factory")
    parser.add_argument("--launch-authorizer", required=True,
        help="installed authority verifier as package.module:callable")
    parser.add_argument("--poll-interval", type=float, default=0.25)
    args = parser.parse_args(argv)
    stop_event = threading.Event()
    previous_handlers: dict[signal.Signals, Any] = {}

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[handled_signal] = signal.signal(handled_signal, request_stop)
    try:
        manifest = load_role_manifest(args.manifest)
        result = run_role(role=args.role, manifest=manifest,
            runtime_provider=lambda role, config: resolve_provider(args.provider)(role, config),
            launch_authorizer=lambda role, config: resolve_provider(
                args.launch_authorizer)(role, config) is True,
            stop_event=stop_event, poll_interval_seconds=args.poll_interval)
        print(json.dumps({"schema_version": "sentientos.gaming_companion_role_status:v1",
            "role": args.role, "deployment_id": manifest["deployment_id"],
            "status": "stopped" if result == 0 else "unhealthy",
            "authority_effects_performed": False}, sort_keys=True, separators=(",", ":")))
        return result
    except Exception as exc:
        candidate_code = str(exc.args[0]) if exc.args else ""
        code = (candidate_code if re.fullmatch(
            r"[a-z0-9_]{1,96}(?::[a-z0-9_]{1,96})?", candidate_code)
            else type(exc).__name__)
        print(json.dumps({"schema_version": "sentientos.gaming_companion_role_status:v1",
            "role": args.role, "status": "blocked", "reason_code": code,
            "authority_effects_performed": False}, sort_keys=True, separators=(",", ":")))
        return 2
    finally:
        for handled_signal, handler in previous_handlers.items():
            signal.signal(handled_signal, handler)


__all__ = ["RoleRuntimeProvider", "load_role_manifest", "resolve_provider",
    "RoleLaunchAuthorizer", "runtime_is_healthy", "run_role", "main"]
