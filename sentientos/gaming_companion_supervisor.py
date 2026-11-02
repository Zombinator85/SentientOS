"""Bounded supervision for authorized companion bridge generations.

The supervisor owns only the in-process listener lifecycle. It cannot create
keys, issue generations, change firewall policy, or install a system service.
Every recovery asks an injected authority-backed factory for a replacement
runtime and custody record, then verifies the rotation receipt before start.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .gaming_companion_bridge import CompanionBridgeError, VerifiedBridgeMessage
from .gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
    verify_generation_pair_rotation,
)


class SupervisedRuntime(Protocol):
    def start(self) -> int: ...
    def close(self) -> None: ...
    def status(self) -> object: ...
    def receive(self, timeout: float | None = None) -> VerifiedBridgeMessage: ...
    def supervisor_identity_bindings(self) -> tuple[dict[str, str], str, str]: ...


@dataclass(frozen=True, slots=True)
class CompanionBridgeSupervisorStatus:
    state: str
    generation_id: str | None
    acknowledgment_generation_id: str | None
    restart_count: int
    last_failure: str | None
    listener_port: int | None


RuntimeFactory = Callable[
    [BridgeGenerationPair | None],
    tuple[SupervisedRuntime, BridgeGenerationPair],
]
ReceiptVerifier = Callable[[str, BridgeGenerationCustodyRecord], bool]


class CompanionBridgeSupervisor:
    """Start and recover a private bridge under a fixed restart budget.

    ``runtime_factory`` must return a runtime whose source key, listener TLS
    identity, active receiver generation, and acknowledgment identity are
    already bound to the returned custody record. The supervisor verifies the
    external authority receipt and predecessor chain before opening it.
    """

    def __init__(self, *, runtime_factory: RuntimeFactory,
                 authority_receipt_verifier: ReceiptVerifier,
                 max_restarts: int = 3, poll_interval_seconds: float = 0.25,
                 backoff_base_seconds: float = 0.25) -> None:
        if not callable(runtime_factory) or not callable(authority_receipt_verifier):
            raise CompanionBridgeError("bridge_supervisor_authority_callbacks_required")
        if type(max_restarts) is not int or not 0 <= max_restarts <= 10:
            raise CompanionBridgeError("bridge_supervisor_restart_budget_invalid")
        for value, code in ((poll_interval_seconds, "bridge_supervisor_poll_interval_invalid"),
                            (backoff_base_seconds, "bridge_supervisor_backoff_invalid")):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.01 <= value <= 30:
                raise CompanionBridgeError(code)
        self._factory = runtime_factory
        self._verify = authority_receipt_verifier
        self._max_restarts = max_restarts
        self._poll = float(poll_interval_seconds)
        self._backoff = float(backoff_base_seconds)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None
        self._started_once = False
        self._runtime: SupervisedRuntime | None = None
        self._generation: BridgeGenerationPair | None = None
        self._restart_count = 0
        self._last_failure: str | None = None
        self._state = "stopped"
        self._listener_port: int | None = None

    def start(self) -> CompanionBridgeSupervisorStatus:
        with self._lock:
            if self._state != "stopped" or self._started_once:
                raise CompanionBridgeError("bridge_supervisor_already_started")
            self._started_once = True
            self._state = "starting"
        try:
            self._install_runtime(previous=None)
        except Exception:
            with self._lock:
                self._state = "failed"
            raise
        with self._lock:
            self._state = "running"
            self._monitor = threading.Thread(target=self._monitor_runtime,
                name="sentientos-companion-bridge-supervisor", daemon=True)
            self._monitor.start()
        return self.status()

    def status(self) -> CompanionBridgeSupervisorStatus:
        with self._lock:
            return CompanionBridgeSupervisorStatus(
                self._state,
                self._generation.source.generation_id if self._generation else None,
                self._generation.acknowledgment.generation_id if self._generation else None,
                self._restart_count, self._last_failure, self._listener_port,
            )

    @property
    def generation_id(self) -> str | None:
        with self._lock:
            return self._generation.source.generation_id if self._generation else None

    def receive(self, timeout: float | None = None) -> VerifiedBridgeMessage:
        """Read from the active generation, waiting briefly through recovery."""
        if timeout is not None and (isinstance(timeout, bool)
                or not isinstance(timeout, (int, float)) or timeout < 0):
            raise CompanionBridgeError("bridge_receive_timeout_invalid")
        deadline = None if timeout is None else time.monotonic() + float(timeout)
        while True:
            with self._lock:
                runtime = self._runtime
                state = self._state
            if state in {"failed", "stopped", "stopping"}:
                raise CompanionBridgeError("bridge_supervisor_unavailable")
            if runtime is not None and state == "running":
                try:
                    return runtime.receive(timeout=0)
                except CompanionBridgeError as exc:
                    if exc.args and exc.args[0] != "bridge_receive_timeout":
                        raise
            if deadline is not None and time.monotonic() >= deadline:
                raise CompanionBridgeError("bridge_receive_timeout")
            self._stop.wait(0.01 if deadline is None else min(0.01, max(0.0, deadline-time.monotonic())))

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            runtime, monitor = self._runtime, self._monitor
            self._state = "stopping" if runtime is not None else "stopped"
        if runtime is not None:
            try:
                runtime.close()
            except Exception as exc:
                with self._lock:
                    self._last_failure = type(exc).__name__
            finally:
                with self._lock:
                    self._runtime = None
                    self._listener_port = None
        if monitor is not None and monitor is not threading.current_thread():
            monitor.join(timeout=max(1.0, self._poll * 4))
        with self._lock:
            if self._state != "failed":
                self._state = "stopped"
            self._monitor = None

    def _install_runtime(self, *, previous: BridgeGenerationPair | None) -> None:
        runtime, generation = self._factory(previous)
        try:
            if self._stop.is_set():
                raise CompanionBridgeError("bridge_supervisor_stopping")
            if type(generation) is not BridgeGenerationPair:
                raise CompanionBridgeError("bridge_generation_pair_record_required")
            verify_generation_pair_rotation(previous=previous, successor=generation,
                                            authority_receipt_verifier=self._verify)
            bindings = runtime.supervisor_identity_bindings()
            expected_bindings = (
                {generation.source.source_id: generation.source.generation_id},
                generation.acknowledgment.source_id,
                generation.acknowledgment.generation_id,
            )
            if bindings != expected_bindings:
                raise CompanionBridgeError("bridge_runtime_generation_binding_mismatch")
            if self._stop.is_set():
                raise CompanionBridgeError("bridge_supervisor_stopping")
        except Exception:
            runtime.close()
            raise
        try:
            port = runtime.start()
            if self._stop.is_set():
                runtime.close()
                raise CompanionBridgeError("bridge_supervisor_stopping")
        except Exception:
            runtime.close()
            raise
        with self._lock:
            if self._stop.is_set():
                runtime.close()
                raise CompanionBridgeError("bridge_supervisor_stopping")
            self._runtime = runtime
            self._generation = generation
            self._listener_port = port

    def _monitor_runtime(self) -> None:
        while not self._stop.wait(self._poll):
            with self._lock:
                runtime = self._runtime
                previous = self._generation
                if self._state != "running" or runtime is None:
                    return
            try:
                running = bool(getattr(runtime.status(), "running"))
            except Exception:
                running = False
            if running:
                continue
            with self._lock:
                self._last_failure = "bridge_listener_stopped"
                if self._restart_count >= self._max_restarts:
                    self._state = "failed"
                    try:
                        runtime.close()
                    finally:
                        with self._lock:
                            if self._runtime is runtime:
                                self._runtime = None
                                self._listener_port = None
                    return
                attempt = self._restart_count + 1
                self._restart_count = attempt
                self._state = "recovering"
            try:
                runtime.close()
                if self._stop.wait(min(30.0, self._backoff * (2 ** (attempt - 1)))):
                    return
                self._install_runtime(previous=previous)
            except Exception as exc:
                with self._lock:
                    if self._stop.is_set():
                        return
                    self._last_failure = type(exc).__name__
                    self._state = "failed"
                    if self._runtime is runtime:
                        self._runtime = None
                        self._listener_port = None
                return
            with self._lock:
                self._state = "running"


__all__ = ["CompanionBridgeSupervisor", "CompanionBridgeSupervisorStatus"]
