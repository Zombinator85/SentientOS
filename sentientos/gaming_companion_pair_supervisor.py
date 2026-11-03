"""Coordinate the independently authorized Windows-edge and WSL-core owners.

The coordinator owns process ordering and pair health only. Each role still
uses ``GamingCompanionProcessSupervisor`` for receipt verification, launch
authorization, readiness, graceful shutdown, and generation-rotated recovery.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Protocol

from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_process_supervisor import (
    CompanionProcessSupervisorStatus,
    GamingCompanionProcessSupervisor,
)


class _RoleOwner(Protocol):
    def start(self) -> object: ...
    def status(self) -> CompanionProcessSupervisorStatus: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class GamingCompanionPairStatus:
    state: str
    core: CompanionProcessSupervisorStatus
    edge: CompanionProcessSupervisorStatus
    last_failure: str | None


def _safe_failure(exc: Exception) -> str:
    candidate = str(exc.args[0]) if exc.args else ""
    return (candidate if re.fullmatch(r"[a-z0-9_]{1,96}(?::[a-z0-9_]{1,96})?", candidate)
            else type(exc).__name__)


class GamingCompanionPairSupervisor:
    """Run core then edge, and close edge then core as one deployment lifetime.

    Recovery remains role-local and must obtain newly verified generations.
    If either role exhausts recovery or otherwise leaves its supervised
    lifecycle, the coordinator closes its peer so a half-live deployment is
    not reported as healthy. No credentials, generations, or authority are
    created here.
    """

    def __init__(self, *, core: GamingCompanionProcessSupervisor,
                 edge: GamingCompanionProcessSupervisor,
                 poll_interval_seconds: float = 0.25) -> None:
        if type(core) is not GamingCompanionProcessSupervisor or type(edge) is not GamingCompanionProcessSupervisor:
            raise CompanionBridgeError("companion_pair_process_supervisors_required")
        if core is edge:
            raise CompanionBridgeError("companion_pair_distinct_supervisors_required")
        if (isinstance(poll_interval_seconds, bool)
                or not isinstance(poll_interval_seconds, (int, float))
                or not 0.05 <= poll_interval_seconds <= 10):
            raise CompanionBridgeError("companion_pair_poll_interval_invalid")
        self._core = core
        self._edge = edge
        self._poll = float(poll_interval_seconds)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None
        self._started = False
        self._state = "stopped"
        self._last_failure: str | None = None

    def status(self) -> GamingCompanionPairStatus:
        with self._lock:
            state, failure = self._state, self._last_failure
        return GamingCompanionPairStatus(state, self._core.status(),
                                         self._edge.status(), failure)

    def start(self) -> GamingCompanionPairStatus:
        with self._lock:
            if self._started:
                raise CompanionBridgeError("companion_pair_supervisor_already_started")
            self._started = True
            self._state = "starting"
        attempted: list[_RoleOwner] = []
        try:
            for owner, expected_role in ((self._core, "wsl_core"), (self._edge, "windows_edge")):
                if self._stop.is_set():
                    raise CompanionBridgeError("companion_pair_supervisor_stopping")
                attempted.append(owner)
                owner.start()
                self._require_role_running(owner, expected_role)
            if self._stop.is_set():
                raise CompanionBridgeError("companion_pair_supervisor_stopping")
        except Exception as exc:
            failure = _safe_failure(exc)
            cleanup_failure = self._close_owners(reversed(attempted))
            with self._lock:
                self._last_failure = cleanup_failure or failure
                self._state = "failed"
            raise
        with self._lock:
            self._state = "running"
            self._monitor = threading.Thread(target=self._monitor_roles,
                name="sentientos-companion-pair-supervisor", daemon=True)
            self._monitor.start()
        return self.status()

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            monitor = self._monitor
            if self._state not in {"stopped", "failed"}:
                self._state = "stopping"
        if monitor is not None and monitor is not threading.current_thread():
            monitor.join(timeout=max(1.0, self._poll * 4))
        failure = self._close_owners((self._edge, self._core))
        with self._lock:
            self._monitor = None
            if failure is not None:
                self._last_failure = failure
                self._state = "failed"
            elif self._state != "failed":
                self._state = "stopped"
        if failure is not None:
            raise CompanionBridgeError(failure)

    @staticmethod
    def _require_role_running(owner: _RoleOwner, expected_role: str) -> None:
        status = owner.status()
        if status.role != expected_role or status.state != "running":
            raise CompanionBridgeError("companion_pair_role_not_running:" + expected_role)

    @staticmethod
    def _close_owners(owners: Iterable[_RoleOwner]) -> str | None:
        failure: str | None = None
        for owner in owners:
            try:
                owner.close()
            except Exception as exc:
                failure = failure or _safe_failure(exc)
        return failure

    def _monitor_roles(self) -> None:
        while not self._stop.wait(self._poll):
            core, edge = self._core.status(), self._edge.status()
            statuses = ((core, "wsl_core"), (edge, "windows_edge"))
            failed = next((status for status, role in statuses
                if status.role not in {None, role} or status.state in {"failed", "stopped"}), None)
            if failed is not None:
                reason = failed.last_failure or "companion_pair_role_unavailable"
                cleanup_failure = self._close_owners((self._edge, self._core))
                with self._lock:
                    self._last_failure = cleanup_failure or reason
                    self._state = "failed"
                self._stop.set()
                return
            with self._lock:
                self._state = ("recovering" if any(status.state != "running"
                    for status, _role in statuses) else "running")


__all__ = ["GamingCompanionPairStatus", "GamingCompanionPairSupervisor"]
