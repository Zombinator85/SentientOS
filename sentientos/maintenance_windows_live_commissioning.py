"""Bounded, recovery-first composition of the Windows live maintenance APIs."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from sentientos import maintenance_wake_cycle as wake
from sentientos import maintenance_windows_deployment as deployment
from sentientos import maintenance_windows_host_readiness as readiness
from sentientos import maintenance_windows_live_bootstrap as bootstrap

STATUS_READY = "windows_commissioning_ready"
STATUS_BLOCKED = "windows_commissioning_blocked"
STATUS_COMPLETED = "windows_commissioning_completed"
STATE_SCHEMA = "sentientos.maintenance_windows_live_commissioning_state:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_windows_live_commissioning_receipt:v1"
ZERO_DIGEST = "sha256:" + "0" * 64
DEFECT = b"sentientos-windows-live-host-canary: defect\n"


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _now() -> str:
    value: str = wake.canonical_evaluation_time(datetime.now(timezone.utc).isoformat())
    return value


def _load(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("unsafe_json_path:" + str(source))
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("json_object_required:" + str(source))
    return value


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    data = _bytes(value)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError("conflicting_commissioning_custody:" + str(path))
        return
    temporary = path.with_name(path.name + ".new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)


def _save_state(root: Path, state: Mapping[str, Any]) -> None:
    target = root / "commissioning-state.json"
    temporary = root / "commissioning-state.json.new"
    data = _bytes(state)
    temporary.write_bytes(data)
    os.replace(temporary, target)


def _state(root: Path, manifest_digest: str) -> dict[str, Any]:
    path = root / "commissioning-state.json"
    if not path.exists():
        return {"schema_version": STATE_SCHEMA, "manifest_digest": manifest_digest, "completed_stages": [], "evidence": {}}
    value = _load(path)
    if value.get("schema_version") != STATE_SCHEMA or value.get("manifest_digest") != manifest_digest:
        raise ValueError("conflicting_commissioning_state")
    return value


@contextmanager
def _lock(root: Path) -> Iterator[None]:
    handle = (root / "commissioning.lock").open("a+b")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close(); raise ValueError("commissioning_active") from exc
    try: yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN); handle.close()


def _stop_paths(state_root: Path, index: Mapping[str, Any] | None = None) -> list[Path]:
    paths = [state_root / "STOP"]
    if index:
        for value in index.get("custody_layout", {}).values():
            paths.append(Path(str(value)) / "STOP")
    return paths


def _require_no_stop(state_root: Path, index: Mapping[str, Any] | None = None) -> None:
    if any(path.exists() for path in _stop_paths(state_root, index)):
        raise ValueError("stop_marker_present")


def doctor(manifest_path: str | Path, state_root: str | Path) -> dict[str, Any]:
    """Perform the commissioning preflight without creating or changing custody."""
    reasons: list[str] = []
    try:
        manifest = bootstrap.validate_manifest(_load(manifest_path))
        repo = Path(str(manifest["repository_root"])).resolve()
        if not repo.is_dir(): reasons.append("repository_root_missing")
        facts = bootstrap.inspect_host(repo)
        if facts.get("status") != "windows_host_inspected": reasons.append("host_inspection_failed")
        if facts.get("repository_head") != manifest["expected_repository_sha"]: reasons.append("repository_head_mismatch")
        if not facts.get("repository_clean"): reasons.append("repository_dirty")
        for executable in ("python", "git", "codex", "powershell"):
            if not (facts.get(executable) or {}).get("executable"): reasons.append(executable + "_executable_missing")
        root = Path(state_root).absolute()
        if root == repo or repo in root.parents: reasons.append("commissioning_state_inside_repository")
        if root.exists():
            if root.is_symlink() or not root.is_dir(): reasons.append("commissioning_state_unsafe")
            else: _state(root, bootstrap.digest(manifest))
        _require_no_stop(root)
        remote = subprocess.run([str(facts["git"]["executable"]), "-C", str(repo), "rev-parse", "--verify", str(manifest["tracked_base_ref"])], capture_output=True, text=True, check=False)
        if remote.returncode: reasons.append("tracked_remote_base_unreadable")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        reasons.append(str(exc))
    return {"status": STATUS_READY if not reasons else STATUS_BLOCKED, "reason_codes": sorted(set(reasons)), "warnings": [], "credentials_inspected": False, "scheduler_mutation_performed": False}


def commission_once(manifest_path: str | Path, state_root: str | Path, *,
                    create_custody_directories: bool = False, authorize_canary_defect: bool = False,
                    stage_hook: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Run or reconcile exactly one live commissioning chain."""
    try:
        manifest = bootstrap.validate_manifest(_load(manifest_path)); manifest_digest = bootstrap.digest(manifest)
        root = Path(state_root).absolute(); repo = Path(str(manifest["repository_root"])).resolve()
        if root == repo or repo in root.parents: raise ValueError("commissioning_state_inside_repository")
        if not root.exists():
            if not create_custody_directories: raise ValueError("commissioning_state_creation_not_authorized")
            root.mkdir(parents=True, mode=0o700)
        if root.is_symlink() or not root.is_dir(): raise ValueError("commissioning_state_unsafe")
        with _lock(root):
            state = _state(root, manifest_digest); evidence = state["evidence"]
            receipt_path = root / "commissioning-receipt.json"
            if receipt_path.exists():
                receipt = _load(receipt_path)
                if receipt.get("terminal_status") != STATUS_COMPLETED: raise ValueError("conflicting_commissioning_receipt")
                return {"status": STATUS_COMPLETED, "receipt_path": str(receipt_path), "receipt_digest": receipt["receipt_digest"], "scheduler_mutation_performed": False, "credentials_inspected": False}

            index_path = root / "bundle" / "windows-live-bootstrap-index.json"
            index = _load(index_path) if index_path.exists() else None
            _require_no_stop(root, index)
            facts = bootstrap.inspect_host(repo)
            if facts.get("status") != "windows_host_inspected": raise ValueError("host_inspection_failed")
            evidence.setdefault("host_inspection", facts)
            evidence.setdefault("initial_head", facts.get("repository_head"))
            if "bootstrap_verified" not in state["completed_stages"]:
                if not facts.get("repository_clean"): raise ValueError("repository_dirty_before_canary")
                rendered = bootstrap.render(manifest, facts, root / "bundle", create_custody_directories=create_custody_directories)
                index_path = Path(rendered["index_path"]); index = _load(index_path)
                verified = bootstrap.verify(index_path, evaluation_time=_now())
                if verified["status"] != bootstrap.STATUS_READY: raise ValueError("bootstrap_bundle_blocked")
                state["completed_stages"].append("bootstrap_verified"); evidence["bootstrap_index_digest"] = rendered["index_digest"]; _save_state(root, state)
                if stage_hook: stage_hook("bootstrap_verified")
            assert index is not None
            host = readiness.load_manifest(index["artifacts"]["host_manifest"]["path"])
            wake_config = wake.load_config(index["artifacts"]["wake_config"]["path"])
            if "readiness_complete" not in state["completed_stages"]:
                live = readiness.doctor_live(host)
                if live["status"] != "windows_host_ready": raise ValueError("windows_host_readiness_blocked:" + ",".join(live["reason_codes"]))
                remote = subprocess.run([host["git_executable"], "-C", str(repo), "rev-parse", "--verify", str(manifest["tracked_base_ref"])], capture_output=True, text=True, check=False)
                if remote.returncode: raise ValueError("tracked_remote_base_unreadable")
                evidence.update({"readiness": live, "readiness_evaluation_time": live["facts"]["readiness_evaluation_time"], "initial_remote_base_sha": remote.stdout.strip()})
                state["completed_stages"].append("readiness_complete"); _save_state(root, state)
                if stage_hook: stage_hook("readiness_complete")
            if "canary_defect_proven" not in state["completed_stages"]:
                _require_no_stop(root, index)
                if not authorize_canary_defect: raise ValueError("canary_defect_not_authorized")
                target = Path(host["canary_source_path"])
                status = subprocess.run([host["git_executable"], "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=False)
                if status.returncode or status.stdout.strip(): raise ValueError("repository_dirty_before_canary")
                target.write_bytes(DEFECT)
                failed = subprocess.run([host["python_executable"], "-m", "pytest", "-q", host["canary_validation_node"]], cwd=repo, capture_output=True, text=True, check=False)
                if failed.returncode == 0: raise ValueError("canary_validation_did_not_fail")
                evidence.update({"canary_defect_digest": _digest_bytes(DEFECT), "failing_validation_identity": {"node": host["canary_validation_node"], "returncode": failed.returncode}})
                state["completed_stages"].append("canary_defect_proven"); _save_state(root, state)
                if stage_hook: stage_hook("canary_defect_proven")
            # Only the declared canary dirt is tolerated between mutation and production wake.
            dirty = subprocess.run([host["git_executable"], "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=False).stdout.splitlines()
            allowed = str(Path(host["canary_source_path"]).resolve().relative_to(repo)).replace(os.sep, "/")
            if any(line[3:].replace("\\", "/") != allowed for line in dirty): raise ValueError("unrelated_dirty_path_during_canary")
            inspection = readiness.inspect_canary(host)
            if inspection["status"] != "canary_completed":
                _require_no_stop(root, index)
                invocation_time = _now(); result = wake.wake_once(wake_config, evaluation_time=invocation_time)
                if result.get("status") not in {"autonomy_cycle_completed", "maintenance_wake_idle"}: raise ValueError("maintenance_wake_incomplete:" + str(result.get("status")))
                evidence["wake_invocation_evaluation_time"] = invocation_time
                if stage_hook: stage_hook("wake_returned")
                inspection = readiness.inspect_canary(host)
            if inspection["status"] != "canary_completed": raise ValueError("canary_not_completed:" + inspection["status"])
            _require_no_stop(root, index)
            clean = subprocess.run([host["git_executable"], "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=False)
            head = subprocess.run([host["git_executable"], "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
            final_remote_sha = subprocess.run([host["git_executable"], "-C", str(repo), "rev-parse", "--verify", str(manifest["tracked_base_ref"])], capture_output=True, text=True, check=False).stdout.strip()
            if clean.returncode or clean.stdout.strip() or head != inspection["commit_identity"] or final_remote_sha != head or inspection.get("base_cursor") != head or not inspection.get("terminally_idle"):
                raise ValueError("canary_publication_invariants_failed")
            dep = deployment.load_manifest(index["artifacts"]["deployment_manifest"]["path"])
            dep_verify = deployment.verify(dep, dep["deployment_output_directory"])
            if dep_verify["status"] != "windows_deployment_ready": raise ValueError("windows_deployment_blocked")
            command = deployment.print_install_command(dep)
            terminal = inspection.get("wake_receipt") or {}
            receipt_body = {"schema_version": RECEIPT_SCHEMA, "sequence": 1, "predecessor_receipt_digest": ZERO_DIGEST,
                "commissioning_manifest_digest": manifest_digest, "bootstrap_bundle_index_digest": evidence["bootstrap_index_digest"],
                "repository_identity": manifest["repository_identity"], "repository_root": str(manifest["repository_root"]), "initial_head": evidence["initial_head"],
                "initial_remote_base_sha": evidence["initial_remote_base_sha"], "executable_identities": index["executable_identities"],
                "readiness_evaluation_time": evidence["readiness_evaluation_time"], "readiness_result": evidence["readiness"]["status"],
                "canary_defect_digest": evidence["canary_defect_digest"], "failing_validation_identity": evidence["failing_validation_identity"],
                "wake_invocation_evaluation_time": evidence.get("wake_invocation_evaluation_time"), "health_signal_identity": inspection.get("governed_signal_identity"),
                "candidate_identity": inspection.get("candidate_identity"), "task_identity": inspection.get("task_identity"), "lease_identity": inspection.get("lease_identity"),
                "implementation_session_identity": inspection.get("implementation_session_identity"), "implementation_thread_identity": inspection.get("implementation_thread_identity"),
                "validation_identities": inspection.get("validation_identities"), "repair_commit_sha": head, "publication_identity": inspection.get("publication_identity"),
                "final_remote_base_sha": final_remote_sha, "closure_identity": inspection.get("closure_identity"), "terminal_wake_receipt": terminal.get("receipt_digest"),
                "canary_inspection_result": inspection["status"], "deployment_bundle_digest": index["artifacts"]["deployment_manifest"]["digest"],
                "scheduler_install_command_digest": _digest_bytes(_bytes(command)), "scheduler_install_command": command,
                "scheduler_mutation_performed": False, "credentials_inspected": False, "terminal_status": STATUS_COMPLETED}
            receipt = dict(receipt_body); receipt["receipt_digest"] = bootstrap.digest(receipt_body)
            _write_once(receipt_path, receipt)
            state["completed_stages"].append("commissioning_completed"); state["receipt_digest"] = receipt["receipt_digest"]; _save_state(root, state)
            if stage_hook: stage_hook("commissioning_completed")
            return {"status": STATUS_COMPLETED, "receipt_path": str(receipt_path), "receipt_digest": receipt["receipt_digest"], "scheduler_mutation_performed": False, "credentials_inspected": False}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        return {"status": STATUS_BLOCKED, "reason_codes": [str(exc)], "scheduler_mutation_performed": False, "credentials_inspected": False}


def inspect(state_root: str | Path) -> dict[str, Any]:
    try:
        root = Path(state_root); state = _load(root / "commissioning-state.json")
        receipt = _load(root / "commissioning-receipt.json") if (root / "commissioning-receipt.json").exists() else None
        return {"status": "windows_commissioning_inspected", "state": state, "receipt": receipt, "scheduler_mutation_performed": False, "credentials_inspected": False}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": STATUS_BLOCKED, "reason_codes": [str(exc)], "scheduler_mutation_performed": False, "credentials_inspected": False}


def print_scheduler_install_command(state_root: str | Path) -> dict[str, Any]:
    try:
        receipt = _load(Path(state_root) / "commissioning-receipt.json")
        if receipt.get("terminal_status") != STATUS_COMPLETED: raise ValueError("commissioning_incomplete")
        command = receipt["scheduler_install_command"]
        if _digest_bytes(_bytes(command)) != receipt["scheduler_install_command_digest"]: raise ValueError("scheduler_command_digest_mismatch")
        return {"status": "windows_commissioning_scheduler_install_command_ready", **command, "scheduler_mutation_performed": False}
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"status": STATUS_BLOCKED, "reason_codes": [str(exc)], "scheduler_mutation_performed": False}


__all__ = ["doctor", "commission_once", "inspect", "print_scheduler_install_command", "STATUS_READY", "STATUS_BLOCKED", "STATUS_COMPLETED"]
