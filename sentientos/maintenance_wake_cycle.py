"""Recovery-first, bounded coordinator for maintenance probe and autonomy APIs."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

from sentientos import maintenance_autonomy_cycle as autonomy
from sentientos import maintenance_candidate_collector as collector
from sentientos import maintenance_health_probe as health

CONFIG_SCHEMA = "sentientos.maintenance_wake_cycle_config:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_wake_cycle_receipt:v1"
ZERO_DIGEST = "sha256:" + "0" * 64
_REQUIRED = {"schema_version", "repository_identity", "repository_root", "base_sha",
    "health_probe_configuration_path", "autonomy_cycle_configuration_path",
    "external_wake_state_root", "wake_receipt_journal_path", "stop_marker",
    "evaluation_time"}
_ALLOWED = _REQUIRED | {"config_digest"}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) - _ALLOWED or not _REQUIRED.issubset(value):
        raise ValueError("invalid_closed_config")
    if value["schema_version"] != CONFIG_SCHEMA or not isinstance(value["evaluation_time"], str) or not value["evaluation_time"]:
        raise ValueError("invalid_config_value")
    repo_raw = Path(str(value["repository_root"]))
    if repo_raw.is_symlink() or not repo_raw.is_dir():
        raise ValueError("repository_root_unsafe")
    repo = repo_raw.resolve(strict=True)
    state_raw = Path(str(value["external_wake_state_root"])).absolute()
    if state_raw.is_symlink() or not state_raw.exists() or not stat.S_ISDIR(os.lstat(state_raw).st_mode):
        raise ValueError("wake_state_root_unsafe")
    state = state_raw.resolve(strict=True)
    if state == repo or repo in state.parents or (os.name == "posix" and stat.S_IMODE(os.lstat(state_raw).st_mode) != 0o700):
        raise ValueError("wake_state_root_custody_invalid")
    result = dict(value); result["repository_root"] = str(repo); result["external_wake_state_root"] = str(state)
    for key in ("health_probe_configuration_path", "autonomy_cycle_configuration_path"):
        path = Path(str(value[key]))
        if path.is_symlink() or not path.is_file(): raise ValueError(key + "_unsafe")
        result[key] = str(path.resolve(strict=True))
    for key in ("wake_receipt_journal_path", "stop_marker"):
        path = Path(str(value[key])).absolute()
        if path.is_symlink() or path.parent.resolve(strict=True) != state: raise ValueError(key + "_custody_invalid")
        result[key] = str(path)
    expected = digest({k: v for k, v in result.items() if k != "config_digest"})
    if value.get("config_digest") not in (None, "", expected): raise ValueError("config_digest_mismatch")
    result["config_digest"] = expected
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file(): raise ValueError("config_path_unsafe")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping): raise ValueError("config_not_object")
    return validate_config(value)


def _components(cfg: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    hc = health.load_config(cfg["health_probe_configuration_path"])
    ac = autonomy.load_config(cfg["autonomy_cycle_configuration_path"])
    cc = collector.load_config(ac["collector_configuration_path"])
    agreements = (cfg["repository_identity"] == hc["repository_identity"] == ac["repository_identity"] == cc["repository_identity"],
        Path(cfg["repository_root"]) == Path(hc["repository_root"]) == Path(ac["repository_root"]) == Path(cc["repository_root"]),
        cfg["base_sha"] == hc["base_sha"] == ac["base_sha"] == cc["base_sha"],
        cfg["evaluation_time"] == hc["evaluation_time"],
        Path(hc["governed_signal_output_root"]) in [Path(x) for x in cc["governed_improvement_signal_source_roots"]],
        Path(ac["activation_profile_bundle_manifest_path"]) == Path(cc["activation_profile_bundle_manifest_path"]),
        bool(cc.get("stop_marker")) and bool(ac.get("stop_marker")))
    if not all(agreements): raise ValueError("component_configuration_disagreement")
    return hc, ac, cc


def _lock(cfg: Mapping[str, Any]) -> Any:
    handle = (Path(str(cfg["external_wake_state_root"])) / "wake.lock").open("a+b")
    try: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: handle.close(); raise ValueError("wake_lock_unavailable")
    return handle


def _receipts(cfg: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    path = Path(str(cfg["wake_receipt_journal_path"])); rows: list[dict[str, Any]] = []
    if not path.exists(): return rows, []
    try:
        for line in path.read_bytes().splitlines():
            row = json.loads(line); body = {k: v for k, v in row.items() if k != "receipt_digest"}
            if row.get("schema_version") != RECEIPT_SCHEMA or row.get("sequence") != len(rows)+1 or row.get("predecessor_receipt_digest") != (rows[-1]["receipt_digest"] if rows else ZERO_DIGEST) or row.get("receipt_digest") != digest(body):
                raise ValueError("wake_receipt_chain_invalid")
            rows.append(row)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError): return [], ["wake_receipt_chain_invalid"]
    return rows, []


def doctor(config: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        cfg = validate_config(config); hc, ac, _ = _components(cfg)
        if health.doctor(hc)["status"] != "health_probe_ready": reasons.append("health_probe_not_ready")
        if autonomy.doctor(ac, evaluation_time=cfg["evaluation_time"])["status"] != "autonomy_cycle_ready": reasons.append("autonomy_cycle_not_ready")
        if _receipts(cfg)[1]: reasons.append("wake_receipt_chain_invalid")
        lock = _lock(cfg); lock.close()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc: reasons.append(str(exc)); cfg = dict(config)
    return {"schema_version":"sentientos.maintenance_wake_cycle_doctor:v1", "status":"maintenance_wake_ready" if not reasons else "maintenance_wake_blocked", "config_digest":cfg.get("config_digest"), "reason_codes":sorted(set(reasons))}


def inspect_receipts(config: Mapping[str, Any]) -> dict[str, Any]:
    try: cfg=validate_config(config); rows,reasons=_receipts(cfg)
    except (OSError,ValueError,KeyError,TypeError) as exc: rows,reasons=[],[str(exc)]
    return {"status":"receipts_ready" if not reasons else "receipts_blocked", "receipt_count":len(rows), "head_receipt_digest":rows[-1]["receipt_digest"] if rows else ZERO_DIGEST, "reason_codes":reasons, "receipts":rows}


def _stop(cfg: Mapping[str, Any], stage: str, observations: list[dict[str, Any]]) -> bool:
    present=Path(str(cfg["stop_marker"])).exists(); observations.append({"stage":stage,"present":present}); return present


def wake_once(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg=validate_config(config); effects={"health_probe_invocations":0,"autonomy_cycle_invocations":0}; stops: list[dict[str,Any]]=[]
    try: lock=_lock(cfg)
    except ValueError as exc: return {"status":"maintenance_wake_blocked","reason_codes":[str(exc)],"effect_counts":effects}
    with lock:
        try:
            hc,ac,cc=_components(cfg); rows,reasons=_receipts(cfg)
            if reasons: raise ValueError(reasons[0])
            pre=autonomy.inspect(ac,evaluation_time=cfg["evaluation_time"])
            probe_result=None; autonomy_result=None; skip_reason=None
            if _stop(cfg,"integrity_and_stop",stops): status="maintenance_wake_paused"
            elif pre["status"] != "inspection_ready": raise ValueError("autonomy_inspection_blocked")
            elif pre["next_action"] in {"continue_existing_work","process_existing_candidate"}:
                skip_reason="existing_autonomy_custody"; autonomy_result=autonomy.cycle_once(ac,evaluation_time=cfg["evaluation_time"]); effects["autonomy_cycle_invocations"]=1; status=str(autonomy_result["status"])
            else:
                scanned=collector.scan(cc,evaluation_time=cfg["evaluation_time"])
                if scanned["status"] != "scan_ready": raise ValueError("collector_scan_blocked")
                if int(scanned["source_count"]) > 0:
                    skip_reason="existing_governed_source"; autonomy_result=autonomy.cycle_once(ac,evaluation_time=cfg["evaluation_time"]); effects["autonomy_cycle_invocations"]=1; status=str(autonomy_result["status"])
                else:
                    probe_result=health.probe_once(hc); effects["health_probe_invocations"]=1
                    if probe_result["status"] == "health_probe_healthy": status="maintenance_wake_idle"
                    elif probe_result["status"] != "health_probe_findings": status="maintenance_wake_blocked"
                    elif _stop(cfg,"after_health_probe",stops): status="maintenance_wake_paused"
                    else: autonomy_result=autonomy.cycle_once(ac,evaluation_time=cfg["evaluation_time"]); effects["autonomy_cycle_invocations"]=1; status=str(autonomy_result["status"])
            component_receipt = (autonomy_result or {}).get("receipt") or {}
            body={"schema_version":RECEIPT_SCHEMA,"sequence":len(rows)+1,"predecessor_receipt_digest":rows[-1]["receipt_digest"] if rows else ZERO_DIGEST,"wake_config_digest":cfg["config_digest"],"evaluation_time":cfg["evaluation_time"],"stop_observations":stops,"pre_wake_autonomy_state":pre,"probe_ran":probe_result is not None,"probe_skip_reason":skip_reason,"health_probe_result":probe_result,"autonomy_cycle_result":autonomy_result,"terminal_custody":component_receipt.get("terminal_custody"),"terminal_status":status,"effect_counts":effects}
            receipt=dict(body); receipt["receipt_digest"]=digest(body)
            fd=os.open(cfg["wake_receipt_journal_path"],os.O_WRONLY|os.O_APPEND|os.O_CREAT|getattr(os,"O_NOFOLLOW",0),0o600)
            with os.fdopen(fd,"ab") as handle: handle.write(canonical_json_bytes(receipt)+b"\n"); handle.flush(); os.fsync(handle.fileno())
            return {"schema_version":"sentientos.maintenance_wake_cycle_result:v1","status":status,"effect_counts":effects,"receipt":receipt}
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
            return {"status":"maintenance_wake_blocked","reason_codes":[str(exc)],"effect_counts":effects}


def inspect(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg=validate_config(config); _,ac,cc=_components(cfg)
    return {"status":"inspection_ready","config_digest":cfg["config_digest"],"autonomy":autonomy.inspect(ac,evaluation_time=cfg["evaluation_time"]),"collector":collector.inspect(cc,evaluation_time=cfg["evaluation_time"]),"receipts":inspect_receipts(cfg)}


def print_run_command(config_path: str|Path, *, python_executable: str=sys.executable) -> dict[str,Any]:
    return {"status":"run_command_ready","argv":[python_executable,str(Path(__file__).parents[1]/"scripts"/"maintenance_wake_cycle.py"),"--config",str(Path(config_path).resolve()),"wake-once"],"shell":False,"scheduler_installation":False}

__all__=["CONFIG_SCHEMA","RECEIPT_SCHEMA","ZERO_DIGEST","validate_config","load_config","doctor","wake_once","inspect","inspect_receipts","print_run_command","canonical_json_bytes","digest"]
