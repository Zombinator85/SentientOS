"""Explicit, bounded daemon custody for the existing maintenance wake cycle.

This owner has timing and witnessing authority only.  Every effectful cadence
decision crosses :func:`maintenance_wake_cycle.wake_once`; downstream authority
and component locks remain owned by that coordinator and its components.

The implementation uses POSIX ``fcntl`` locks and is not a native Windows
service or OS-scheduler integration.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos import maintenance_wake_cycle as wake

ADOPTION_SCHEMA = "sentientos.maintenance_wake_daemon_adoption:v1"
EVENT_SCHEMA = "sentientos.maintenance_wake_daemon_cadence_event:v1"
OWNER_EVENT_SCHEMA = "sentientos.maintenance_wake_daemon_owner_event:v1"
ZERO_DIGEST = "sha256:" + "0" * 64
CONTINUING_WAKE_STATUSES = frozenset({
    "maintenance_wake_idle", "autonomy_cycle_idle", "autonomy_cycle_completed",
    "autonomy_cycle_continuing", "autonomy_cycle_waiting",
})


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _utc(value: datetime | str) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("wake_daemon_timestamp_not_timezone_aware")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _external(path: Any, repo: Path, *, exists: bool) -> Path:
    raw = Path(str(path)).expanduser()
    if raw.is_symlink() or any(parent.is_symlink() for parent in (raw, *raw.parents) if parent.exists()):
        raise ValueError("wake_daemon_custody_symlink")
    resolved = raw.resolve(strict=exists)
    git = (repo / ".git").resolve(strict=True)
    if resolved == repo or repo in resolved.parents or resolved == git or git in resolved.parents:
        raise ValueError("wake_daemon_custody_inside_repository")
    return resolved


def validate_adoption(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "enabled", "wake_config_path", "wake_config_digest",
                "expected_wake_schema", "cadence_state_root", "journal_path", "evidence_path",
                "stop_marker", "cadence_interval_seconds", "schedule_anchor_utc",
                "initial_run_posture", "maximum_cycles", "maximum_daemon_wall_clock_seconds",
                "shutdown_timeout_seconds"}
    allowed = required | {"adoption_config_digest"}
    if set(value) - allowed or not required.issubset(value) or value.get("schema_version") != ADOPTION_SCHEMA:
        raise ValueError("invalid_wake_daemon_adoption")
    if type(value.get("enabled")) is not bool:
        raise ValueError("invalid_wake_daemon_adoption_posture")
    if value.get("expected_wake_schema") != wake.CONFIG_SCHEMA:
        raise ValueError("wake_daemon_schema_mismatch")
    for key in ("cadence_interval_seconds", "maximum_cycles", "maximum_daemon_wall_clock_seconds"):
        if type(value.get(key)) is not int or int(value[key]) < 1:
            raise ValueError("invalid_wake_daemon_bound")
    if type(value.get("shutdown_timeout_seconds")) not in (int, float) or float(value["shutdown_timeout_seconds"]) <= 0:
        raise ValueError("invalid_wake_daemon_bound")
    if value.get("initial_run_posture") not in {"immediate", "after_interval"}:
        raise ValueError("invalid_wake_daemon_adoption")
    anchor = _utc(str(value["schedule_anchor_utc"]))
    result = dict(value)
    # A disabled document is an explicit non-adoption and cannot cause discovery.
    if not result["enabled"]:
        expected = digest({k: v for k, v in result.items() if k != "adoption_config_digest"})
        if result.get("adoption_config_digest") not in (None, "", expected):
            raise ValueError("wake_daemon_adoption_digest_mismatch")
        result["adoption_config_digest"] = expected
        return result
    config_path = Path(str(value["wake_config_path"])).expanduser()
    if config_path.is_symlink() or not config_path.is_file():
        raise ValueError("wake_daemon_config_file_invalid")
    bound = wake.load_config(config_path)
    if bound["config_digest"] != value["wake_config_digest"]:
        raise ValueError("maintenance_wake_daemon_config_drift")
    repo = Path(str(bound["repository_root"]))
    state = _external(value["cadence_state_root"], repo, exists=True)
    if not state.is_dir() or not stat.S_ISDIR(os.lstat(state).st_mode) or (os.name == "posix" and stat.S_IMODE(os.lstat(state).st_mode) != 0o700):
        raise ValueError("wake_daemon_state_root_invalid")
    paths = [_external(value[key], repo, exists=False) for key in ("journal_path", "evidence_path", "stop_marker")]
    if any(path.parent != state for path in paths) or len(set(paths)) != len(paths):
        raise ValueError("wake_daemon_state_path_collision")
    result.update(wake_config_path=str(config_path.resolve()), cadence_state_root=str(state),
                  journal_path=str(paths[0]), evidence_path=str(paths[1]), stop_marker=str(paths[2]),
                  schedule_anchor_utc=_utc_text(anchor))
    expected = digest({k: v for k, v in result.items() if k != "adoption_config_digest"})
    if value.get("adoption_config_digest") not in (None, "", expected):
        raise ValueError("wake_daemon_adoption_digest_mismatch")
    result["adoption_config_digest"] = expected
    return result


def load_adoption(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("wake_daemon_adoption_file_invalid")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("invalid_wake_daemon_adoption")
    return validate_adoption(value)


def _events(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(str(cfg["journal_path"]))
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    prior = ZERO_DIGEST
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line); claimed = row.pop("event_digest")
            if row.get("schema_version") != EVENT_SCHEMA or row.get("adoption_config_digest") != cfg["adoption_config_digest"] or row.get("prior_event_digest") != prior or digest(row) != claimed:
                raise ValueError("wake_daemon_journal_chain_invalid")
            _utc(str(row["evaluation_time"])); _utc(str(row["next_due_utc"]))
            row["event_digest"] = claimed; rows.append(row); prior = claimed
    except (OSError, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("wake_daemon_journal_corrupt") from exc
    if rows and rows[-1]["event_type"] == "invocation_intent":
        raise ValueError("wake_daemon_recovery_ambiguous")
    return rows


def _append(cfg: Mapping[str, Any], event: Mapping[str, Any], prior: str) -> dict[str, Any]:
    row = {"schema_version": EVENT_SCHEMA, "adoption_config_digest": cfg["adoption_config_digest"],
           "wake_config_digest": cfg["wake_config_digest"], "prior_event_digest": prior, **event}
    row["event_digest"] = digest(row)
    fd = os.open(cfg["journal_path"], os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "ab") as handle:
        handle.write(canonical_bytes(row) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    return row


def _next(cfg: Mapping[str, Any], rows: list[dict[str, Any]]) -> tuple[int, datetime]:
    completed = [row for row in rows if row["event_type"] == "invocation_completed"]
    if completed:
        return int(completed[-1]["invocation_ordinal"]) + 1, _utc(completed[-1]["next_due_utc"])
    anchor = _utc(str(cfg["schedule_anchor_utc"]))
    if cfg["initial_run_posture"] == "after_interval":
        anchor += timedelta(seconds=int(cfg["cadence_interval_seconds"]))
    return 1, anchor


def inspect(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_adoption(config); rows = _events(cfg); ordinal, due = _next(cfg, rows)
    return {"status": "wake_daemon_state_ready", "event_count": len(rows),
            "next_invocation_ordinal": ordinal, "next_due_utc": _utc_text(due),
            "last_event_digest": rows[-1]["event_digest"] if rows else ZERO_DIGEST}


def _verified_wake(cfg: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    bound = wake.load_config(cfg["wake_config_path"])
    if bound["config_digest"] != cfg["wake_config_digest"]:
        raise ValueError("maintenance_wake_daemon_config_drift")
    report = wake.doctor(bound, evaluation_time=evaluation_time)
    if report["status"] != "maintenance_wake_ready":
        raise ValueError("maintenance_wake_component_drift:" + ",".join(report.get("reason_codes", ())))
    return cast(dict[str, Any], bound)


def run_once(config: Mapping[str, Any], *, evaluation_time: datetime,
             monotonic: Callable[[], float] = time.monotonic,
             wake_runner: Callable[..., dict[str, Any]] = wake.wake_once) -> dict[str, Any]:
    cfg = validate_adoption(config); now = _utc(evaluation_time)
    lock_path = Path(cfg["cadence_state_root"]) / "wake-daemon-cadence.lock"; lock_path.touch(exist_ok=True)
    with lock_path.open("r+") as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return {"status": "maintenance_wake_daemon_lock_contention"}
        rows = _events(cfg); ordinal, due = _next(cfg, rows)
        if Path(cfg["stop_marker"]).exists():
            return {"status": "maintenance_wake_daemon_paused", "next_due_utc": _utc_text(due)}
        if now < due:
            return {"status": "maintenance_wake_daemon_not_due", "next_due_utc": _utc_text(due)}
        evaluation = _utc_text(now); bound = _verified_wake(cfg, evaluation)
        prior = rows[-1]["event_digest"] if rows else ZERO_DIGEST
        common = {"invocation_ordinal": ordinal, "evaluation_time": evaluation}
        intent = _append(cfg, {**common, "event_type": "invocation_intent", "wake_status": None,
                               "disposition": "pending", "next_due_utc": _utc_text(due)}, prior)
        began = monotonic(); result = wake_runner(bound, evaluation_time=evaluation); duration = max(0.0, monotonic() - began)
        status = str(result.get("status", "unknown"))
        reasons = set(str(item) for item in result.get("reason_codes", ()))
        if status in CONTINUING_WAKE_STATUSES: disposition = "continue"
        elif status in {"maintenance_wake_paused", "autonomy_cycle_paused"}: disposition = "paused"
        elif status == "maintenance_wake_blocked" and "wake_lock_unavailable" in reasons: disposition = "lock_contention"
        elif status in {"maintenance_wake_blocked", "autonomy_cycle_blocked"}: disposition = "blocked"
        else: disposition = "unknown_result"
        interval = timedelta(seconds=int(cfg["cadence_interval_seconds"])); next_due = due + interval
        while next_due <= now: next_due += interval
        completed = _append(cfg, {**common, "event_type": "invocation_completed", "wake_status": status,
            "wake_result_digest": digest(result), "duration_seconds": duration, "disposition": disposition,
            "next_due_utc": _utc_text(next_due)}, intent["event_digest"])
        return {"status": "maintenance_wake_daemon_" + disposition, "wake_result": result, "event": completed}


def run_bounded(config: Mapping[str, Any], *, wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                monotonic: Callable[[], float] = time.monotonic,
                waiter: Callable[[float], None] = time.sleep,
                wake_runner: Callable[..., dict[str, Any]] = wake.wake_once,
                stop_requested: Callable[[], bool] = lambda: False) -> dict[str, Any]:
    cfg = validate_adoption(config); owner_path = Path(cfg["cadence_state_root"]) / "wake-daemon-owner.lock"; owner_path.touch(exist_ok=True)
    with owner_path.open("r+") as owner_lock:
        try: fcntl.flock(owner_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return {"status": "maintenance_wake_daemon_owner_lock_contention", "cycle_count": 0}
        started = monotonic(); cycles = 0; results: list[dict[str, Any]] = []
        while cycles < int(cfg["maximum_cycles"]):
            if stop_requested(): return {"status": "maintenance_wake_daemon_shutdown", "cycle_count": cycles, "results": results}
            elapsed = monotonic() - started
            if elapsed >= int(cfg["maximum_daemon_wall_clock_seconds"]): break
            state = inspect(cfg); now = _utc(wall_clock()); due = _utc(state["next_due_utc"])
            wait = max(0.0, (due - now).total_seconds()); remaining = int(cfg["maximum_daemon_wall_clock_seconds"]) - elapsed
            if wait > 0:
                if wait >= remaining: break
                waiter(wait)
                continue
            result = run_once(cfg, evaluation_time=now, monotonic=monotonic, wake_runner=wake_runner); results.append(result)
            if result["status"] == "maintenance_wake_daemon_not_due": continue
            if result["status"] != "maintenance_wake_daemon_lock_contention": cycles += 1
            if result["status"] != "maintenance_wake_daemon_continue": break
        status = ("maintenance_wake_daemon_cycle_limit" if cycles >= int(cfg["maximum_cycles"])
                  else results[-1]["status"] if results and results[-1]["status"] != "maintenance_wake_daemon_continue"
                  else "maintenance_wake_daemon_time_limit")
        return {"status": status, "cycle_count": cycles, "results": results}


class MaintenanceWakeOwner:
    """Daemon-local cooperative owner of one bounded wake cadence lifetime."""
    def __init__(self, adoption: Mapping[str, Any], *, runner: Callable[..., dict[str, Any]] = run_bounded,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self._adoption = validate_adoption(adoption); self._runner = runner; self._clock = clock
        self._stop = threading.Event(); self._thread: threading.Thread | None = None; self._guard = threading.Lock()
        self._health: dict[str, Any] = {"status": "configured" if self._adoption["enabled"] else "disabled", "read_only": True}
        if self._adoption["enabled"]: self._record("wake_adoption_configured")

    def health(self) -> dict[str, Any]:
        with self._guard: return dict(self._health)

    def _set(self, status: str, reason: str | None = None) -> None:
        with self._guard: self._health = {"status": status, "reason": reason, "read_only": True,
            "wake_config_digest": self._adoption.get("wake_config_digest")}

    def _record(self, event_type: str, **detail: Any) -> None:
        path = Path(str(self._adoption["evidence_path"])); prior = ZERO_DIGEST
        if path.exists() and path.stat().st_size:
            try: prior = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])["event_digest"]
            except (OSError, KeyError, json.JSONDecodeError) as exc: raise ValueError("wake_daemon_owner_evidence_corrupt") from exc
        row = {"schema_version": OWNER_EVENT_SCHEMA, "event_type": event_type,
               "adoption_config_digest": self._adoption["adoption_config_digest"],
               "wake_config_digest": self._adoption["wake_config_digest"], "prior_event_digest": prior,
               "recorded_at_utc": _utc_text(self._clock()), **detail}; row["event_digest"] = digest(row)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "ab") as handle: handle.write(canonical_bytes(row) + b"\n"); handle.flush(); os.fsync(handle.fileno())

    def start(self) -> bool:
        if not self._adoption["enabled"]: return False
        with self._guard:
            if self._thread is not None and self._thread.is_alive(): return False
        try:
            now = _utc_text(self._clock()); _verified_wake(self._adoption, now); _events(self._adoption)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self._set("degraded", str(exc)); self._record("wake_adoption_degraded", reason=str(exc)); return False
        self._stop.clear(); self._thread = threading.Thread(target=self._run, name="sentientosd-maintenance-wake", daemon=True); self._thread.start(); return True

    def _run(self) -> None:
        self._set("running"); self._record("wake_lifetime_started")
        try:
            result = self._runner(self._adoption, wall_clock=self._clock,
                waiter=lambda seconds: self._stop.wait(seconds), stop_requested=self._stop.is_set)
            status = str(result.get("status", "maintenance_wake_daemon_unknown_result")); self._record("wake_bounded_run_returned", cadence_status=status)
            projection = {"maintenance_wake_daemon_shutdown": "stopped", "maintenance_wake_daemon_cycle_limit": "stopped",
                          "maintenance_wake_daemon_time_limit": "stopped", "maintenance_wake_daemon_paused": "paused",
                          "maintenance_wake_daemon_lock_contention": "lock_contention",
                          "maintenance_wake_daemon_owner_lock_contention": "lock_contention"}.get(status, "degraded")
            self._set(projection, status)
        except Exception as exc:
            self._set("degraded", str(exc)); self._record("wake_adoption_degraded", reason=str(exc))
        self._record("wake_lifetime_stopped", reason=self.health().get("reason"))

    def stop(self) -> bool:
        if self._adoption["enabled"]: self._record("daemon_shutdown_requested")
        self._stop.set(); thread = self._thread
        if thread is None: return True
        thread.join(float(self._adoption["shutdown_timeout_seconds"]))
        if thread.is_alive():
            self._set("degraded", "bounded_shutdown_timeout"); self._record("wake_adoption_degraded", reason="bounded_shutdown_timeout"); return False
        return True


__all__ = ["ADOPTION_SCHEMA", "EVENT_SCHEMA", "OWNER_EVENT_SCHEMA", "MaintenanceWakeOwner",
           "validate_adoption", "load_adoption", "inspect", "run_once", "run_bounded", "canonical_bytes", "digest"]
