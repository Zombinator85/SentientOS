"""Operator-started, bounded cadence coordinator for the maintenance watchdog.

This module owns timing evidence only.  The bound watchdog remains the sole owner
of maintenance scanning, authority checks, transitions, and effects.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos import maintenance_loop_watchdog as watchdog

CONFIG_SCHEMA = "sentientos.maintenance_scheduler_config:v1"
EVENT_SCHEMA = "sentientos.maintenance_scheduler_event:v1"
ZERO_DIGEST = "sha256:" + "0" * 64
TERMINAL_WATCHDOG = frozenset({"paused"})
FAILURE_WATCHDOG = frozenset({"blocked"})


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("scheduler_timestamp_not_timezone_aware")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduler_timestamp_not_timezone_aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _external(path: str | Path, repo: Path, *, must_exist: bool = True) -> Path:
    raw = Path(path).expanduser()
    if raw.is_symlink() or any(p.is_symlink() for p in (raw, *raw.parents) if p.exists()):
        raise ValueError("scheduler_custody_symlink")
    resolved = raw.resolve(strict=must_exist)
    git = (repo / ".git").resolve(strict=True)
    if resolved == repo or repo in resolved.parents or resolved == git or git in resolved.parents:
        raise ValueError("scheduler_custody_inside_repository")
    return resolved


def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "watchdog_config_path", "watchdog_config_digest",
                "scheduler_state_root", "cadence_interval_seconds", "initial_run_posture",
                "schedule_anchor_utc", "maximum_cycles", "maximum_scheduler_wall_clock_seconds",
                "consecutive_failure_threshold", "stop_marker", "journal_path"}
    allowed = required | {"config_digest"}
    if set(value) - allowed:
        raise ValueError("unknown_scheduler_config_field")
    if not required.issubset(value):
        raise ValueError("missing_scheduler_config_field")
    if value["schema_version"] != CONFIG_SCHEMA or value["initial_run_posture"] not in {"immediate", "after_interval"}:
        raise ValueError("invalid_scheduler_config")
    for key in ("cadence_interval_seconds", "maximum_cycles", "maximum_scheduler_wall_clock_seconds", "consecutive_failure_threshold"):
        if type(value[key]) is not int or value[key] < 1:
            raise ValueError("invalid_scheduler_bound")
    _utc(str(value["schedule_anchor_utc"]))
    watchdog_path = Path(str(value["watchdog_config_path"])).expanduser()
    if watchdog_path.is_symlink() or not watchdog_path.is_file():
        raise ValueError("watchdog_config_file_invalid")
    bound = watchdog.load_config(watchdog_path)
    repo = Path(bound["repository_root"])
    state = _external(str(value["scheduler_state_root"]), repo)
    if not state.is_dir() or not stat.S_ISDIR(os.lstat(state).st_mode):
        raise ValueError("scheduler_state_root_invalid")
    journal = _external(str(value["journal_path"]), repo, must_exist=False)
    stop = _external(str(value["stop_marker"]), repo, must_exist=False)
    if journal.parent != state or stop.parent != state or journal == stop:
        raise ValueError("scheduler_state_path_collision")
    if journal.exists() and (journal.is_symlink() or not journal.is_file()):
        raise ValueError("scheduler_journal_invalid")
    if str(value["watchdog_config_digest"]) != bound["config_digest"]:
        raise ValueError("maintenance_scheduler_watchdog_config_drift")
    result = dict(value)
    result.update(watchdog_config_path=str(watchdog_path.resolve()), scheduler_state_root=str(state),
                  journal_path=str(journal), stop_marker=str(stop), schedule_anchor_utc=_utc_text(_utc(str(value["schedule_anchor_utc"]))))
    expected = digest({k: v for k, v in result.items() if k != "config_digest"})
    if value.get("config_digest") not in (None, "", expected):
        raise ValueError("scheduler_config_digest_mismatch")
    result["config_digest"] = expected
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("scheduler_config_file_invalid")
    return validate_config(json.loads(p.read_text(encoding="utf-8")))


def _events(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(str(cfg["journal_path"]))
    if not path.exists():
        return []
    prior = ZERO_DIGEST
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            item = json.loads(line)
            claimed = item.pop("event_digest")
            if item.get("schema_version") != EVENT_SCHEMA or item.get("scheduler_config_digest") != cfg["config_digest"] or item.get("prior_event_digest") != prior or digest(item) != claimed:
                raise ValueError("scheduler_journal_chain_invalid")
            item["event_digest"] = claimed
            _utc(str(item["recorded_at_utc"])); _utc(str(item["scheduled_due_utc"])); _utc(str(item["next_due_utc"]))
            prior = claimed; records.append(item)
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("scheduler_journal_malformed") from exc
    if records and records[-1]["event_type"] == "invocation_started":
        raise ValueError("maintenance_scheduler_recovery_ambiguous")
    return records


def _append(cfg: Mapping[str, Any], event: dict[str, Any], prior: str) -> dict[str, Any]:
    complete = {"schema_version": EVENT_SCHEMA, "scheduler_config_digest": cfg["config_digest"],
                "watchdog_config_digest": cfg["watchdog_config_digest"], "prior_event_digest": prior, **event}
    complete["event_digest"] = digest(complete)
    path = Path(str(cfg["journal_path"]))
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "ab") as handle:
        handle.write(canonical_bytes(complete) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    return complete


def _next_due(cfg: Mapping[str, Any], events: list[dict[str, Any]]) -> tuple[int, datetime, int]:
    completed = [e for e in events if e["event_type"] == "cycle_completed"]
    failures = int(completed[-1].get("consecutive_failures", 0)) if completed else 0
    if completed:
        return int(completed[-1]["cycle_ordinal"]) + 1, _utc(completed[-1]["next_due_utc"]), failures
    anchor = _utc(str(cfg["schedule_anchor_utc"]))
    due = anchor if cfg["initial_run_posture"] == "immediate" else anchor + timedelta(seconds=int(cfg["cadence_interval_seconds"]))
    return 1, due, failures


def _verified_watchdog(cfg: Mapping[str, Any]) -> dict[str, Any]:
    current = cast(dict[str, Any], watchdog.load_config(str(cfg["watchdog_config_path"])))
    if current["config_digest"] != cfg["watchdog_config_digest"]:
        raise ValueError("maintenance_scheduler_watchdog_config_drift")
    return current


def inspect(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_config(config); events = _events(cfg); ordinal, due, failures = _next_due(cfg, events)
    return {"schema_version": "sentientos.maintenance_scheduler_inspection:v1", "status": "maintenance_scheduler_state_ready",
            "scheduler_config_digest": cfg["config_digest"], "event_count": len(events), "next_cycle_ordinal": ordinal,
            "next_due_utc": _utc_text(due), "consecutive_failures": failures,
            "last_event_digest": events[-1]["event_digest"] if events else ZERO_DIGEST}


def doctor(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_config(config); _verified_watchdog(cfg); state = inspect(cfg)
    return {"schema_version": "sentientos.maintenance_scheduler_doctor:v1", "status": "maintenance_scheduler_config_ready",
            "scheduler_config_digest": cfg["config_digest"], "watchdog_config_digest": cfg["watchdog_config_digest"], "state": state}


def _locked_run_once(cfg: Mapping[str, Any], now: datetime, monotonic: Callable[[], float], runner: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    events = _events(cfg); ordinal, due, failures = _next_due(cfg, events); prior = events[-1]["event_digest"] if events else ZERO_DIGEST
    common = {"cycle_ordinal": ordinal, "scheduled_due_utc": _utc_text(due), "recorded_at_utc": _utc_text(now)}
    if Path(str(cfg["stop_marker"])).exists():
        event = _append(cfg, {**common, "event_type": "scheduler_stopped", "due": now >= due, "watchdog_invoked": False,
            "watchdog_status": None, "watchdog_result_digest": None, "duration_seconds": 0.0, "disposition": "stopped",
            "next_due_utc": _utc_text(due), "consecutive_failures": failures, "reason": "scheduler_stop_marker"}, prior)
        return {"status": "maintenance_scheduler_stopped", "event": event}
    if now < due:
        return {"status": "maintenance_scheduler_not_due", "cycle_ordinal": ordinal, "next_due_utc": _utc_text(due)}
    bound = _verified_watchdog(cfg)
    started = _append(cfg, {**common, "event_type": "invocation_started", "due": True, "watchdog_invoked": False,
        "watchdog_status": None, "watchdog_result_digest": None, "duration_seconds": 0.0, "disposition": "invocation_pending",
        "next_due_utc": _utc_text(due), "consecutive_failures": failures, "reason": None}, prior)
    began = monotonic(); result = runner(bound, evaluation_time=_utc_text(now)); duration = max(0.0, monotonic() - began)
    status = str(result.get("status", "blocked")); result_digest = watchdog.digest(result)
    failures = failures + 1 if status in FAILURE_WATCHDOG else 0
    # Missed intervals collapse to one invocation.  The new anchor is the first
    # cadence instant strictly after actual invocation time.
    interval = timedelta(seconds=int(cfg["cadence_interval_seconds"])); next_due = due + interval
    while next_due <= now: next_due += interval
    disposition = "stop" if status in TERMINAL_WATCHDOG else "failure_threshold" if failures >= int(cfg["consecutive_failure_threshold"]) else "continue"
    complete = _append(cfg, {**common, "event_type": "cycle_completed", "recorded_at_utc": _utc_text(now), "due": True,
        "watchdog_invoked": True, "watchdog_status": status, "watchdog_result_digest": result_digest,
        "duration_seconds": duration, "disposition": disposition, "next_due_utc": _utc_text(next_due),
        "consecutive_failures": failures, "reason": result.get("reason")}, started["event_digest"])
    return {"status": "maintenance_scheduler_" + disposition, "watchdog_result": result, "event": complete}


def run_once(config: Mapping[str, Any], *, evaluation_time: str, monotonic: Callable[[], float] = time.monotonic,
             watchdog_runner: Callable[..., dict[str, Any]] = watchdog.run_bounded) -> dict[str, Any]:
    cfg = validate_config(config); now = _utc(evaluation_time); lock_path = Path(cfg["scheduler_state_root"]) / "scheduler.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("r+") as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return {"status": "maintenance_scheduler_lock_busy"}
        return _locked_run_once(cfg, now, monotonic, watchdog_runner)


def run_bounded(config: Mapping[str, Any], *, wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                monotonic: Callable[[], float] = time.monotonic, sleeper: Callable[[float], None] = time.sleep,
                watchdog_runner: Callable[..., dict[str, Any]] = watchdog.run_bounded) -> dict[str, Any]:
    cfg = validate_config(config); start = monotonic(); cycles = 0; results = []
    while cycles < int(cfg["maximum_cycles"]):
        elapsed = monotonic() - start
        if elapsed >= int(cfg["maximum_scheduler_wall_clock_seconds"]): break
        state = inspect(cfg); now = _utc(_utc_text(wall_clock())); due = _utc(state["next_due_utc"])
        if Path(cfg["stop_marker"]).exists():
            result = run_once(cfg, evaluation_time=_utc_text(now), monotonic=monotonic, watchdog_runner=watchdog_runner); results.append(result); break
        wait = max(0.0, (due - now).total_seconds())
        remaining = int(cfg["maximum_scheduler_wall_clock_seconds"]) - elapsed
        if wait > 0:
            if wait >= remaining: break
            sleeper(wait); continue
        result = run_once(cfg, evaluation_time=_utc_text(now), monotonic=monotonic, watchdog_runner=watchdog_runner); results.append(result)
        if result["status"] == "maintenance_scheduler_lock_busy": break
        if result["status"] != "maintenance_scheduler_not_due": cycles += 1
        if result["status"] in {"maintenance_scheduler_stop", "maintenance_scheduler_stopped", "maintenance_scheduler_failure_threshold"}: break
    status = results[-1]["status"] if results and results[-1]["status"] != "maintenance_scheduler_continue" else ("maintenance_scheduler_cycle_limit" if cycles >= int(cfg["maximum_cycles"]) else "maintenance_scheduler_time_limit")
    return {"status": status, "cycle_count": cycles, "results": results}


__all__ = ["CONFIG_SCHEMA", "EVENT_SCHEMA", "validate_config", "load_config", "doctor", "inspect", "run_once", "run_bounded", "canonical_bytes", "digest"]
