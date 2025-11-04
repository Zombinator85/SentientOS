"""Lightweight watchdog supervising embodied SentientOS daemons."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Mapping, MutableMapping, Optional, Sequence

try:  # pragma: no cover - typing only on modern Python
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore[misc,assignment]

if sys.version_info >= (3, 8):  # pragma: no cover - typing helpers
    from typing import TYPE_CHECKING
else:  # pragma: no cover - fallback for legacy Python
    TYPE_CHECKING = False

if TYPE_CHECKING:  # pragma: no cover - type hints
    from sentientos.autonomy.runtime import AutonomyRuntime


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProcessHandle(Protocol):  # pragma: no cover - structural typing
    def poll(self) -> Optional[int]:
        ...

    def terminate(self) -> None:
        ...

    def wait(self, timeout: Optional[float] = None) -> Optional[int]:
        ...


@dataclass
class DaemonSpec:
    """Definition describing how a daemon should be launched."""

    command: Sequence[str]
    cwd: Optional[Path] = None
    env: Optional[Mapping[str, str]] = None
    idle_timeout: Optional[float] = None


def _default_process_factory(name: str, spec: DaemonSpec) -> ProcessHandle:
    env = os.environ.copy()
    if spec.env:
        env.update({str(k): str(v) for k, v in spec.env.items()})
    return subprocess.Popen(  # type: ignore[return-value]
        list(spec.command),
        cwd=str(spec.cwd) if spec.cwd else None,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=False,
    )


class ManagedDaemon:
    """Runtime bookkeeping for a supervised daemon."""

    def __init__(
        self,
        name: str,
        spec: DaemonSpec,
        *,
        process_factory: Callable[[str, DaemonSpec], ProcessHandle],
        now: Callable[[], float],
    ) -> None:
        self.name = name
        self.spec = spec
        self._process_factory = process_factory
        self._now = now
        self.process: Optional[ProcessHandle] = None
        self.last_start: Optional[float] = None
        self.last_activity: Optional[float] = None
        self.restart_count = 0

    def status(self, now: float) -> str:
        if not self.process:
            return "stopped"
        exit_code = self.process.poll()
        if exit_code is not None:
            return "stopped"
        timeout = self.spec.idle_timeout
        if timeout and self.last_activity is not None and (now - self.last_activity) >= timeout:
            return "idle"
        return "running"

    def start(self) -> None:
        self.process = self._process_factory(self.name, self.spec)
        self.last_start = self._now()
        self.last_activity = self.last_start
        self.restart_count += 1

    def stop(self, *, graceful_timeout: float = 5.0) -> None:
        if not self.process:
            return
        try:
            self.process.terminate()
            self.process.wait(timeout=graceful_timeout)
        except Exception:
            with suppress(Exception):
                self.process.kill()  # type: ignore[attr-defined]
        finally:
            self.process = None

    def mark_activity(self) -> None:
        self.last_activity = self._now()


class DaemonAutonomySupervisor:
    """Watchdog ensuring embodied daemons stay healthy and state persists."""

    def __init__(
        self,
        *,
        runtime: "AutonomyRuntime" | None = None,
        heartbeat_path: Path | None = None,
        log_path: Path | None = None,
        process_factory: Callable[[str, DaemonSpec], ProcessHandle] = _default_process_factory,
        check_interval: float = 5.0,
        heartbeat_interval: float = 60.0,
        readiness_interval: float = 86400.0,
        readiness_command: Optional[Sequence[str]] = None,
        auto_start: bool = False,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._runtime = runtime
        self._process_factory = process_factory
        self._check_interval = max(0.5, float(check_interval))
        self._heartbeat_interval = max(1.0, float(heartbeat_interval))
        self._readiness_interval = max(60.0, float(readiness_interval))
        self._readiness_command = list(readiness_command or [])
        self._now = now or time.time
        self._log_path = (log_path or Path("logs/autonomy_watchdog.jsonl"))
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._heartbeat_path = heartbeat_path or Path("pulse/heartbeat.snap")
        self._heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self._daemons: Dict[str, ManagedDaemon] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_heartbeat: Optional[float] = None
        self._last_readiness_run: Optional[float] = None
        self._last_readiness_summary: Optional[Mapping[str, object]] = None

        if auto_start:
            self.start()

    # -- Public API -----------------------------------------------------

    def register_daemon(
        self,
        name: str,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        idle_timeout: float | None = None,
        start_immediately: bool = True,
    ) -> None:
        spec = DaemonSpec(command=tuple(command), cwd=cwd, env=dict(env) if env else None, idle_timeout=idle_timeout)
        daemon = ManagedDaemon(
            name,
            spec,
            process_factory=self._process_factory,
            now=self._now,
        )
        with self._lock:
            self._daemons[name] = daemon
        if start_immediately:
            self._start_daemon(name, reason="initial_start")

    def note_activity(self, name: str) -> None:
        daemon = self._daemons.get(name)
        if daemon:
            daemon.mark_activity()

    def status_report(self) -> Mapping[str, str]:
        now = self._now()
        with self._lock:
            return {name: daemon.status(now) for name, daemon in self._daemons.items()}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="autonomy-supervisor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._check_interval * 2)
        with self._lock:
            for daemon in self._daemons.values():
                daemon.stop()
        self._persist_state()

    def run_iteration(self) -> None:
        self._ensure_daemons()
        self._ensure_heartbeat()
        self._ensure_readiness()

    # -- Internal helpers -----------------------------------------------

    def _run_loop(self) -> None:  # pragma: no cover - background thread
        while not self._stop.is_set():
            try:
                self.run_iteration()
            except Exception as exc:
                self._log_event("error", "loop", {"error": str(exc)})
            self._stop.wait(self._check_interval)

    def _start_daemon(self, name: str, *, reason: str) -> None:
        daemon = self._daemons.get(name)
        if not daemon:
            return
        try:
            daemon.start()
            self._log_event("daemon_started", name, {"reason": reason})
        except Exception as exc:
            self._log_event("daemon_start_failed", name, {"reason": reason, "error": str(exc)})

    def _ensure_daemons(self) -> None:
        now = self._now()
        with self._lock:
            for name, daemon in self._daemons.items():
                process = daemon.process
                exit_code: Optional[int] = None
                if process:
                    exit_code = process.poll()
                if process is None or exit_code is not None:
                    if exit_code is not None:
                        self._log_event("daemon_exit", name, {"exit_code": exit_code})
                    self._start_daemon(name, reason="restart")
                elif daemon.status(now) == "idle":
                    continue

    def _ensure_heartbeat(self) -> None:
        now = self._now()
        if self._last_heartbeat is not None and (now - self._last_heartbeat) < self._heartbeat_interval:
            return
        payload = {"timestamp": _utcnow()}
        self._heartbeat_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        self._last_heartbeat = now

    def _ensure_readiness(self) -> None:
        if not self._runtime:
            return
        now = self._now()
        if self._last_readiness_run and (now - self._last_readiness_run) < self._readiness_interval:
            return
        self._run_readiness_check()

    def _run_readiness_check(self) -> None:
        command = self._readiness_command or [
            sys.executable,
            "tools/autonomy_readiness.py",
            "--json",
            "--quiet",
        ]
        try:
            result = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            self._log_event("readiness_error", "autonomy", {"error": str(exc)})
            return
        if result.returncode != 0:
            self._log_event(
                "readiness_failed",
                "autonomy",
                {"status": result.returncode, "stderr": (result.stderr or "").strip()},
            )
            self._last_readiness_run = self._now()
            return
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            payload = {}
        summary = payload.get("summary", {})
        report_path = payload.get("report")
        self._write_readiness_summary(summary, report_path)
        metrics = getattr(self._runtime, "metrics", None)
        if metrics is not None:
            try:
                metrics.set_gauge("readiness_passed", 1.0 if summary.get("healthy") else 0.0)
            except Exception:  # pragma: no cover - metrics failures shouldn't break loop
                pass
        if hasattr(self._runtime, "record_readiness_success"):
            try:
                self._runtime.record_readiness_success(summary, report_path=report_path)
            except Exception as exc:  # pragma: no cover - defensive
                self._log_event("readiness_state_error", "autonomy", {"error": str(exc)})
        self._last_readiness_summary = summary
        self._last_readiness_run = self._now()
        self._log_event("readiness_passed", "autonomy", {"summary": summary})

    def _write_readiness_summary(self, summary: Mapping[str, object], report_path: Optional[str]) -> None:
        pulse_dir = self._heartbeat_path.parent
        pulse_dir.mkdir(parents=True, exist_ok=True)
        totals = summary.get("totals", {}) if isinstance(summary, Mapping) else {}
        lines = [
            f"timestamp: {_utcnow()}",
            f"healthy: {summary.get('healthy') if isinstance(summary, Mapping) else 'unknown'}",
            f"pass: {totals.get('PASS', 0)} fail: {totals.get('FAIL', 0)} missing: {totals.get('MISSING', 0)}",
        ]
        if report_path:
            lines.append(f"report: {report_path}")
        (pulse_dir / "last_readiness.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _persist_state(self) -> None:
        if not self._runtime:
            return
        try:
            if hasattr(self._runtime, "save_state"):
                self._runtime.save_state()
        except Exception as exc:  # pragma: no cover - defensive
            self._log_event("state_persist_failed", "autonomy", {"error": str(exc)})

    def _log_event(self, event: str, target: str, payload: Optional[Mapping[str, object]] = None) -> None:
        entry: MutableMapping[str, object] = {
            "timestamp": _utcnow(),
            "event": event,
            "target": target,
        }
        if payload:
            entry.update(payload)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


__all__ = ["DaemonAutonomySupervisor", "DaemonSpec"]

