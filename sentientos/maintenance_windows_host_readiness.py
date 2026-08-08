"""Read-only Windows host readiness and explicit maintenance-canary planning.

This module deliberately has no scheduler integration.  The only subprocesses it
starts are bounded diagnostic executable/git/pytest probes.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos import maintenance_wake_cycle as wake
from sentientos import maintenance_windows_deployment as deployment

SCHEMA = "sentientos.maintenance_windows_host_manifest:v1"
CANARY_CONTENT = "sentientos-windows-live-host-canary: healthy\n"
FIELDS = {
    "schema_version", "repository_root", "expected_repository_sha", "python_executable",
    "git_executable", "codex_executable", "wake_configuration_path",
    "activation_profile_manifest_path", "collector_external_state_root",
    "autonomy_external_state_root", "wake_external_state_root", "deployment_manifest_path",
    "deployment_output_directory", "tracked_remote", "tracked_base_ref", "expected_task_name",
    "canary_source_path", "canary_validation_node", "canary_allowed_path_boundary",
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


def _run(argv: Sequence[str], cwd: Path | None = None, timeout: int = 15) -> dict[str, Any]:
    try:
        completed = subprocess.run(list(argv), cwd=cwd, stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, timeout=timeout, check=False)
        return {"argv": list(argv), "returncode": completed.returncode,
                "stdout": completed.stdout.strip()[:4096], "stderr": completed.stderr.strip()[:4096]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": list(argv), "returncode": None, "error": type(exc).__name__}


def _which(name: str) -> str | None:
    found = shutil.which(name)
    return str(Path(found).resolve()) if found else None


def _identity(path: str) -> dict[str, Any]:
    target = Path(path)
    result: dict[str, Any] = {"path": str(target.absolute()), "exists": target.exists(), "is_symlink": target.is_symlink()}
    if target.exists() and not target.is_symlink():
        stat = target.stat(); result.update({"is_directory": target.is_dir(), "device": stat.st_dev, "inode": stat.st_ino})
    return result


def inspect_host(repository_root: str | Path, custody_roots: Sequence[str] = ()) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    git = _which("git")
    codex = _which("codex")
    powershell = _which("pwsh") or _which("powershell")
    def probe(executable: str | None, args: Sequence[str]) -> dict[str, Any]:
        return {"executable": executable, "probe": _run([executable, *args]) if executable else None,
                "verified": bool(executable)}
    head = _run([git, "-C", str(repo), "rev-parse", "HEAD"]) if git else {}
    branch = _run([git, "-C", str(repo), "symbolic-ref", "--short", "-q", "HEAD"]) if git else {}
    status = _run([git, "-C", str(repo), "status", "--porcelain"]) if git else {}
    remotes: list[dict[str, str]] = []
    if git:
        remote_probe = _run([git, "-C", str(repo), "remote", "-v"])
        for line in remote_probe.get("stdout", "").splitlines():
            parts = line.split()
            if len(parts) >= 2: remotes.append({"name": parts[0], "url": parts[1]})
    return {"status": "windows_host_inspected", "repository_root": str(repo),
            "repository_head": head.get("stdout") or None, "repository_ref": branch.get("stdout") or "HEAD",
            "repository_clean": status.get("returncode") == 0 and not status.get("stdout"),
            "python": {"executable": str(Path(sys.executable).resolve()), "version": sys.version.splitlines()[0]},
            "git": probe(git, ["--version"]), "codex": probe(codex, ["--version"]),
            "codex_authentication": "unverified", "powershell": probe(powershell, ["--version"]),
            "production_wake_cli_exists": (repo / "scripts" / "maintenance_wake_cycle.py").is_file(),
            "windows_deployment_cli_exists": (repo / "scripts" / "maintenance_windows_deployment.py").is_file(),
            "remotes": remotes, "tracked_base_ref_exists": "unverified_without_explicit_ref",
            "external_custody_identities": [_identity(x) for x in custody_roots],
            "credentials_inspected": False, "scheduler_mutation_performed": False}


def validate_manifest(value: Mapping[str, Any]) -> dict[str, str]:
    if set(value) != FIELDS or value.get("schema_version") != SCHEMA:
        raise ValueError("invalid_closed_host_manifest")
    result = {key: str(value[key]) for key in FIELDS}
    if not all(result[key] for key in FIELDS - {"schema_version"}): raise ValueError("missing_explicit_binding")
    if len(result["expected_repository_sha"]) != 40: raise ValueError("expected_repository_sha_invalid")
    return result


def load_manifest(path: str | Path) -> dict[str, str]:
    source = Path(path)
    if source.is_symlink() or not source.is_file(): raise ValueError("host_manifest_path_unsafe")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping): raise ValueError("host_manifest_not_object")
    return validate_manifest(value)


def render_host_manifest(values: Mapping[str, Any]) -> dict[str, str]:
    return validate_manifest({"schema_version": SCHEMA, **values})


def verify_host_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    try: cfg = validate_manifest(value); reasons: list[str] = []
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "windows_host_manifest_blocked", "reason_codes": [str(exc)], "scheduler_mutation_performed": False}
    repo = Path(cfg["repository_root"])
    canary = Path(cfg["canary_source_path"])
    boundary = Path(cfg["canary_allowed_path_boundary"])
    try: canary.relative_to(boundary); boundary.relative_to(repo)
    except ValueError: reasons.append("canary_outside_allowed_path_boundary")
    return {"status": "windows_host_manifest_verified" if not reasons else "windows_host_manifest_blocked",
            "reason_codes": reasons, "manifest_digest": "sha256:" + hashlib.sha256(canonical_json_bytes(cfg)).hexdigest(),
            "scheduler_mutation_performed": False}


def doctor_live(value: Mapping[str, Any]) -> dict[str, Any]:
    try: cfg = validate_manifest(value)
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "windows_host_blocked", "reason_codes": [str(exc)], "facts": {}, "scheduler_mutation_performed": False}
    reasons: list[str] = []; facts: dict[str, Any] = {}
    repo = Path(cfg["repository_root"]).resolve()
    for name in ("python_executable", "git_executable", "codex_executable"):
        exe = cfg[name]; probe = _run([exe, "--version"]); facts[name + "_probe"] = probe
        if probe["returncode"] != 0: reasons.append(name + "_probe_failed")
    head = _run([cfg["git_executable"], "-C", str(repo), "rev-parse", "HEAD"]); facts["repository_head"] = head.get("stdout")
    if head.get("stdout") != cfg["expected_repository_sha"]: reasons.append("repository_head_mismatch")
    dirty = _run([cfg["git_executable"], "-C", str(repo), "status", "--porcelain"]); facts["working_tree_clean"] = dirty.get("returncode") == 0 and not dirty.get("stdout")
    if not facts["working_tree_clean"]: reasons.append("repository_dirty")
    if not (repo / "scripts" / "maintenance_wake_cycle.py").is_file(): reasons.append("production_wake_cli_missing")
    activation_manifest = Path(cfg["activation_profile_manifest_path"])
    facts["activation_profile_manifest"] = _identity(str(activation_manifest))
    if activation_manifest.is_symlink() or not activation_manifest.is_file(): reasons.append("activation_profile_manifest_missing")
    remote_ref = f"{cfg['tracked_remote']}/{cfg['tracked_base_ref']}"
    rp = _run([cfg["git_executable"], "-C", str(repo), "rev-parse", "--verify", remote_ref]); facts["tracked_base_ref"] = remote_ref
    if rp.get("returncode") != 0: reasons.append("tracked_base_ref_unreadable")
    for key in ("collector_external_state_root", "autonomy_external_state_root", "wake_external_state_root"):
        path = Path(cfg[key]).resolve(); facts[key] = _identity(str(path))
        if not path.is_dir() or path == repo or repo in path.parents: reasons.append(key + "_custody_invalid")
        for marker in ("STOP", "stop", "STOP.marker"):
            if (path / marker).exists(): reasons.append("stop_marker_present")
    try:
        wc = wake.load_config(cfg["wake_configuration_path"])
        if Path(str(wc["stop_marker"])).exists(): reasons.append("stop_marker_present")
        wd = wake.doctor(wc); facts["wake_doctor"] = wd
        if wd["status"] != "maintenance_wake_ready": reasons.append("wake_doctor_not_ready")
        wi = wake.inspect(wc); facts["wake_inspection"] = wi
        autonomy = wi.get("autonomy", {})
        if autonomy.get("next_action") not in {None, "idle", "scan_for_work"}: reasons.append("maintenance_custody_active_or_ambiguous")
        collector = wi.get("collector", {})
        if int(collector.get("candidate_count", collector.get("source_count", 0)) or 0): reasons.append("maintenance_inbox_not_empty")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc: reasons.append("wake_configuration_blocked:" + str(exc))
    try:
        dep = deployment.load_manifest(cfg["deployment_manifest_path"])
        if dep.get("task_name") != cfg["expected_task_name"]: reasons.append("deployment_task_name_mismatch")
        dv = deployment.verify(dep, cfg["deployment_output_directory"]); facts["deployment_verification"] = dv
        if dv["status"] != "windows_deployment_ready": reasons.append("deployment_verification_failed")
    except (OSError, ValueError, KeyError, TypeError) as exc: reasons.append("deployment_verification_failed:" + str(exc))
    check = verify_host_manifest(cfg)
    reasons.extend(check["reason_codes"])
    node = _run([cfg["python_executable"], "-m", "pytest", "--collect-only", "-q", cfg["canary_validation_node"]], repo)
    facts["canary_validation_node_probe"] = node
    if node.get("returncode") != 0: reasons.append("canary_validation_node_missing")
    return {"status": "windows_host_ready" if not reasons else "windows_host_blocked",
            "reason_codes": sorted(set(reasons)), "facts": facts, "warnings": [],
            "scheduler_mutation_performed": False}


def print_manual_canary_command(value: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_manifest(value); repo = Path(cfg["repository_root"])
    commands = [
        [cfg["python_executable"], str(repo / "scripts" / "maintenance_windows_host_readiness.py"), "doctor-live", "--manifest", "<host-manifest>"],
        [cfg["python_executable"], "-c", "from pathlib import Path; Path(r'" + cfg["canary_source_path"].replace("'", "''") + "').write_text('sentientos-windows-live-host-canary: defect\\n', encoding='utf-8')"],
        [cfg["python_executable"], str(repo / "scripts" / "maintenance_wake_cycle.py"), "--config", cfg["wake_configuration_path"], "--evaluation-time", "<fresh-utc-evaluation-time>", "wake-once"],
        [cfg["python_executable"], str(repo / "scripts" / "maintenance_windows_host_readiness.py"), "inspect-canary", "--manifest", "<host-manifest>"],
    ]
    return {"status": "manual_canary_command_ready", "commands": [{"argv": x, "shell": False} for x in commands],
            "executed": False, "scheduler_mutation_performed": False}


def inspect_canary(value: Mapping[str, Any]) -> dict[str, Any]:
    try: cfg = validate_manifest(value); path = Path(cfg["canary_source_path"]); data = path.read_bytes()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "canary_blocked", "reason_codes": [str(exc)], "scheduler_mutation_performed": False}
    canonical = CANARY_CONTENT.encode(); content_state = "canonical" if data == canonical else "defect"
    validation = _run([cfg["python_executable"], "-m", "pytest", "-q", cfg["canary_validation_node"]], Path(cfg["repository_root"]))
    try:
        wi = wake.inspect(wake.load_config(cfg["wake_configuration_path"])); receipts = wi.get("receipts", {}).get("receipts", [])
        latest = receipts[-1] if receipts else None; autonomy = wi.get("autonomy", {})
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError): wi={}; receipts=[]; latest=None; autonomy={}
    active = autonomy.get("next_action") not in {None, "idle", "scan_for_work"}
    published = bool(latest and latest.get("terminal_status") in {"autonomy_cycle_completed", "maintenance_wake_idle"})
    if data != canonical: status = "canary_maintenance_active" if active else "canary_defect_present"
    elif not receipts: status = "canary_not_started"
    elif active: status = "canary_maintenance_active"
    elif published and validation.get("returncode") == 0: status = "canary_completed"
    else: status = "canary_repaired_unpublished"
    return {"status": status, "canary_digest": "sha256:" + hashlib.sha256(data).hexdigest(),
            "content_state": content_state, "validation": validation, "latest_health_receipt": latest,
            "governed_signal_identity": (latest or {}).get("receipt_digest"), "candidate_identity": autonomy.get("candidate_id"),
            "task_lease_session_identity": autonomy.get("active_task"), "validation_identities": autonomy.get("validation"),
            "commit_identity": autonomy.get("commit_sha"), "publication_identity": autonomy.get("publication"),
            "base_cursor": autonomy.get("base_cursor"), "closure_identity": autonomy.get("closure"),
            "wake_receipt": latest, "terminally_idle": not active, "scheduler_mutation_performed": False}


__all__ = ["SCHEMA", "CANARY_CONTENT", "FIELDS", "inspect_host", "validate_manifest", "load_manifest",
           "render_host_manifest", "verify_host_manifest", "doctor_live", "print_manual_canary_command", "inspect_canary", "canonical_json_bytes"]
