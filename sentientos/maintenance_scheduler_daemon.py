"""Explicit, exact-profile ownership of bounded maintenance scheduler lifetimes.

This is lifecycle authority only.  It neither discovers profiles nor creates,
admits, leases, implements, validates, lands, or externally releases work.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos import maintenance_loop_scheduler as scheduler

ADOPTION_SCHEMA = "sentientos.maintenance_scheduler_daemon_adoption:v1"
EVIDENCE_SCHEMA = "sentientos.maintenance_scheduler_daemon_event:v1"
TERMINAL = {
    "maintenance_scheduler_stopped": "stopped",
    "maintenance_scheduler_stop": "paused",
    "maintenance_scheduler_failure_threshold": "failure_threshold_reached",
    "maintenance_scheduler_lock_busy": "lock_contention",
}


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def validate_adoption(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "enabled", "scheduler_config_path", "scheduler_config_digest",
                "expected_scheduler_schema", "evidence_path", "shutdown_timeout_seconds",
                "reentry_delay_seconds"}
    if set(value) != required or value.get("schema_version") != ADOPTION_SCHEMA:
        raise ValueError("invalid_scheduler_daemon_adoption")
    if type(value.get("enabled")) is not bool:
        raise ValueError("invalid_scheduler_daemon_adoption_posture")
    if value.get("expected_scheduler_schema") != scheduler.CONFIG_SCHEMA:
        raise ValueError("scheduler_daemon_schema_mismatch")
    for key in ("shutdown_timeout_seconds", "reentry_delay_seconds"):
        if type(value.get(key)) not in (int, float) or float(value[key]) <= 0:
            raise ValueError("invalid_scheduler_daemon_bound")
    result = dict(value)
    if not result["enabled"]:
        return result
    path = Path(str(result["scheduler_config_path"])).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError("scheduler_config_file_invalid")
    path = path.resolve(strict=True)
    cfg = scheduler.load_config(path)
    if cfg["config_digest"] != result["scheduler_config_digest"]:
        raise ValueError("maintenance_scheduler_daemon_config_drift")
    result["scheduler_config_path"] = str(path)
    evidence = Path(str(result["evidence_path"])).expanduser()
    if evidence.is_symlink() or not evidence.parent.is_dir():
        raise ValueError("scheduler_daemon_evidence_path_invalid")
    evidence = evidence.resolve(strict=False)
    if evidence.parent != Path(str(cfg["scheduler_state_root"])) or evidence in {
        Path(str(cfg["journal_path"])), Path(str(cfg["stop_marker"])),
        Path(str(cfg["scheduler_state_root"])) / "scheduler.lock",
    }:
        raise ValueError("scheduler_daemon_evidence_custody_invalid")
    result["evidence_path"] = str(evidence)
    return result


def load_adoption(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("scheduler_daemon_adoption_file_invalid")
    return validate_adoption(json.loads(source.read_text(encoding="utf-8")))


class MaintenanceSchedulerOwner:
    """One daemon-local owner repeatedly composing bounded scheduler runs."""

    def __init__(self, adoption: Mapping[str, Any], *,
                 runner: Callable[..., dict[str, Any]] = scheduler.run_bounded,
                 waiter: Callable[[threading.Event, float], bool] | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self._adoption = validate_adoption(adoption)
        self._runner = runner
        self._waiter = waiter or (lambda event, seconds: event.wait(seconds))
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._guard = threading.Lock()
        self._health: dict[str, Any] = {"status": "configured" if self._adoption["enabled"] else "disabled", "read_only": True}
        if self._adoption["enabled"]:
            self._record("scheduler_adoption_configured")

    def health(self) -> dict[str, Any]:
        with self._guard:
            return dict(self._health)

    def _set(self, status: str, reason: str | None = None) -> None:
        with self._guard:
            self._health = {"status": status, "reason": reason, "read_only": True,
                            "scheduler_config_digest": self._adoption.get("scheduler_config_digest")}

    def _record(self, event_type: str, **detail: Any) -> None:
        path = Path(str(self._adoption["evidence_path"]))
        event = {"schema_version": EVIDENCE_SCHEMA, "event_type": event_type,
                 "recorded_at_utc": self._clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                 "scheduler_config_path": self._adoption["scheduler_config_path"],
                 "scheduler_config_digest": self._adoption["scheduler_config_digest"], **detail}
        event["event_digest"] = _digest_bytes(_bytes(event))
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "ab") as handle:
            handle.write(_bytes(event) + b"\n"); handle.flush(); os.fsync(handle.fileno())

    def start(self) -> bool:
        if not self._adoption["enabled"]:
            return False
        with self._guard:
            if self._thread is not None and self._thread.is_alive():
                return False
            # Validate exact bytes and the bound watchdog immediately before ownership.
            try:
                scheduler.doctor(scheduler.load_config(self._adoption["scheduler_config_path"]))
                if scheduler.load_config(self._adoption["scheduler_config_path"])["config_digest"] != self._adoption["scheduler_config_digest"]:
                    raise ValueError("maintenance_scheduler_daemon_config_drift")
            except Exception as exc:
                self._health = {"status": "degraded", "reason": str(exc), "read_only": True,
                                "scheduler_config_digest": self._adoption["scheduler_config_digest"]}
                self._record("scheduler_adoption_degraded", reason=str(exc))
                return False
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="sentientosd-maintenance-scheduler", daemon=True)
            self._thread.start()
            return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                cfg = scheduler.load_config(self._adoption["scheduler_config_path"])
                if cfg["config_digest"] != self._adoption["scheduler_config_digest"]:
                    raise ValueError("maintenance_scheduler_daemon_config_drift")
                scheduler.doctor(cfg)
                self._set("running"); self._record("scheduler_lifetime_started")
                result = self._runner(cfg, sleeper=lambda seconds: self._stop.wait(seconds), stop_requested=self._stop.is_set)
                status = str(result.get("status", "maintenance_scheduler_recovery_ambiguous"))
                self._record("scheduler_bounded_run_returned", scheduler_status=status)
                if status == "maintenance_scheduler_daemon_shutdown":
                    self._set("stopped", "daemon_shutdown"); break
                terminal = TERMINAL.get(status)
                if terminal:
                    self._set(terminal, status); self._record("scheduler_terminal_disposition", disposition=terminal); break
                if status not in {"maintenance_scheduler_cycle_limit", "maintenance_scheduler_time_limit"}:
                    self._set("degraded", status); self._record("scheduler_adoption_degraded", reason=status); break
                self._set("idle_between_bounded_lifetimes")
                if self._waiter(self._stop, float(self._adoption["reentry_delay_seconds"])):
                    break
            except Exception as exc:
                reason = str(exc)
                status = "config_drift" if "config_drift" in reason else "recovery_ambiguous" if "recovery_ambiguous" in reason else "degraded"
                self._set(status, reason); self._record("scheduler_adoption_degraded", reason=reason); break
        self._record("scheduler_lifetime_stopped", reason=self.health().get("reason"))

    def stop(self) -> bool:
        self._record("daemon_shutdown_requested") if self._adoption["enabled"] else None
        self._stop.set()
        thread = self._thread
        if thread is None:
            return True
        thread.join(float(self._adoption["shutdown_timeout_seconds"]))
        if thread.is_alive():
            self._set("degraded", "bounded_shutdown_timeout")
            self._record("scheduler_adoption_degraded", reason="bounded_shutdown_timeout")
            return False
        return True


__all__ = ["ADOPTION_SCHEMA", "EVIDENCE_SCHEMA", "MaintenanceSchedulerOwner", "load_adoption", "validate_adoption"]
