"""Foreground Windows-edge owner when WSL core is supervised by chat."""
from __future__ import annotations

import argparse
import json
import platform
import re
import signal
import threading
from collections.abc import Mapping, Sequence
from typing import Any, Callable, cast

from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_deployment import SCHEMA_MUTUAL_TLS_REVERSE, validate_manifest
from .gaming_companion_pair_entrypoint import resolve_pair_provider
from .gaming_companion_process_supervisor import GamingCompanionProcessSupervisor
from .gaming_companion_role_entrypoint import load_role_manifest


EdgeSupervisorProvider = Callable[[Mapping[str, Any]], object]
DeploymentLaunchAuthorizer = Callable[[Mapping[str, Any]], bool]


def run_windows_edge_supervisor(*, manifest: Mapping[str, Any],
        supervisor_provider: EdgeSupervisorProvider,
        launch_authorizer: DeploymentLaunchAuthorizer,
        stop_event: threading.Event, poll_interval_seconds: float = 0.25,
        system_name: str | None = None) -> int:
    """Authorize and supervise only the Windows publisher process.

    WSL core remains owned by the chat child. Per-spawn generation checks,
    exact command authorization, health checks, and bounded recovery stay in
    the existing ``GamingCompanionProcessSupervisor``.
    """
    if not callable(supervisor_provider) or not callable(launch_authorizer):
        raise CompanionBridgeError("companion_edge_supervisor_authority_callbacks_required")
    if (isinstance(poll_interval_seconds, bool)
            or not isinstance(poll_interval_seconds, (int, float))
            or not 0.05 <= poll_interval_seconds <= 10):
        raise CompanionBridgeError("companion_edge_supervisor_poll_interval_invalid")
    normalized = validate_manifest(dict(manifest))
    if normalized.get("schema_version") != SCHEMA_MUTUAL_TLS_REVERSE:
        raise CompanionBridgeError("companion_role_manifest_v3_required")
    for field in ("installation_identity_ref", "runtime_handoff_ref",
                  "software_generation_digest"):
        if not isinstance(normalized.get(field), str) or not normalized[field].strip():
            raise CompanionBridgeError("companion_pair_authority_reference_missing")
    if (system_name or platform.system()) != "Windows":
        raise CompanionBridgeError("companion_pair_windows_host_required")
    if launch_authorizer(normalized) is not True:
        raise CompanionBridgeError("companion_pair_launch_authority_denied")

    candidate = supervisor_provider(normalized)
    if type(candidate) is not GamingCompanionProcessSupervisor:
        raise CompanionBridgeError("companion_edge_supervisor_type_mismatch")
    supervisor = cast(GamingCompanionProcessSupervisor, candidate)
    if supervisor.status().role != "windows_edge":
        raise CompanionBridgeError("companion_edge_supervisor_role_mismatch")
    try:
        status = supervisor.start()
        if status.role != "windows_edge" or status.state != "running":
            return 3
        while not stop_event.wait(float(poll_interval_seconds)):
            status = supervisor.status()
            if status.role != "windows_edge" or status.state not in {
                    "running", "recovering"}:
                return 3
        return 0
    finally:
        supervisor.close()


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
        manifest = load_role_manifest(args.manifest)
        result = run_windows_edge_supervisor(manifest=manifest,
            supervisor_provider=lambda value: resolve_pair_provider(
                args.provider)(value),
            launch_authorizer=lambda value: resolve_pair_provider(
                args.launch_authorizer)(value) is True,
            stop_event=stop_event, poll_interval_seconds=args.poll_interval)
        print(json.dumps({"schema_version": "sentientos.gaming_companion_edge_supervisor_status:v1",
            "deployment_id": manifest["deployment_id"],
            "status": "stopped" if result == 0 else "unhealthy",
            "authority_effects_performed": False}, sort_keys=True, separators=(",", ":")))
        return result
    except Exception as exc:
        candidate_code = str(exc.args[0]) if exc.args else ""
        code = (candidate_code if re.fullmatch(
            r"[a-z0-9_]{1,96}(?::[a-z0-9_]{1,96})?", candidate_code)
            else type(exc).__name__)
        print(json.dumps({"schema_version": "sentientos.gaming_companion_edge_supervisor_status:v1",
            "status": "blocked", "reason_code": code,
            "authority_effects_performed": False}, sort_keys=True, separators=(",", ":")))
        return 2
    finally:
        for handled_signal, handler in previous_handlers.items():
            signal.signal(handled_signal, handler)


__all__ = ["EdgeSupervisorProvider", "DeploymentLaunchAuthorizer",
    "run_windows_edge_supervisor", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
