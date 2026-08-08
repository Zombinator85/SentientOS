"""Bounded external producer of governed maintenance health evidence."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import stat
import subprocess
from datetime import datetime, timezone
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.provenance_hash_chain import compute_provenance_hash
from sentientos import governed_improvement_signal_plane as signal_plane

CONFIG_SCHEMA = "sentientos.maintenance_health_probe_config:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_health_probe_receipt:v1"
ZERO_DIGEST = "sha256:" + "0" * 64
_REQUIRED = {
    "schema_version", "repository_identity", "repository_root", "base_sha",
    "pytest_node_ids", "probe_timeout_seconds", "maximum_failing_records",
    "probe_state_root", "governed_signal_output_root",
    "declared_validation_expectations", "requested_maintenance_authority_classes",
    "declared_constraints", "estimated_file_count", "estimated_changed_line_count",
    "estimated_implementation_seconds", "estimated_validation_seconds",
    "evaluation_time", "receipt_journal_path",
}
_ALLOWED = _REQUIRED | {"config_digest"}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical_json_bytes(value))


def _directory(value: object, *, label: str, repo: Path) -> Path:
    path = Path(str(value))
    if path.is_symlink() or not path.exists() or not stat.S_ISDIR(os.lstat(path).st_mode):
        raise ValueError(label + "_unsafe")
    resolved = path.resolve(strict=True)
    if resolved == repo or repo in resolved.parents:
        raise ValueError(label + "_inside_repository")
    if stat.S_IMODE(os.stat(resolved).st_mode) & 0o077:
        raise ValueError(label + "_not_private")
    return resolved


def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) - _ALLOWED:
        raise ValueError("unknown_config_field")
    if not _REQUIRED.issubset(value):
        raise ValueError("missing_config_field")
    cfg = dict(value)
    if cfg["schema_version"] != CONFIG_SCHEMA:
        raise ValueError("wrong_config_schema")
    repo = Path(str(cfg["repository_root"]))
    if repo.is_symlink() or not repo.is_dir():
        raise ValueError("repository_root_unsafe")
    repo = repo.resolve(strict=True)
    cfg["repository_root"] = str(repo)
    for key in ("pytest_node_ids", "declared_validation_expectations", "requested_maintenance_authority_classes", "declared_constraints"):
        rows = cfg[key]
        if not isinstance(rows, list) or not rows or any(not isinstance(x, str) or not x.strip() for x in rows):
            raise ValueError(key + "_invalid")
        if len(set(rows)) != len(rows):
            raise ValueError(key + "_duplicate")
        if rows != sorted(rows):
            raise ValueError(key + "_not_canonical")
    for node in cfg["pytest_node_ids"]:
        if node.startswith("-") or "\x00" in node or not node.startswith("tests/") or "::" not in node:
            raise ValueError("pytest_node_id_invalid")
        relative = node.split("::", 1)[0]
        if ".." in Path(relative).parts:
            raise ValueError("pytest_node_id_invalid")
    for key in ("probe_timeout_seconds", "maximum_failing_records", "estimated_file_count", "estimated_changed_line_count", "estimated_implementation_seconds", "estimated_validation_seconds"):
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError(key + "_invalid")
    if cfg["maximum_failing_records"] > signal_plane.MAX_RECORDS:
        raise ValueError("maximum_failing_records_unsupported")
    state = _directory(cfg["probe_state_root"], label="probe_state_root", repo=repo)
    output = _directory(cfg["governed_signal_output_root"], label="governed_signal_output_root", repo=repo)
    receipt = Path(str(cfg["receipt_journal_path"]))
    if receipt.is_symlink() or receipt.parent.resolve() != state:
        raise ValueError("receipt_journal_path_unsafe")
    cfg.update(probe_state_root=str(state), governed_signal_output_root=str(output), receipt_journal_path=str(receipt))
    supplied = cfg.pop("config_digest", None)
    computed = digest(cfg)
    if supplied is not None and supplied != computed:
        raise ValueError("config_digest_mismatch")
    cfg["config_digest"] = computed
    return cfg


def load_config(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("config_path_unsafe")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("config_not_object")
    return validate_config(payload)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False, shell=False, env={"PATH": os.defpath, "LC_ALL": "C"})
    if result.returncode:
        raise ValueError("git_inspection_failed")
    return result.stdout.strip()


def doctor(config: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    cfg_digest: str | None = None
    try:
        cfg = validate_config(config); cfg_digest = cfg["config_digest"]
        repo = Path(cfg["repository_root"])
        if _git(repo, "rev-parse", "HEAD") != cfg["base_sha"]:
            reasons.append("base_sha_mismatch")
        if _git(repo, "status", "--porcelain", "--untracked-files=all"):
            reasons.append("repository_not_clean")
        if not (repo / "scripts" / "run_tests.py").is_file():
            reasons.append("run_tests_entry_point_missing")
        for node in cfg["pytest_node_ids"]:
            path, symbol = node.split("::", 1)
            candidate = repo / path
            if candidate.is_symlink() or not candidate.is_file() or symbol.split("[")[0].split("::")[-1] not in candidate.read_text(encoding="utf-8"):
                reasons.append("pytest_node_missing:" + node)
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        reasons.append(str(exc))
    return {"schema_version": "sentientos.maintenance_health_probe_doctor:v1", "status": "health_probe_ready" if not reasons else "health_probe_blocked", "config_digest": cfg_digest, "reason_codes": sorted(set(reasons))}


def print_run_command(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_config(config)
    return {"status": "health_probe_ready", "argv": [sys.executable, "-m", "scripts.run_tests", "-q", *cfg["pytest_node_ids"]], "cwd": cfg["repository_root"], "shell": False}


def _run_bounded(argv: Sequence[str], *, cwd: Path, timeout: int) -> int:
    # Do not forward the operator environment (and therefore do not expose
    # credentials) to diagnostic tests. The editable repository and absolute
    # interpreter are sufficient for the repository-native runner.
    child = subprocess.Popen(list(argv), cwd=cwd, shell=False, start_new_session=True,
                             env={"PATH": os.defpath, "PYTHONPATH": str(cwd), "LC_ALL": "C"})
    try:
        return child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL); child.wait()
        raise ValueError("probe_timeout")


def _validated_provenance(cfg: Mapping[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path = Path(cfg["repository_root"]) / signal_plane.RUN_TESTS_PROVENANCE_RELATIVE_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("run_tests_provenance_missing")
    raw = path.read_bytes(); payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("run_tests_provenance_not_object")
    actual = payload.get("provenance_hash")
    prior = payload.get("prev_provenance_hash")
    if actual != compute_provenance_hash(payload, prior if isinstance(prior, str) else None):
        raise ValueError("run_tests_provenance_hash_mismatch")
    if payload.get("git_sha") != cfg["base_sha"] or payload.get("repo_root") != cfg["repository_root"]:
        raise ValueError("run_tests_provenance_repository_binding_mismatch")
    pytest_args = payload.get("pytest_args")
    if (not isinstance(pytest_args, list)
            or sorted(pytest_args) != sorted(["-q", *cfg["pytest_node_ids"]])
            or payload.get("selected_node_ids") != cfg["pytest_node_ids"]):
        raise ValueError("run_tests_provenance_selection_mismatch")
    if payload.get("metrics_status") != "ok" or payload.get("reporter_ok") is not True:
        raise ValueError("run_tests_provenance_incomplete")
    return path, payload, digest_bytes(raw)


def _receipts(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    if path.is_symlink() or not path.is_file(): raise ValueError("receipt_journal_unsafe")
    rows = [json.loads(x) for x in path.read_bytes().splitlines()]
    previous = ZERO_DIGEST
    for index, row in enumerate(rows, 1):
        claimed = row.pop("receipt_digest", None)
        if row.get("schema_version") != RECEIPT_SCHEMA or row.get("sequence") != index or row.get("predecessor_receipt_digest") != previous or claimed != digest(row):
            raise ValueError("receipt_chain_invalid")
        row["receipt_digest"] = claimed; previous = claimed
    return rows


def _effective_time(cfg: Mapping[str, Any], evaluation_time: str | None) -> str:
    if evaluation_time is None:
        return str(cfg["evaluation_time"])
    try:
        parsed = datetime.fromisoformat(evaluation_time.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("invalid_evaluation_time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("invalid_evaluation_time")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "0Z"


def _append_receipt(cfg: Mapping[str, Any], *, evaluation_time: str, status: str, provenance_hash: str, output_name: str | None, output_digest: str | None) -> None:
    path = Path(cfg["receipt_journal_path"]); rows = _receipts(path)
    if any(x["provenance_hash"] == provenance_hash and x["status"] == status and x["evaluation_time"] == evaluation_time for x in rows): return
    row = {"schema_version": RECEIPT_SCHEMA, "sequence": len(rows)+1, "predecessor_receipt_digest": rows[-1]["receipt_digest"] if rows else ZERO_DIGEST, "config_digest": cfg["config_digest"], "provenance_hash": provenance_hash, "status": status, "output_filename": output_name, "output_byte_digest": output_digest, "evaluation_time": evaluation_time}
    row["receipt_digest"] = digest(row)
    fd = os.open(path, os.O_WRONLY|os.O_APPEND|os.O_CREAT|getattr(os,"O_NOFOLLOW",0), 0o600)
    with os.fdopen(fd,"ab") as handle: handle.write(canonical_json_bytes(row)+b"\n"); handle.flush(); os.fsync(handle.fileno())


def probe_once(config: Mapping[str, Any], *, evaluation_time: str | None = None) -> dict[str, Any]:
    cfg = validate_config(config); effective_time = _effective_time(cfg, evaluation_time); readiness = doctor(cfg)
    if readiness["status"] != "health_probe_ready": return {**readiness, "evaluation_time": effective_time}
    lock_path = Path(cfg["probe_state_root"]) / "probe.lock"
    lock = open(lock_path, "a+b"); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        command = print_run_command(cfg)["argv"]
        _run_bounded(command, cwd=Path(cfg["repository_root"]), timeout=cfg["probe_timeout_seconds"])
        provenance_path, provenance, provenance_digest = _validated_provenance(cfg)
        failed = int(provenance.get("tests_failed") or 0)
        if failed == 0:
            if int(provenance.get("pytest_exit_code", 1)) != 0: raise ValueError("run_tests_non_failure_error")
            _append_receipt(cfg, evaluation_time=effective_time, status="health_probe_healthy", provenance_hash=str(provenance["provenance_hash"]), output_name=None, output_digest=None)
            return {"status":"health_probe_healthy", "config_digest":cfg["config_digest"], "evaluation_time":effective_time, "provenance_digest":provenance_digest, "governed_signal_written":False}
        records = signal_plane.records_from_run_tests_provenance(provenance, provenance_path=provenance_path, repo_root=cfg["repository_root"], provenance_digest=provenance_digest)
        if len(records) > cfg["maximum_failing_records"]: raise ValueError("maximum_failing_records_exceeded")
        metadata = {"declared_validation_expectations":cfg["declared_validation_expectations"], "requested_authority_classes":cfg["requested_maintenance_authority_classes"], "declared_constraints":cfg["declared_constraints"], "estimated_file_count":cfg["estimated_file_count"], "estimated_changed_line_count":cfg["estimated_changed_line_count"], "estimated_implementation_seconds":cfg["estimated_implementation_seconds"], "estimated_validation_seconds":cfg["estimated_validation_seconds"], "observed_at":effective_time}
        evaluation = signal_plane.evaluate_signal_plane(({**record, **metadata} for record in records), repo_root=cfg["repository_root"])
        # Validate the exact JSON-domain value the collector will load, rather
        # than an in-memory tuple-bearing dataclass projection.
        payload = json.loads(canonical_json_bytes(evaluation.to_dict()))
        valid, why = signal_plane.validate_evaluation(payload)
        if not valid: raise ValueError("governed_signal_invalid:" + ",".join(why))
        raw = canonical_json_bytes(payload) + b"\n"; invocation_digest = hashlib.sha256(effective_time.encode()).hexdigest()[:16]; name = "health-probe-" + str(provenance["provenance_hash"]) + "-" + invocation_digest + ".json"; target = Path(cfg["governed_signal_output_root"])/name
        if target.exists():
            if target.is_symlink() or target.read_bytes() != raw: raise ValueError("governed_signal_output_conflict")
        else:
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
            with os.fdopen(fd,"wb") as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        output_digest=digest_bytes(raw); _append_receipt(cfg,evaluation_time=effective_time,status="health_probe_findings",provenance_hash=str(provenance["provenance_hash"]),output_name=name,output_digest=output_digest)
        return {"status":"health_probe_findings", "config_digest":cfg["config_digest"], "evaluation_time":effective_time, "provenance_digest":provenance_digest, "governed_signal_path":str(target), "governed_signal_byte_digest":output_digest}
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        return {"status":"health_probe_blocked", "config_digest":cfg["config_digest"], "evaluation_time":effective_time, "reason_codes":[str(exc)]}
    finally:
        lock.close()


def inspect(config: Mapping[str, Any]) -> dict[str, Any]:
    cfg=validate_config(config); rows=_receipts(Path(cfg["receipt_journal_path"]))
    return {"status":"health_probe_ready", "config_digest":cfg["config_digest"], "receipt_count":len(rows), "receipts":rows}

__all__ = ["CONFIG_SCHEMA", "validate_config", "load_config", "doctor", "probe_once", "inspect", "print_run_command", "canonical_json_bytes"]
