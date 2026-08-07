"""Bounded, external coordinator for collector and watchdog production APIs.

This module owns only cycle exclusion and cycle receipts.  Component locks and
all maintenance authority remain owned by the collector and watchdog.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_candidate_collector as collector
from sentientos import maintenance_loop_activation as activation
from sentientos import maintenance_loop_watchdog as watchdog

CONFIG_SCHEMA = "sentientos.maintenance_autonomy_cycle_config:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_autonomy_cycle_receipt:v1"
ZERO_DIGEST = "sha256:" + "0" * 64
TERMINAL_STATUSES = frozenset({"autonomy_cycle_idle", "autonomy_cycle_completed", "autonomy_cycle_continuing", "autonomy_cycle_waiting", "autonomy_cycle_paused", "autonomy_cycle_blocked"})
_REQUIRED = {"schema_version", "repository_identity", "repository_root", "base_sha",
    "activation_profile_bundle_manifest_path", "collector_configuration_path",
    "watchdog_configuration_path", "external_cycle_state_root", "cycle_receipt_journal_path",
    "stop_marker", "maximum_cycle_wall_clock_seconds", "maximum_collector_invocations_per_cycle",
    "maximum_watchdog_invocations_per_cycle", "maximum_candidates_collected_per_cycle",
    "remote_readiness_probe_required", "evaluation_time_required"}
_ALLOWED = _REQUIRED | {"config_digest"}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _external_private_directory(value: object, repo: Path) -> Path:
    raw = Path(str(value)).absolute()
    if raw.is_symlink() or not raw.exists() or not stat.S_ISDIR(os.lstat(raw).st_mode):
        raise ValueError("cycle_state_root_unsafe")
    resolved = raw.resolve(strict=True)
    if resolved == repo or repo in resolved.parents or resolved == (repo / ".git").resolve() or (repo / ".git").resolve() in resolved.parents:
        raise ValueError("cycle_state_root_inside_repository")
    if os.name == "posix" and stat.S_IMODE(os.lstat(raw).st_mode) != 0o700:
        raise ValueError("cycle_state_root_permissions_unsafe")
    return resolved


def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("maximum_collector_invocations_per_cycle", "maximum_watchdog_invocations_per_cycle", "maximum_candidates_collected_per_cycle"):
        if key in value and (value[key] != 1 or isinstance(value[key], bool)):
            raise ValueError("unsupported_bound:" + key)
    if set(value) - _ALLOWED or not _REQUIRED.issubset(value):
        raise ValueError("invalid_closed_config")
    if value["schema_version"] != CONFIG_SCHEMA:
        raise ValueError("invalid_config_schema")
    if value["evaluation_time_required"] is not True or not isinstance(value["remote_readiness_probe_required"], bool):
        raise ValueError("invalid_explicit_boolean")
    if not isinstance(value["maximum_cycle_wall_clock_seconds"], int) or isinstance(value["maximum_cycle_wall_clock_seconds"], bool) or value["maximum_cycle_wall_clock_seconds"] < 1:
        raise ValueError("invalid_cycle_wall_clock_bound")
    repo_raw = Path(str(value["repository_root"]))
    if repo_raw.is_symlink():
        raise ValueError("repository_root_unsafe")
    repo = repo_raw.resolve(strict=True)
    if not (repo / ".git").exists():
        raise ValueError("repository_identity_unverifiable")
    result = dict(value); result["repository_root"] = str(repo)
    state = _external_private_directory(value["external_cycle_state_root"], repo)
    result["external_cycle_state_root"] = str(state)
    receipt = Path(str(value["cycle_receipt_journal_path"])).absolute()
    stop = Path(str(value["stop_marker"])).absolute()
    for path, label in ((receipt, "cycle_receipt"), (stop, "stop_marker")):
        if path.is_symlink() or path.parent.resolve(strict=True) != state:
            raise ValueError(label + "_custody_invalid")
    result["cycle_receipt_journal_path"] = str(receipt); result["stop_marker"] = str(stop)
    for key in ("activation_profile_bundle_manifest_path", "collector_configuration_path", "watchdog_configuration_path"):
        raw = Path(str(value[key]))
        if raw.is_symlink() or not raw.is_file():
            raise ValueError(key + "_unsafe")
        result[key] = str(raw.resolve(strict=True))
    expected = digest({k: v for k, v in result.items() if k != "config_digest"})
    if value.get("config_digest") not in (None, "", expected):
        raise ValueError("config_digest_mismatch")
    result["config_digest"] = expected
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    raw = Path(path)
    if raw.is_symlink() or not raw.is_file():
        raise ValueError("config_path_unsafe")
    value = json.loads(raw.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("config_not_object")
    return validate_config(value)


def _component_configs(cfg: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cc = collector.load_config(cfg["collector_configuration_path"])
    wc = watchdog.load_config(cfg["watchdog_configuration_path"])
    inspected = profiles.inspect_profile_bundle(cfg["activation_profile_bundle_manifest_path"], "9999-12-31T23:59:59Z")
    manifest = inspected["manifest"]
    agreements = [
        cfg["repository_identity"] == cc["repository_identity"] == manifest["repository_identity"],
        Path(cfg["repository_root"]) == Path(cc["repository_root"]) == Path(wc["repository_root"]) == Path(manifest["repository_root"]),
        cfg["base_sha"] == cc["base_sha"] == wc["base_sha"] == manifest["base_sha"],
        Path(cfg["activation_profile_bundle_manifest_path"]) == Path(cc["activation_profile_bundle_manifest_path"]),
        Path(cfg["collector_configuration_path"]) != Path(cfg["watchdog_configuration_path"]),
        Path(cc["watchdog_configuration_path"]) == Path(cfg["watchdog_configuration_path"]),
        Path(cc["maintenance_candidate_inbox"]) == Path(manifest["inbox_root"]),
        Path(cc["maintenance_candidate_inbox"]) in [Path(x) for x in wc["candidate_inbox_roots"]],
        Path(wc["state_root"]) == Path(manifest["state_root"]),
        wc["tracked_base_ref"] == manifest["tracked_base_ref"],
        Path(cfg["stop_marker"]) == Path(cc.get("stop_marker", "")) == Path(wc.get("stop_marker", "")),
    ]
    if not all(agreements):
        raise ValueError("component_configuration_disagreement")
    return cc, wc, manifest


def doctor(config: Mapping[str, Any], *, evaluation_time: str, _lock_already_owned: bool = False) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        cfg = validate_config(config); cc, wc, _ = _component_configs(cfg)
        cd = collector.doctor(cc, evaluation_time=evaluation_time)
        if cd.get("status") != "collector_ready": reasons.append("collector_not_ready")
        ad = activation.doctor_live(cfg["watchdog_configuration_path"], evaluation_time=evaluation_time,
                                    probe_remote=cfg["remote_readiness_probe_required"])
        if ad.get("status") != "activation_ready": reasons.append("activation_not_ready")
        scanned = watchdog.scan(wc, evaluation_time=evaluation_time); decision = watchdog.decide(wc, scanned)
        if decision.get("transition") in {"integrity_failure", "ambiguous_active_tasks"}: reasons.append(str(decision["transition"]))
        if not _lock_already_owned:
            lock = _cycle_lock(cfg, nonblocking=True); lock.close()
        _ = collector.collect_once, watchdog.run_bounded
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        reasons.append(str(exc))
        cfg = dict(config)
    return {"schema_version": "sentientos.maintenance_autonomy_cycle_doctor:v1",
            "status": "autonomy_cycle_ready" if not reasons else "autonomy_cycle_blocked",
            "config_digest": cfg.get("config_digest"), "reason_codes": sorted(set(reasons))}


def _cycle_lock(cfg: Mapping[str, Any], *, nonblocking: bool) -> Any:
    handle = (Path(str(cfg["external_cycle_state_root"])) / "autonomy_cycle.lock").open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
    except BlockingIOError:
        handle.close(); raise ValueError("cycle_global_lock_unavailable")
    return handle


def _receipts(cfg: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    path = Path(str(cfg["cycle_receipt_journal_path"])); rows: list[dict[str, Any]] = []; reasons: list[str] = []
    if not path.exists(): return rows, reasons
    try:
        for line in path.read_bytes().splitlines():
            row = json.loads(line); body = {k: v for k, v in row.items() if k != "receipt_digest"}
            if row.get("schema_version") != RECEIPT_SCHEMA or row.get("sequence") != len(rows) + 1 or row.get("predecessor_receipt_digest") != (rows[-1]["receipt_digest"] if rows else ZERO_DIGEST) or row.get("receipt_digest") != digest(body):
                reasons.append("cycle_receipt_chain_invalid"); break
            rows.append(row)
    except (OSError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError): reasons.append("cycle_receipt_truncated_or_invalid")
    return rows, reasons


def inspect_receipts(config: Mapping[str, Any]) -> dict[str, Any]:
    try:
        cfg = validate_config(config); rows, reasons = _receipts(cfg)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        rows, reasons = [], [str(exc)]
    return {"schema_version": "sentientos.maintenance_autonomy_cycle_receipt_inspection:v1", "status": "receipts_ready" if not reasons else "receipts_blocked", "receipt_count": len(rows), "head_receipt_digest": rows[-1]["receipt_digest"] if rows else ZERO_DIGEST, "reason_codes": reasons, "receipts": rows}


def _stop(cfg: Mapping[str, Any], stage: str, observations: list[dict[str, Any]], order: list[str]) -> bool:
    order.append(stage); present = Path(str(cfg["stop_marker"])).exists(); observations.append({"stage": stage, "present": present}); return present


def _map_watchdog(result: Mapping[str, Any], *, had_candidate: bool) -> str:
    status = result.get("status")
    if status == "paused": return "autonomy_cycle_paused"
    if status == "waiting" or status == "time_limit": return "autonomy_cycle_waiting"
    if status == "blocked": return "autonomy_cycle_blocked"
    ticks = result.get("ticks", [])
    if status == "idle":
        return "autonomy_cycle_completed" if had_candidate and any(x.get("transition") == "close_task" and x.get("status") == "completed" for x in ticks) else "autonomy_cycle_idle"
    return "autonomy_cycle_continuing" if status == "completed" else "autonomy_cycle_blocked"


def cycle_once(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    cfg = validate_config(config); order: list[str] = []; stops: list[dict[str, Any]] = []
    status = ""
    effects = {"collector_invocations": 0, "watchdog_invocations": 0, "candidates_collected": 0}
    collection: dict[str, Any] | None = None; wd_result: dict[str, Any] | None = None
    try: lock = _cycle_lock(cfg, nonblocking=True)
    except ValueError as exc: return {"status": "autonomy_cycle_blocked", "reason_codes": [str(exc)], "effect_counts": effects}
    with lock:
        readiness = doctor(cfg, evaluation_time=evaluation_time, _lock_already_owned=True)
        if readiness["status"] != "autonomy_cycle_ready": status, reason = "autonomy_cycle_blocked", readiness["reason_codes"]
        else:
            cc, wc, _ = _component_configs(cfg); reason = []
            if _stop(cfg, "integrity_and_stop", stops, order): status = "autonomy_cycle_paused"
            else:
                scanned = watchdog.scan(wc, evaluation_time=evaluation_time); decision = watchdog.decide(wc, scanned); transition = decision["transition"]
                if transition in {"integrity_failure", "ambiguous_active_tasks"}: status, reason = "autonomy_cycle_blocked", [transition]
                elif transition == "paused": status = "autonomy_cycle_paused"
                else:
                    pending = transition == "select_candidate"
                    active = transition not in {"idle", "select_candidate"}
                    had_candidate = pending or active
                    if active or pending:
                        order.append("existing_active_task" if active else "existing_inbox_candidate")
                    else:
                        if _stop(cfg, "before_collection", stops, order): status = "autonomy_cycle_paused"
                        else:
                            collection = collector.collect_once(cc, evaluation_time=evaluation_time); effects["collector_invocations"] = 1
                            effects["candidates_collected"] = int(collection.get("candidates_written", 0))
                            if effects["candidates_collected"] > 1 or int(collection.get("candidates_reused", 0)) > 1: status, reason = "autonomy_cycle_blocked", ["collector_bound_exceeded"]
                            elif collection.get("status") != "collection_ready": status, reason = "autonomy_cycle_blocked", ["collection_not_ready"]
                            else: had_candidate = bool(effects["candidates_collected"] or collection.get("candidates_reused")); status = ""
                    if status == "":
                        if not had_candidate: status = "autonomy_cycle_idle"
                        elif _stop(cfg, "before_watchdog", stops, order): status = "autonomy_cycle_paused"
                        else:
                            order.append("watchdog_execution"); wd_result = watchdog.run_bounded(wc, evaluation_time=evaluation_time); effects["watchdog_invocations"] = 1
                            status = _map_watchdog(wd_result, had_candidate=had_candidate)
        order.append("terminal_inspection")
        rows, chain_reasons = _receipts(cfg)
        if chain_reasons:
            return {"schema_version": "sentientos.maintenance_autonomy_cycle_result:v1",
                    "status": "autonomy_cycle_blocked", "reason_codes": chain_reasons,
                    "effect_counts": effects, "collector_result": collection,
                    "watchdog_result": wd_result, "receipt": None}
        body = {"schema_version": RECEIPT_SCHEMA, "sequence": len(rows) + 1, "predecessor_receipt_digest": rows[-1]["receipt_digest"] if rows else ZERO_DIGEST,
            "cycle_config_digest": cfg["config_digest"], "evaluation_time": evaluation_time, "repository_identity": cfg["repository_identity"], "base_sha_before": cfg["base_sha"],
            "collector_config_digest": collector.load_config(cfg["collector_configuration_path"])["config_digest"], "collector_result_digest": digest(collection) if collection is not None else None,
            "collection_skipped": effects["collector_invocations"] == 0, "collection_skip_reason": "prior_custody" if effects["collector_invocations"] == 0 else None,
            "collected_candidates": [{"candidate_id": x.get("canonical_candidate_id"), "revision": x.get("canonical_candidate_revision_digest")} for x in (collection or {}).get("scan", {}).get("candidate_bindings", [])],
            "watchdog_config_digest": watchdog.load_config(cfg["watchdog_configuration_path"])["config_digest"], "watchdog_result_digest": digest(wd_result) if wd_result is not None else None,
            "terminal_status": status, "stop_observations": stops, "stage_order": order, "effect_counts": effects}
        receipt = dict(body); receipt["receipt_digest"] = digest(body)
        path = Path(cfg["cycle_receipt_journal_path"]); fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "ab") as handle: handle.write(canonical_json_bytes(receipt) + b"\n"); handle.flush(); os.fsync(handle.fileno())
        return {"schema_version": "sentientos.maintenance_autonomy_cycle_result:v1", "status": status, "reason_codes": reason, "effect_counts": effects, "collector_result": collection, "watchdog_result": wd_result, "receipt": receipt}


def inspect(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    cfg = validate_config(config); cc, wc, _ = _component_configs(cfg); scanned = watchdog.scan(wc, evaluation_time=evaluation_time); decision = watchdog.decide(wc, scanned); receipts = inspect_receipts(cfg)
    transition = decision["transition"]
    next_action = "block" if transition in {"integrity_failure", "ambiguous_active_tasks"} else "pause" if transition == "paused" else "collect" if transition == "idle" else "process_existing_candidate" if transition == "select_candidate" else "continue_existing_work"
    active = scanned["observations"]["active_tasks"]
    return {"schema_version": "sentientos.maintenance_autonomy_cycle_inspection:v1", "status": "inspection_ready" if receipts["status"] == "receipts_ready" else "inspection_blocked", "config_digest": cfg["config_digest"], "last_cycle_status": receipts["receipts"][-1]["terminal_status"] if receipts["receipts"] else None, "collector_status": collector.inspect(cc, evaluation_time=evaluation_time)["status"], "watchdog_transition": transition, "pending_candidate_count": len(scanned["candidates"]), "active_task_identity": active[0].get("task_id") if len(active) == 1 else None, "cycle_receipt_digest": receipts["head_receipt_digest"], "next_action": next_action}


def print_run_command(config_path: str | Path, *, evaluation_time: str, python_executable: str = sys.executable) -> dict[str, Any]:
    return {"schema_version": "sentientos.maintenance_autonomy_cycle_run_command:v1", "status": "run_command_ready", "argv": [python_executable, str(Path(__file__).parents[1] / "scripts" / "maintenance_autonomy_cycle.py"), "--config", str(Path(config_path).resolve()), "--evaluation-time", evaluation_time, "cycle-once"], "shell": False, "scheduler_installation": False}


__all__ = ["CONFIG_SCHEMA", "validate_config", "load_config", "doctor", "cycle_once", "inspect", "inspect_receipts", "print_run_command", "canonical_json_bytes", "digest"]
