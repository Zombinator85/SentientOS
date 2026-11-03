"""Foreground owner for the paired Windows-edge/WSL-core deployment."""
from __future__ import annotations

import argparse
import importlib
import json
import platform
import re
import signal
import threading
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_deployment import SCHEMA_MUTUAL_TLS_REVERSE, validate_manifest
from .gaming_companion_pair_supervisor import (
    GamingCompanionPairStatus,
    GamingCompanionPairSupervisor,
)
from .gaming_companion_role_entrypoint import load_role_manifest


PairSupervisorProvider = Callable[[Mapping[str, Any]], object]
DeploymentLaunchAuthorizer = Callable[[Mapping[str, Any]], bool]


def resolve_pair_provider(reference: str) -> Callable[..., object]:
    if (not isinstance(reference, str) or len(reference) > 512
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*", reference)):
        raise CompanionBridgeError("companion_pair_provider_reference_invalid")
    module_name, attribute = reference.split(":", 1)
    try:
        provider = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise CompanionBridgeError("companion_pair_provider_unavailable") from exc
    if not callable(provider):
        raise CompanionBridgeError("companion_pair_provider_not_callable")
    return cast(Callable[..., object], provider)


def run_pair(*, manifest: Mapping[str, Any],
             pair_provider: PairSupervisorProvider,
             launch_authorizer: DeploymentLaunchAuthorizer,
             stop_event: threading.Event,
             poll_interval_seconds: float = 0.25,
             system_name: str | None = None) -> int:
    """Authorize the deployment, then run its two independently gated roles.

    The Windows launcher owns the WSL process boundary and the Windows-edge
    process. Its provider resolves protected custody only after the deployment
    launch record is accepted; each child supervisor still repeats its own
    generation and process-launch authorization checks.
    """
    if not callable(pair_provider) or not callable(launch_authorizer):
        raise CompanionBridgeError("companion_pair_authority_callbacks_required")
    if (isinstance(poll_interval_seconds, bool)
            or not isinstance(poll_interval_seconds, (int, float))
            or not 0.05 <= poll_interval_seconds <= 10):
        raise CompanionBridgeError("companion_pair_poll_interval_invalid")
    normalized = validate_manifest(dict(manifest))
    if normalized.get("schema_version") != SCHEMA_MUTUAL_TLS_REVERSE:
        raise CompanionBridgeError("companion_role_manifest_v3_required")
    for field in ("installation_identity_ref", "runtime_handoff_ref",
                  "software_generation_digest"):
        value = normalized.get(field)
        if not isinstance(value, str) or not value.strip():
            raise CompanionBridgeError("companion_pair_authority_reference_missing")
    if (system_name or platform.system()) != "Windows":
        raise CompanionBridgeError("companion_pair_windows_host_required")
    if launch_authorizer(normalized) is not True:
        raise CompanionBridgeError("companion_pair_launch_authority_denied")

    candidate = pair_provider(normalized)
    if type(candidate) is not GamingCompanionPairSupervisor:
        raise CompanionBridgeError("companion_pair_supervisor_type_mismatch")
    supervisor = candidate
    try:
        status = supervisor.start()
        if not _pair_running(status):
            return 3
        while not stop_event.wait(float(poll_interval_seconds)):
            status = supervisor.status()
            if status.state == "failed":
                return 3
            if status.state not in {"running", "recovering"} or not _pair_roles_match(status):
                return 3
        return 0
    finally:
        supervisor.close()


def _pair_roles_match(status: GamingCompanionPairStatus) -> bool:
    return status.core.role == "wsl_core" and status.edge.role == "windows_edge"


def _pair_running(status: GamingCompanionPairStatus) -> bool:
    return status.state == "running" and _pair_roles_match(status)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--provider", required=True,
        help="installed platform provider as package.module:factory")
    parser.add_argument("--launch-authorizer", required=True,
        help="deployment launch-record verifier as package.module:callable")
    parser.add_argument("--poll-interval", type=float, default=0.25)
    args = parser.parse_args(argv)
    stop_event = threading.Event()
    previous_handlers: dict[signal.Signals, Any] = {}

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[handled_signal] = signal.signal(handled_signal, request_stop)
    try:
        manifest = load_role_manifest(Path(args.manifest))
        result = run_pair(manifest=manifest,
            pair_provider=lambda value: resolve_pair_provider(args.provider)(value),
            launch_authorizer=lambda value: resolve_pair_provider(
                args.launch_authorizer)(value) is True,
            stop_event=stop_event, poll_interval_seconds=args.poll_interval)
        print(json.dumps({"schema_version": "sentientos.gaming_companion_pair_status:v1",
            "deployment_id": manifest["deployment_id"],
            "status": "stopped" if result == 0 else "unhealthy",
            "authority_effects_performed": False}, sort_keys=True, separators=(",", ":")))
        return result
    except Exception as exc:
        candidate_code = str(exc.args[0]) if exc.args else ""
        code = (candidate_code if re.fullmatch(
            r"[a-z0-9_]{1,96}(?::[a-z0-9_]{1,96})?", candidate_code)
            else type(exc).__name__)
        print(json.dumps({"schema_version": "sentientos.gaming_companion_pair_status:v1",
            "status": "blocked", "reason_code": code,
            "authority_effects_performed": False}, sort_keys=True, separators=(",", ":")))
        return 2
    finally:
        for handled_signal, handler in previous_handlers.items():
            signal.signal(handled_signal, handler)


__all__ = ["DeploymentLaunchAuthorizer", "PairSupervisorProvider", "resolve_pair_provider",
           "run_pair", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
