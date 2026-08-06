"""Bounded external coordinator for the repository maintenance loop.

The watchdog deliberately owns no implementation, validation, Git, or publication
logic.  A tick selects one transition from durable observations and dispatches it
to a caller supplied canonical component.  This makes the policy testable without
turning SentientOS into a scheduler or granting the runtime new authority.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

CONFIG_SCHEMA = "sentientos.maintenance_watchdog_config:v1"
SCAN_SCHEMA = "sentientos.maintenance_watchdog_scan:v1"
DECISION_SCHEMA = "sentientos.maintenance_watchdog_decision:v1"
TICK_SCHEMA = "sentientos.maintenance_watchdog_tick_result:v1"
BRIEF_SCHEMA = "sentientos.maintenance_implementation_brief:v1"
BASE_CURSOR_SCHEMA = "sentientos.maintenance_base_cursor_event:v1"
CONTROL_SCHEMA = "sentientos.maintenance_watchdog_control_event:v1"
ZERO_DIGEST = "sha256:" + "0" * 64

PRIORITY = (
    "paused", "integrity_failure", "ambiguous_active_tasks", "recover",
    "observe_process", "close_task", "publish", "commit_enqueue", "validate",
    "prepare_implementation", "admit_candidate", "select_candidate", "idle",
)
TERMINAL = frozenset({"idle", "waiting", "paused", "blocked"})


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _closed(value: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    if set(value) - allowed:
        raise ValueError("unknown_config_field")
    if not required.issubset(value):
        raise ValueError("missing_config_field")


def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "repository_root", "state_root", "workspace_root",
                "scratch_root", "candidate_inbox_roots", "standing_grant",
                "selector_policy", "foreman_policy", "validation_policy",
                "landing_policy", "maximum_active_tasks", "maximum_actions",
                "maximum_wall_clock_seconds", "publication_retry_backoff_seconds",
                "base_sha", "tracked_base_ref"}
    allowed = required | {"stop_marker", "control_journal", "base_cursor_journal",
                          "component_commands", "config_digest"}
    _closed(value, allowed, required)
    if value["schema_version"] != CONFIG_SCHEMA or int(value["maximum_active_tasks"]) != 1:
        raise ValueError("invalid_watchdog_config")
    if int(value["maximum_actions"]) < 1 or int(value["maximum_wall_clock_seconds"]) < 1:
        raise ValueError("invalid_watchdog_bounds")
    if int(value["publication_retry_backoff_seconds"]) < 0:
        raise ValueError("invalid_publication_backoff")
    result = dict(value)
    repo = Path(str(value["repository_root"])).resolve(strict=True)
    git = (repo / ".git").resolve(strict=True)
    roots = [Path(str(value[k])) for k in ("state_root", "workspace_root", "scratch_root")]
    roots += [Path(str(p)) for p in value["candidate_inbox_roots"]]
    for root in roots:
        if root.is_symlink():
            raise ValueError("custody_root_symlink")
        resolved = root.resolve(strict=True)
        if resolved == repo or repo in resolved.parents or resolved == git or git in resolved.parents:
            raise ValueError("custody_root_inside_repository")
        if not stat.S_ISDIR(os.lstat(root).st_mode):
            raise ValueError("custody_root_not_directory")
    result["repository_root"] = str(repo)
    result["candidate_inbox_roots"] = sorted(str(Path(p).resolve()) for p in value["candidate_inbox_roots"])
    unsigned = {k: v for k, v in result.items() if k != "config_digest"}
    expected = digest(unsigned)
    if value.get("config_digest") not in (None, "", expected):
        raise ValueError("config_digest_mismatch")
    result["config_digest"] = expected
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")))


def _json_files(root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(root.glob("*.json"), key=lambda p: p.name):
        if path.is_symlink() or not path.is_file():
            records.append({"path": str(path), "status": "integrity_failure"})
            continue
        raw = path.read_bytes()
        try:
            payload = json.loads(raw)
            records.append({"path": str(path), "status": "ready", "digest": "sha256:" + hashlib.sha256(raw).hexdigest(), "payload": payload})
        except (ValueError, UnicodeDecodeError):
            records.append({"path": str(path), "status": "integrity_failure", "digest": "sha256:" + hashlib.sha256(raw).hexdigest()})
    return records


def scan(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    cfg = validate_config(config)
    state = Path(cfg["state_root"])
    candidates = [r for root in cfg["candidate_inbox_roots"] for r in _json_files(Path(root))]
    observations: dict[str, Any] = {}
    for name in ("active_tasks", "interrupted_operations", "live_processes", "closures",
                 "publication_queue", "commit_ready", "validation_ready", "implementation_ready",
                 "admission_ready", "selection_ready"):
        p = state / (name + ".json")
        observations[name] = json.loads(p.read_text()) if p.exists() and not p.is_symlink() else []
    control = inspect_control(cfg)
    stop = Path(cfg.get("stop_marker") or state / "STOP")
    result = {"schema_version": SCAN_SCHEMA, "config_digest": cfg["config_digest"],
              "evaluation_time": evaluation_time, "stop_marker_present": stop.exists(),
              "control": control, "candidates": candidates, "observations": observations}
    result["scan_digest"] = digest(result)
    return result


def decide(config: Mapping[str, Any], scan_result: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_config(config)
    if scan_result.get("config_digest") != cfg["config_digest"]:
        raise ValueError("scan_config_mismatch")
    obs = scan_result.get("observations", {})
    active = obs.get("active_tasks") or []
    candidate_bad = any(x.get("status") == "integrity_failure" for x in scan_result.get("candidates", []))
    checks = {
        "paused": bool(scan_result.get("stop_marker_present") or scan_result.get("control", {}).get("paused")),
        "integrity_failure": candidate_bad or bool(obs.get("integrity_failure")),
        "ambiguous_active_tasks": len(active) > 1,
        "recover": bool(obs.get("interrupted_operations")), "observe_process": bool(obs.get("live_processes")),
        "close_task": bool(obs.get("closures")), "publish": bool(obs.get("publication_queue")),
        "commit_enqueue": bool(obs.get("commit_ready")), "validate": bool(obs.get("validation_ready")),
        "prepare_implementation": bool(obs.get("implementation_ready")), "admit_candidate": bool(obs.get("admission_ready")),
        "select_candidate": bool(obs.get("selection_ready") or (not active and scan_result.get("candidates"))), "idle": True,
    }
    transition = next(item for item in PRIORITY if checks[item])
    status = "paused" if transition == "paused" else ("blocked" if transition in {"integrity_failure", "ambiguous_active_tasks"} else ("idle" if transition == "idle" else "action_ready"))
    result = {"schema_version": DECISION_SCHEMA, "config_digest": cfg["config_digest"],
              "scan_digest": scan_result.get("scan_digest"), "transition": transition, "status": status}
    result["decision_digest"] = digest(result)
    return result


def build_implementation_brief(candidate: Mapping[str, Any], admission: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    brief = {"schema_version": BRIEF_SCHEMA, "candidate_id": candidate.get("candidate_id"),
             "candidate_revision_digest": candidate.get("candidate_revision_digest"),
             "objective": candidate.get("objective"), "subject_paths": sorted(candidate.get("declared_subject_paths", [])),
             "validation_expectations": sorted(candidate.get("declared_validation_expectations", [])),
             "admission_digest": admission.get("admission_digest"), "base_sha": config.get("base_sha")}
    brief["brief_digest"] = digest(brief)
    return brief


def _append_chain(path: Path, schema: str, event_type: str, evaluation_time: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    previous = events[-1]["event_digest"] if events else ZERO_DIGEST
    event = {"schema_version": schema, "sequence": len(events) + 1, "event_type": event_type,
             "recorded_at": evaluation_time, "previous_event_digest": previous, "payload": dict(payload)}
    event["event_digest"] = digest(event)
    with path.open("ab") as handle:
        handle.write(canonical_json_bytes(event) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    return event


def control(config: Mapping[str, Any], action: str, *, evaluation_time: str) -> dict[str, Any]:
    if action not in {"pause", "resume"}: raise ValueError("invalid_control_action")
    cfg = validate_config(config)
    return _append_chain(Path(cfg.get("control_journal") or Path(cfg["state_root"]) / "watchdog_control.jsonl"), CONTROL_SCHEMA, action, evaluation_time, {})


def inspect_control(config: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(config.get("control_journal") or Path(str(config["state_root"])) / "watchdog_control.jsonl")
    events = [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
    previous = ZERO_DIGEST
    for event in events:
        supplied = event.get("event_digest"); unsigned = {k: v for k, v in event.items() if k != "event_digest"}
        if event.get("previous_event_digest") != previous or supplied != digest(unsigned):
            return {"status": "integrity_failure", "paused": True, "events": events}
        previous = supplied
    return {"status": "ready", "paused": bool(events and events[-1]["event_type"] == "pause"), "events": events}


def tick(config: Mapping[str, Any], *, evaluation_time: str,
         handlers: Mapping[str, Callable[[Mapping[str, Any], Mapping[str, Any]], Any]] | None = None) -> dict[str, Any]:
    cfg = validate_config(config); state = Path(cfg["state_root"]); lock_path = state / "watchdog.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("r+") as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"schema_version": TICK_SCHEMA, "status": "waiting", "transition": "global_lock_busy"}
        scanned = scan(cfg, evaluation_time=evaluation_time); decision = decide(cfg, scanned)
        transition = decision["transition"]
        if decision["status"] != "action_ready": effect = {"status": decision["status"]}
        else:
            stop = Path(cfg.get("stop_marker") or state / "STOP")
            if stop.exists(): transition, effect = "paused", {"status": "paused"}
            else:
                handler = (handlers or {}).get(transition)
                effect = handler(cfg, scanned) if handler else {"status": "waiting", "reason": "canonical_component_not_configured"}
        result = {"schema_version": TICK_SCHEMA, "config_digest": cfg["config_digest"], "scan_digest": scanned["scan_digest"],
                  "decision_digest": decision["decision_digest"], "transition": transition, "effect_result": effect,
                  "status": effect.get("status", "completed") if isinstance(effect, Mapping) else "completed"}
        result["tick_digest"] = digest(result)
        _append_chain(state / "watchdog_ticks.jsonl", TICK_SCHEMA, transition, evaluation_time, result)
        return result


def run_bounded(config: Mapping[str, Any], *, evaluation_time: str, handlers: Mapping[str, Callable[[Mapping[str, Any], Mapping[str, Any]], Any]] | None = None) -> dict[str, Any]:
    cfg = validate_config(config); start = time.monotonic(); results = []
    for _ in range(int(cfg["maximum_actions"])):
        if time.monotonic() - start >= int(cfg["maximum_wall_clock_seconds"]): break
        result = tick(cfg, evaluation_time=evaluation_time, handlers=handlers); results.append(result)
        if result["status"] in TERMINAL or result["transition"] in {"idle", "paused"}: break
    return {"status": results[-1]["status"] if results else "time_limit", "ticks": results, "action_count": len(results)}


__all__ = ["validate_config", "load_config", "scan", "decide", "tick", "run_bounded", "control",
           "inspect_control", "build_implementation_brief", "canonical_json_bytes", "digest"]
