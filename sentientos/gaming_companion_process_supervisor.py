"""Authority-gated supervision for one local gaming-companion process.

This is a foreground process owner, not an OS service installer. Every spawn
requires an authority callback bound to the exact command and bridge generation
pair. Recovery obtains and verifies a fresh pair before restarting, preventing
replay state from being silently reused.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_tls_transport import (
    BridgeGenerationPair,
    verify_generation_pair_rotation,
)


@dataclass(frozen=True, slots=True)
class CompanionProcessLaunchSpec:
    role: str
    argv: tuple[str, ...]
    working_directory: str
    environment: Mapping[str, str]
    startup_timeout_seconds: float = 15.0
    shutdown_timeout_seconds: float = 5.0

    @property
    def command_digest(self) -> str:
        import hashlib
        import json
        payload = {"role": self.role, "argv": self.argv,
            "working_directory": str(Path(self.working_directory).resolve()),
            "environment": dict(sorted(self.environment.items()))}
        return hashlib.sha256(json.dumps(payload, sort_keys=True,
            separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CompanionProcessSupervisorStatus:
    state: str
    role: str | None
    pid: int | None
    generation_id: str | None
    restart_count: int
    last_failure: str | None


class _ChildProcess(Protocol):
    pid: int
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


ProcessFactory = Callable[[BridgeGenerationPair | None],
                          tuple[CompanionProcessLaunchSpec, BridgeGenerationPair]]
ReceiptVerifier = Callable[[str, object], bool]
LaunchAuthorizer = Callable[[str, str, BridgeGenerationPair], bool]
HealthProbe = Callable[[_ChildProcess, CompanionProcessLaunchSpec], bool]
ProcessSpawner = Callable[..., _ChildProcess]
ForceStopAuthorizer = Callable[[str, int], bool]


def validate_launch_spec(spec: CompanionProcessLaunchSpec) -> None:
    if type(spec) is not CompanionProcessLaunchSpec:
        raise CompanionBridgeError("companion_process_launch_spec_required")
    if spec.role not in {"windows_edge", "wsl_core"}:
        raise CompanionBridgeError("companion_process_role_invalid")
    if (not isinstance(spec.argv, tuple) or not 1 <= len(spec.argv) <= 64
            or any(not isinstance(item, str) or not item or "\x00" in item
                   or len(item) > 4096 for item in spec.argv)
            or sum(len(item.encode("utf-8")) for item in spec.argv) > 16_384):
        raise CompanionBridgeError("companion_process_argv_invalid")
    directory = Path(spec.working_directory)
    if (not directory.is_absolute() or directory.is_symlink()
            or not directory.is_dir()):
        raise CompanionBridgeError("companion_process_working_directory_invalid")
    allowed_environment = {"SENTIENTOS_COMPANION_ROLE",
        "SENTIENTOS_COMPANION_MANIFEST", "SENTIENTOS_COMPANION_GENERATION_PAIR_REF"}
    if not isinstance(spec.environment, Mapping) or any(
            key not in allowed_environment
            or not isinstance(value, str) or "\x00" in value
            for key, value in spec.environment.items()):
        raise CompanionBridgeError("companion_process_environment_invalid")
    for value, code in ((spec.startup_timeout_seconds, "companion_process_startup_timeout_invalid"),
                        (spec.shutdown_timeout_seconds, "companion_process_shutdown_timeout_invalid")):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.1 <= value <= 60:
            raise CompanionBridgeError(code)


def _minimal_child_environment(additions: Mapping[str, str]) -> dict[str, str]:
    allowed = ("PATH", "HOME", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR",
               "HOMEDRIVE", "HOMEPATH", "USERPROFILE", "LOCALAPPDATA", "APPDATA")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update(additions)
    return environment


class GamingCompanionProcessSupervisor:
    """Run one explicitly authorized local edge or core foreground process."""

    def __init__(self, *, process_factory: ProcessFactory,
                 authority_receipt_verifier: ReceiptVerifier,
                 launch_authorizer: LaunchAuthorizer,
                 health_probe: HealthProbe,
                 expected_role: str | None = None,
                 force_stop_authorizer: ForceStopAuthorizer | None = None,
                 max_restarts: int = 3, poll_interval_seconds: float = 0.25,
                 spawner: ProcessSpawner = subprocess.Popen) -> None:
        if not all(callable(item) for item in
                   (process_factory, authority_receipt_verifier, launch_authorizer, health_probe, spawner)):
            raise CompanionBridgeError("companion_process_authority_callbacks_required")
        if expected_role is not None and expected_role not in {"windows_edge", "wsl_core"}:
            raise CompanionBridgeError("companion_process_role_invalid")
        if type(max_restarts) is not int or not 0 <= max_restarts <= 10:
            raise CompanionBridgeError("companion_process_restart_budget_invalid")
        if (isinstance(poll_interval_seconds, bool)
                or not isinstance(poll_interval_seconds, (int, float))
                or not 0.01 <= poll_interval_seconds <= 30):
            raise CompanionBridgeError("companion_process_poll_interval_invalid")
        self._factory = process_factory
        self._expected_role = expected_role
        self._verify = authority_receipt_verifier
        self._authorize = launch_authorizer
        self._probe = health_probe
        self._authorize_force_stop = force_stop_authorizer or (lambda _role, _pid: False)
        self._spawner = spawner
        self._max_restarts = max_restarts
        self._poll = float(poll_interval_seconds)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None
        self._started = False
        self._state = "stopped"
        self._child: _ChildProcess | None = None
        self._spec: CompanionProcessLaunchSpec | None = None
        self._generation: BridgeGenerationPair | None = None
        self._restart_count = 0
        self._last_failure: str | None = None

    def status(self) -> CompanionProcessSupervisorStatus:
        with self._lock:
            child, generation, spec = self._child, self._generation, self._spec
            return CompanionProcessSupervisorStatus(self._state,
                spec.role if spec else self._expected_role, child.pid if child else None,
                generation.source.generation_id if generation else None,
                self._restart_count, self._last_failure)

    def start(self) -> CompanionProcessSupervisorStatus:
        with self._lock:
            if self._started:
                raise CompanionBridgeError("companion_process_supervisor_already_started")
            self._started = True
            self._state = "starting"
        try:
            self._install(previous=None)
        except Exception:
            with self._lock:
                self._state = "failed"
            raise
        with self._lock:
            self._state = "running"
            self._monitor = threading.Thread(target=self._monitor_process,
                name="sentientos-companion-process-supervisor", daemon=True)
            self._monitor.start()
        return self.status()

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            child, spec, monitor = self._child, self._spec, self._monitor
            self._state = "stopping" if child is not None else "stopped"
        if child is not None and spec is not None:
            self._stop_child(child, spec)
        if monitor is not None and monitor is not threading.current_thread():
            monitor.join(timeout=max(1.0, self._poll * 4))
        with self._lock:
            self._child = None
            self._monitor = None
            if self._state != "failed":
                self._state = "stopped"

    def _install(self, *, previous: BridgeGenerationPair | None) -> None:
        spec, generation = self._factory(previous)
        validate_launch_spec(spec)
        if self._expected_role is not None and spec.role != self._expected_role:
            raise CompanionBridgeError("companion_process_role_mismatch")
        verify_generation_pair_rotation(previous=previous, successor=generation,
                                        authority_receipt_verifier=self._verify)
        if self._authorize(spec.role, spec.command_digest, generation) is not True:
            raise CompanionBridgeError("companion_process_launch_authority_denied")
        child = self._spawner(list(spec.argv), cwd=spec.working_directory,
            env=_minimal_child_environment(spec.environment), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False,
            close_fds=True)
        deadline = time.monotonic() + float(spec.startup_timeout_seconds)
        try:
            while not self._stop.is_set() and time.monotonic() < deadline:
                if child.poll() is not None:
                    raise CompanionBridgeError("companion_process_exited_during_startup")
                try:
                    if self._probe(child, spec):
                        break
                except Exception:
                    pass
                self._stop.wait(min(self._poll, max(0.0, deadline - time.monotonic())))
            else:
                raise CompanionBridgeError("companion_process_startup_timeout")
            if self._stop.is_set():
                raise CompanionBridgeError("companion_process_supervisor_stopping")
        except Exception:
            self._stop_child(child, spec)
            raise
        with self._lock:
            self._child, self._spec, self._generation = child, spec, generation

    def _stop_child(self, child: _ChildProcess, spec: CompanionProcessLaunchSpec) -> None:
        if child.poll() is not None:
            return
        child.terminate()
        try:
            child.wait(timeout=float(spec.shutdown_timeout_seconds))
        except subprocess.TimeoutExpired:
            if self._authorize_force_stop(spec.role, child.pid) is not True:
                raise CompanionBridgeError("companion_process_forced_stop_authority_denied")
            child.kill()
            child.wait(timeout=max(1.0, float(spec.shutdown_timeout_seconds)))

    def _monitor_process(self) -> None:
        unhealthy = 0
        while not self._stop.wait(self._poll):
            with self._lock:
                child, spec, previous = self._child, self._spec, self._generation
                if self._state != "running" or child is None or spec is None:
                    return
            try:
                healthy = child.poll() is None and self._probe(child, spec) is True
            except Exception:
                healthy = False
            unhealthy = 0 if healthy else unhealthy + 1
            if healthy or unhealthy < 3:
                continue
            if self._restart_count >= self._max_restarts:
                try:
                    self._stop_child(child, spec)
                except Exception as exc:
                    with self._lock:
                        self._last_failure = str(exc.args[0])[:128] if exc.args else type(exc).__name__
                with self._lock:
                    self._last_failure = self._last_failure or "companion_process_restart_budget_exhausted"
                    self._state = "failed"
                    if child.poll() is not None:
                        self._child = None
                        self._spec = None
                return
            with self._lock:
                self._last_failure = "companion_process_unhealthy_or_exited"
                self._restart_count += 1
                attempt = self._restart_count
                self._state = "recovering"
            try:
                self._stop_child(child, spec)
                if self._stop.wait(min(30.0, self._poll * (2 ** (attempt - 1)))):
                    return
                self._install(previous=previous)
            except Exception as exc:
                with self._lock:
                    self._last_failure = str(exc.args[0])[:128] if exc.args else type(exc).__name__
                    self._state = "failed"
                    self._child = None
                    self._spec = None
                return
            with self._lock:
                self._state = "running"
            unhealthy = 0


__all__ = ["CompanionProcessLaunchSpec", "CompanionProcessSupervisorStatus",
           "GamingCompanionProcessSupervisor", "validate_launch_spec"]
