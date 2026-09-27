"""Operator-approved commissioning of one exact POSIX generation-zero resident.

This owner has no successor-selection or self-replacement authority.  Read-only
planning precedes an externally supplied approval and a separate control-plane
decision; only then can immutable external custody and one launch be attempted.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_authority_continuity as continuity
from sentientos import maintenance_resident_runtime_adoption as resident
from sentientos import maintenance_successor_generation_adoption as successor
from sentientos import maintenance_wake_daemon_adoption as wake
from sentientos.control_plane_kernel import (
    AdmissionOutcome, AuthorityClass, ControlActionRequest, ControlPlaneKernel,
    LifecyclePhase,
)

CAPABILITY = "maintenance_initial_posix_resident_commissioning"
PRINCIPAL = "deterministic_maintenance_initial_posix_resident_commissioning_controller"
ACTION = "commission_exact_initial_posix_resident"
MANIFEST_SCHEMA = "sentientos.maintenance_initial_posix_resident_commissioning_manifest:v1"
INTENT_SCHEMA = "sentientos.maintenance_initial_posix_resident_commissioning_intent:v1"
APPROVAL_SCHEMA = "sentientos.maintenance_initial_posix_resident_commissioning_approval:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_initial_posix_resident_commissioning_receipt:v1"
STARTUP_SCHEMA = "sentientos.maintenance_initial_posix_resident_startup_ready:v1"
STARTUP_GATE_ENV = "SENTIENTOS_INITIAL_RESIDENT_COMMISSIONING_INTENT"
STARTUP_ROOT_ENV = "SENTIENTOS_INITIAL_RESIDENT_COMMISSIONING_CUSTODY"
ZERO_DIGEST = "sha256:" + "0" * 64
EFFECTS = tuple(sorted((
    "exact_initial_resident_repository_state_read", "exact_posix_resident_host_capability_read",
    "exact_initial_maintenance_authority_profile_read", "bounded_initial_resident_commissioning_custody_write",
    "initial_maintenance_continuity_policy_write", "initial_maintenance_authority_generation_write",
    "initial_maintenance_wake_adoption_configuration_write",
    "maintenance_successor_generation_adoption_configuration_write",
    "maintenance_resident_runtime_adoption_configuration_write", "bounded_exact_initial_sentientosd_launch",
    "initial_resident_launch_provenance_write", "maintenance_initial_resident_commissioning_receipt_write",
    "read_only_maintenance_initial_resident_commissioning_health_projection",
)))
MANIFEST_FIELDS = {
    "schema_version", "repository_identity", "repository_root", "expected_commit", "expected_tree",
    "canonical_ref", "python_executable", "daemon_entrypoint", "custody_root", "profile_manifest_path",
    "profile_manifest_digest", "profile_bundle_digest", "initial_wake_adoption_path",
    "initial_wake_adoption_digest", "operator_reference", "approval_evidence_path", "lineage_id",
    "created_at", "stop_marker", "environment_allowlist", "required_environment",
    "maximum_handoffs", "maximum_successful_transitions", "maximum_wall_clock_seconds",
    "quiescence_timeout_seconds", "readiness_timeout_seconds", "launch_timeout_seconds", "manifest_digest",
}


class CommissioningError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code); self.code = code


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any, omitted: str | None = None) -> str:
    body = {k: v for k, v in value.items() if k != omitted} if omitted else value
    return "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()


def _load(path: str | Path, code: str) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file(): raise CommissioningError(code)
    try: value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise CommissioningError(code) from exc
    if not isinstance(value, dict): raise CommissioningError(code)
    return value


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if result.returncode: raise CommissioningError("repository_inspection_failed")
    return result.stdout.strip()


def validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    m = dict(value)
    if set(m) != MANIFEST_FIELDS or m.get("schema_version") != MANIFEST_SCHEMA:
        raise CommissioningError("commissioning_manifest_closed_schema_invalid")
    if m.get("manifest_digest") != digest(m, "manifest_digest"):
        raise CommissioningError("commissioning_manifest_digest_invalid")
    for key in ("repository_root", "python_executable", "daemon_entrypoint", "custody_root",
                "profile_manifest_path", "initial_wake_adoption_path", "stop_marker", "approval_evidence_path"):
        if not Path(str(m[key])).is_absolute(): raise CommissioningError(key + "_must_be_absolute")
    if m["environment_allowlist"] != sorted(set(m["environment_allowlist"])) or any(
            x in {"PYTHONPATH", "PYTHONHOME"} for x in m["environment_allowlist"]):
        raise CommissioningError("unbounded_initial_environment")
    if not isinstance(m["required_environment"], dict) or any(
            k in {"PYTHONPATH", "PYTHONHOME", resident.TRANSITION_ENV} or not isinstance(v, str)
            for k, v in m["required_environment"].items()):
        raise CommissioningError("unbounded_initial_environment")
    for key in ("maximum_handoffs", "maximum_successful_transitions", "maximum_wall_clock_seconds",
                "quiescence_timeout_seconds", "readiness_timeout_seconds", "launch_timeout_seconds"):
        if type(m[key]) not in (int, float) or m[key] <= 0: raise CommissioningError("invalid_commissioning_bound")
    return m


def load_manifest(path: str | Path) -> dict[str, Any]:
    return validate_manifest(_load(path, "commissioning_manifest_not_regular"))


def _unsafe_symlink(path: Path) -> bool:
    return path.is_symlink() or any(p.is_symlink() for p in path.parents if p.exists())


def doctor(value: Mapping[str, Any], *, platform_name: str | None = None) -> dict[str, Any]:
    """Inspect exact host/repository/profile inputs without filesystem mutation."""
    reasons: list[str] = []
    try: m = validate_manifest(value)
    except CommissioningError as exc:
        return {"schema_version": "sentientos.maintenance_initial_posix_resident_doctor:v1",
                "status": "initial_resident_commissioning_not_ready", "reason_codes": [exc.code], "read_only": True}
    posix = (os.name if platform_name is None else platform_name) == "posix"
    if not posix or not hasattr(fcntl, "flock"): reasons.append("posix_locking_required")
    repo = Path(m["repository_root"]); custody = Path(m["custody_root"])
    try:
        if _unsafe_symlink(repo) or repo.resolve(strict=True) != repo: reasons.append("repository_symlink_or_realpath_mismatch")
        if _git(repo, "rev-parse", "--show-toplevel") != str(repo): reasons.append("repository_root_mismatch")
        if _git(repo, "rev-parse", "HEAD") != m["expected_commit"]: reasons.append("repository_commit_mismatch")
        if _git(repo, "rev-parse", "HEAD^{tree}") != m["expected_tree"]: reasons.append("repository_tree_mismatch")
        if _git(repo, "status", "--porcelain=v1", "--untracked-files=all"): reasons.append("repository_dirty")
        if any((repo / ".git" / marker).exists() for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "rebase-apply", "rebase-merge")):
            reasons.append("ambiguous_git_operation")
        if _git(repo, "rev-parse", "--verify", m["canonical_ref"]) != m["expected_commit"]: reasons.append("canonical_ref_mismatch")
    except (OSError, CommissioningError): reasons.append("repository_inspection_failed")
    python = Path(m["python_executable"]); entrypoint = Path(m["daemon_entrypoint"])
    if not python.is_file() or str(python.resolve()) != str(python): reasons.append("python_executable_not_exact_realpath")
    if entrypoint != repo / "sentientosd.py" or not entrypoint.is_file() or entrypoint.is_symlink(): reasons.append("daemon_entrypoint_not_canonical")
    if _unsafe_symlink(custody): reasons.append("custody_symlink_unsafe")
    resolved_custody = custody.resolve(strict=False)
    if resolved_custody == repo or repo in resolved_custody.parents: reasons.append("custody_inside_repository")
    if custody.exists():
        if not custody.is_dir() or stat.S_IMODE(os.lstat(custody).st_mode) != 0o700: reasons.append("custody_root_unsafe")
        # Completed custody is an idempotent reconstruction candidate. Its exact
        # intent and artifact chain are checked by ``verify``/``commission``.
        if not (custody / "COMMISSIONED.json").exists() and any(custody.iterdir()):
            reasons.append("conflicting_commissioning_custody")
    elif not custody.parent.exists() or not os.access(custody.parent, os.W_OK): reasons.append("custody_parent_not_writable")
    try:
        profile = profiles.validate_manifest(_load(m["profile_manifest_path"], "profile_manifest_invalid"))
        checked = profiles.verify_profile_bundle(m["profile_manifest_path"], m["created_at"])
        if profile["manifest_digest"] != m["profile_manifest_digest"] or checked.get("bundle_digest") != m["profile_bundle_digest"]:
            reasons.append("initial_profile_binding_mismatch")
        if profile["repository_identity"] != m["repository_identity"] or profile["repository_root"] != str(repo) or profile["base_sha"] != m["expected_commit"]:
            reasons.append("initial_profile_repository_mismatch")
        initial_wake = wake.load_adoption(m["initial_wake_adoption_path"])
        if initial_wake["adoption_config_digest"] != m["initial_wake_adoption_digest"]: reasons.append("initial_wake_binding_mismatch")
    except (OSError, ValueError, CommissioningError): reasons.append("initial_profile_or_wake_invalid")
    return {"schema_version": "sentientos.maintenance_initial_posix_resident_doctor:v1",
            "status": "initial_resident_commissioning_ready" if not reasons else "initial_resident_commissioning_not_ready",
            "reason_codes": sorted(set(reasons)), "repository_commit": m["expected_commit"],
            "repository_tree": m["expected_tree"], "custody_root": str(resolved_custody), "read_only": True}


def prepare_intent(value: Mapping[str, Any]) -> dict[str, Any]:
    m = validate_manifest(value); report = doctor(m)
    launch = {"argv": [m["python_executable"], "-m", "sentientosd"], "cwd": m["repository_root"],
              "environment_allowlist": m["environment_allowlist"], "required_environment": m["required_environment"],
              "shell": False, "maximum_launches": 1}
    intent = {"schema_version": INTENT_SCHEMA, "intent_id": "", "intent_digest": "", "capability": CAPABILITY,
              "principal": PRINCIPAL, "effects": list(EFFECTS), "effects_digest": digest(list(EFFECTS)),
              "manifest": m, "manifest_digest": m["manifest_digest"], "host_doctor": report,
              "repository_identity": m["repository_identity"], "repository_commit": m["expected_commit"],
              "repository_tree": m["expected_tree"], "lineage_id": m["lineage_id"],
              "custody_root": m["custody_root"], "launch_contract": launch}
    intent["intent_digest"] = digest(intent, "intent_digest")
    intent["intent_id"] = "initial-resident-intent-" + intent["intent_digest"].split(":", 1)[1][:24]
    intent["intent_digest"] = digest(intent, "intent_digest")
    return intent


def approval_bindings(intent: Mapping[str, Any]) -> dict[str, Any]:
    return {k: intent[k] for k in ("intent_id", "intent_digest", "capability", "principal", "effects",
        "effects_digest", "repository_identity", "repository_commit", "repository_tree", "lineage_id", "custody_root", "launch_contract")}


def verify_approval(approval: Mapping[str, Any], intent: Mapping[str, Any], *, now: datetime | None = None,
                    allow_synthetic_for_tests: bool = False) -> dict[str, Any]:
    a = dict(approval); claimed = a.pop("approval_digest", None)
    if claimed != digest(a): raise CommissioningError("runtime_operator_approval_digest_invalid")
    a["approval_digest"] = claimed
    required = {"schema_version", "approval_id", "approval_digest", "source", "synthetic", "bindings",
                "operator_identity", "operator_provenance", "not_before", "expires_at"}
    if set(a) != required or a["schema_version"] != APPROVAL_SCHEMA or a["source"] != "external_operator":
        raise CommissioningError("runtime_operator_approval_invalid")
    if a["synthetic"] is True and not allow_synthetic_for_tests: raise CommissioningError("synthetic_runtime_approval_rejected")
    if a["synthetic"] not in ({False} if not allow_synthetic_for_tests else {False, True}): raise CommissioningError("runtime_operator_approval_invalid")
    if not isinstance(a["approval_id"], str) or not a["approval_id"].strip():
        raise CommissioningError("runtime_operator_approval_identity_invalid")
    if not isinstance(a["operator_identity"], str) or not a["operator_identity"].strip():
        raise CommissioningError("runtime_operator_identity_invalid")
    provenance = a["operator_provenance"]
    if (not isinstance(provenance, str) or not provenance.strip() or
            (not allow_synthetic_for_tests and any(token in provenance.lower() for token in ("placeholder", "synthetic", "test fixture")))):
        raise CommissioningError("runtime_operator_provenance_invalid")
    if a["bindings"] != approval_bindings(intent): raise CommissioningError("runtime_operator_approval_binding_mismatch")
    instant = now or datetime.now(timezone.utc)
    try:
        start = datetime.fromisoformat(str(a["not_before"]).replace("Z", "+00:00")); end = datetime.fromisoformat(str(a["expires_at"]).replace("Z", "+00:00"))
    except ValueError as exc: raise CommissioningError("runtime_operator_approval_time_invalid") from exc
    if not start <= instant < end: raise CommissioningError("runtime_operator_approval_expired_or_not_yet_valid")
    return a


def _write(path: Path, value: Mapping[str, Any]) -> None:
    data = canonical_bytes(value) + b"\n"; path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data: raise CommissioningError("immutable_commissioning_custody_conflict")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())


def _artifacts(intent: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    m = intent["manifest"]; root = Path(m["custody_root"]); profile = profiles.validate_manifest(_load(m["profile_manifest_path"], "profile_manifest_invalid"))
    policy = {"schema_version": continuity.POLICY_SCHEMA, "policy_id": m["lineage_id"] + ":policy", "policy_digest": "",
        "lineage_id": m["lineage_id"], "repository_identity": m["repository_identity"], "generation_root": str(root / "generations"),
        "receipt_root": str(root / "continuity-receipts"), "initial_generation_path": str(root / "generations/generation-0.json"),
        "operator_reference": m["operator_reference"], "approval_reference": "external-runtime-approval",
        "created_at": m["created_at"], "constraints": ["same_or_narrower", "local_fast_forward_base_ref", "no_runtime_adoption"]}
    policy["policy_digest"] = continuity.digest(policy, "policy_digest")
    generation = {"schema_version": continuity.GENERATION_SCHEMA, "generation_id": m["lineage_id"] + ":generation:0",
        "generation_digest": "", "lineage_id": m["lineage_id"], "ordinal": 0, "base_sha": m["expected_commit"],
        "manifest_path": m["profile_manifest_path"], "manifest_digest": profile["manifest_digest"],
        "profile_bundle_digest": m["profile_bundle_digest"], "predecessor_generation_digest": "", "prior_receipt_digest": "", "created_at": m["created_at"]}
    generation["generation_digest"] = continuity._generation_digest(generation)
    sc = {"schema_version": successor.CONFIG_SCHEMA, "enabled": True, "continuity_policy_path": str(root / "continuity-policy.json"),
        "continuity_policy_digest": policy["policy_digest"], "initial_generation_path": policy["initial_generation_path"],
        "initial_generation_digest": generation["generation_digest"], "initial_wake_adoption_path": m["initial_wake_adoption_path"],
        "initial_wake_adoption_digest": m["initial_wake_adoption_digest"], "repository_identity": m["repository_identity"],
        "repository_root": m["repository_root"], "state_root": str(root / "successor-state"),
        "successor_configuration_root": str(root / "successor-configurations"), "handoff_journal_path": str(root / "successor-state/handoffs.jsonl"),
        "stop_marker": str(root / "successor-state/STOP"), "observation_delay_seconds": 1, "maximum_handoffs": int(m["maximum_handoffs"]),
        "maximum_wall_clock_seconds": int(m["maximum_wall_clock_seconds"]), "shutdown_timeout_seconds": float(m["quiescence_timeout_seconds"])}
    sc["config_digest"] = successor.digest(sc)
    rc_path = root / "resident-adoption.json"
    required = dict(m["required_environment"]); required.update({resident.CONFIG_ENV: str(rc_path), resident.SUCCESSOR_CONFIG_ENV: str(root / "successor-adoption.json")})
    rc = {"schema_version": resident.CONFIG_SCHEMA, "enabled": True, "continuity_policy_path": str(root / "continuity-policy.json"),
        "continuity_policy_digest": policy["policy_digest"], "successor_adoption_config_path": str(root / "successor-adoption.json"),
        "successor_adoption_config_digest": sc["config_digest"], "automatic_continuity_config_path": "", "automatic_continuity_config_digest": "",
        "repository_identity": m["repository_identity"], "repository_root": m["repository_root"], "python_executable": m["python_executable"],
        "daemon_module": "sentientosd", "daemon_entrypoint": m["daemon_entrypoint"], "working_directory": m["repository_root"],
        "inherited_environment_allowlist": m["environment_allowlist"], "required_environment": required, "state_root": str(root / "resident-state"),
        "transition_journal_path": str(root / "resident-state/transitions.jsonl"), "provenance_root": str(root / "resident-state/provenance"),
        "receipt_root": str(root / "resident-state/receipts"), "stop_marker": m["stop_marker"],
        "quiescence_timeout_seconds": m["quiescence_timeout_seconds"], "readiness_timeout_seconds": m["readiness_timeout_seconds"],
        "maximum_successful_transitions": int(m["maximum_successful_transitions"]), "maximum_wall_clock_seconds": m["maximum_wall_clock_seconds"], "config_digest": ""}
    rc["config_digest"] = resident.digest(rc, "config_digest")
    return {"policy": policy, "generation": generation, "successor": sc, "resident": rc}


def _verify_custody(root: Path, intent: Mapping[str, Any], *, require_complete: bool) -> dict[str, Any]:
    paths = {"manifest": root / "manifest.json", "intent": root / "intent.json", "approval": root / "approval.json",
             "policy": root / "continuity-policy.json", "generation": root / "generations/generation-0.json",
             "successor": root / "successor-adoption.json", "resident": root / "resident-adoption.json", "receipt": root / "commissioning-receipt.json"}
    if require_complete and not (root / "COMMISSIONED.json").is_file(): raise CommissioningError("commissioning_incomplete")
    if _load(paths["manifest"], "commissioning_manifest_missing") != intent["manifest"] or _load(paths["intent"], "commissioning_intent_missing") != intent:
        raise CommissioningError("commissioning_intent_conflict")
    policy = continuity.validate_policy(_load(paths["policy"], "continuity_policy_missing"))
    generation = continuity.validate_generation(_load(paths["generation"], "generation_zero_missing"), policy)
    sc = successor.load_config(paths["successor"]); rc = resident.load_config(paths["resident"])
    result = {"policy_digest": policy["policy_digest"], "generation_digest": generation["generation_digest"],
              "successor_config_digest": sc["config_digest"], "resident_config_digest": rc["config_digest"]}
    if require_complete:
        receipt = _load(paths["receipt"], "commissioning_receipt_missing"); claimed = receipt.pop("receipt_digest", None)
        if claimed != digest(receipt): raise CommissioningError("commissioning_receipt_tampered")
        receipt["receipt_digest"] = claimed
        approval = _load(paths["approval"], "runtime_operator_approval_missing"); approval_claim = approval.pop("approval_digest", None)
        if approval_claim != digest(approval) or approval_claim != receipt["approval_digest"]:
            raise CommissioningError("runtime_operator_approval_tampered")
        approval["approval_digest"] = approval_claim
        if approval.get("bindings") != approval_bindings(intent): raise CommissioningError("runtime_operator_approval_binding_mismatch")
        decision = _load(root / "control-plane-decision.json", "control_plane_decision_missing")
        if digest(decision) != receipt["control_plane_decision_digest"]:
            raise CommissioningError("control_plane_decision_tampered")
        marker = _load(root / "COMMISSIONED.json", "commissioning_marker_invalid")
        if (marker.get("receipt_digest") != claimed or marker.get("status") != "initial_resident_commissioned" or
                marker.get("intent_digest") != intent["intent_digest"] or
                marker.get("process_instance_id") != receipt["launch_provenance"].get("process_instance_id")):
            raise CommissioningError("commissioning_marker_invalid")
        provenance = _load(root / "launch-provenance.json", "initial_launch_provenance_invalid")
        if (provenance != receipt["launch_provenance"] or
                provenance.get("provenance_digest") != resident.digest(provenance, "provenance_digest")):
            raise CommissioningError("initial_launch_provenance_tampered")
        result.update(receipt_digest=claimed, launch_provenance=receipt["launch_provenance"])
    return result


def verify(value: Mapping[str, Any]) -> dict[str, Any]:
    intent = prepare_intent(value); root = Path(intent["custody_root"])
    try: details = _verify_custody(root, intent, require_complete=True)
    except CommissioningError as exc: return {"status": "initial_resident_commissioning_not_verified", "reason_codes": [exc.code], "read_only": True}
    return {"status": "initial_resident_commissioning_verified", **details, "read_only": True}


def _environment(intent: Mapping[str, Any], resident_config: Mapping[str, Any]) -> dict[str, str]:
    m = intent["manifest"]
    env = {k: os.environ[k] for k in m["environment_allowlist"] if k in os.environ}
    env.update(resident_config["required_environment"])
    env[STARTUP_GATE_ENV] = intent["intent_digest"]
    env[STARTUP_ROOT_ENV] = m["custody_root"]
    env.pop("PYTHONPATH", None); env.pop("PYTHONHOME", None)
    return env


def _startup_environment_digest(env: Mapping[str, str]) -> str:
    return digest(dict(sorted(env.items())))


def await_initial_commissioning_gate(provenance: Mapping[str, Any]) -> None:
    """Child-side, initial-launch-only gate; returns only after exact completion."""
    intent_digest = os.environ.get(STARTUP_GATE_ENV); root_text = os.environ.get(STARTUP_ROOT_ENV)
    if not intent_digest and not root_text:
        return
    if not intent_digest or not root_text:
        raise CommissioningError("initial_commissioning_gate_context_incomplete")
    root = Path(root_text)
    intent = _load(root / "intent.json", "initial_commissioning_intent_missing")
    manifest = validate_manifest(intent.get("manifest", {}))
    if (intent.get("intent_digest") != intent_digest or root.resolve() != Path(manifest["custody_root"]).resolve()):
        raise CommissioningError("initial_commissioning_gate_context_mismatch")
    resident_config = resident.load_config(root / "resident-adoption.json")
    bounded_env = {key: os.environ[key] for key in manifest["environment_allowlist"] if key in os.environ}
    bounded_env.update({key: os.environ[key] for key in resident_config["required_environment"]})
    bounded_env[STARTUP_GATE_ENV] = intent_digest; bounded_env[STARTUP_ROOT_ENV] = root_text
    ready = {"schema_version": STARTUP_SCHEMA, "intent_digest": intent_digest,
             "resident_config_digest": provenance.get("config_digest"),
             "generation_ordinal": provenance.get("represented_generation_ordinal"),
             "generation_digest": provenance.get("represented_generation_digest"),
             "provenance_digest": provenance.get("provenance_digest"), "pid": os.getpid(),
             "process_instance_id": provenance.get("process_instance_id"),
             "environment_digest": _startup_environment_digest(bounded_env), "startup_ready_digest": ""}
    ready["startup_ready_digest"] = digest(ready, "startup_ready_digest")
    _write(root / "startup-ready.json", ready)
    deadline = time.monotonic() + float(manifest["launch_timeout_seconds"])
    while time.monotonic() < deadline:
        marker_path = root / "COMMISSIONED.json"
        if marker_path.is_file():
            marker = _load(marker_path, "commissioning_marker_invalid")
            receipt = _load(root / "commissioning-receipt.json", "commissioning_receipt_missing")
            if (marker.get("status") == "initial_resident_commissioned" and
                    marker.get("intent_digest") == intent_digest and
                    marker.get("receipt_digest") == receipt.get("receipt_digest") and
                    marker.get("process_instance_id") == provenance.get("process_instance_id") and
                    receipt.get("launch_provenance_digest") == provenance.get("provenance_digest")):
                return
            raise CommissioningError("commissioning_marker_invalid")
        time.sleep(0.05)
    raise CommissioningError("initial_commissioning_gate_timeout")


def commission(value: Mapping[str, Any], approval: Mapping[str, Any], *, kernel: ControlPlaneKernel,
               correlation_id: str, clock: Callable[[], datetime] | None = None,
               launch_runner: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
               allow_synthetic_approval_for_tests: bool = False,
               approval_evidence_path: str | Path | None = None) -> dict[str, Any]:
    intent = prepare_intent(value); m = intent["manifest"]; root = Path(m["custody_root"])
    if (root / "COMMISSIONED.json").exists():
        details = _verify_custody(root, intent, require_complete=True)
        return {"status": "initial_resident_commissioning_reconstructed", **details, "initial_launch_performed": False}
    if intent["host_doctor"]["status"] != "initial_resident_commissioning_ready":
        raise CommissioningError("host_doctor_not_ready")
    expected_approval_path = Path(m["approval_evidence_path"]).resolve()
    if not allow_synthetic_approval_for_tests:
        if approval_evidence_path is not None and Path(approval_evidence_path).resolve() != expected_approval_path:
            raise CommissioningError("runtime_operator_approval_path_mismatch")
        if expected_approval_path.is_symlink() or not expected_approval_path.is_file():
            raise CommissioningError("runtime_operator_approval_path_invalid")
        if _load(expected_approval_path, "runtime_operator_approval_path_invalid") != dict(approval):
            raise CommissioningError("runtime_operator_approval_bytes_mismatch")
    approved = verify_approval(approval, intent, now=(clock or (lambda: datetime.now(timezone.utc)))(), allow_synthetic_for_tests=allow_synthetic_approval_for_tests)
    metadata = {**approval_bindings(intent), "approval_id": approved["approval_id"], "approval_digest": approved["approval_digest"], "correlation_id": correlation_id}
    decision = kernel.admit(ControlActionRequest(ACTION, AuthorityClass.INITIAL_RESIDENT_COMMISSIONING, PRINCIPAL,
        CAPABILITY, LifecyclePhase.RUNTIME, metadata))
    if decision.outcome != AdmissionOutcome.ALLOW or decision.authority_class != AuthorityClass.INITIAL_RESIDENT_COMMISSIONING or decision.actor != PRINCIPAL:
        raise CommissioningError("initial_resident_control_plane_admission_denied")
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        if root.is_symlink() or not root.is_dir() or any(root.iterdir()): raise CommissioningError("conflicting_commissioning_custody")
    _write(root / "INCOMPLETE.json", {"intent_digest": intent["intent_digest"], "status": "commissioning_incomplete"})
    for directory in (root / "generations", root / "continuity-receipts", root / "successor-state", root / "successor-configurations", root / "resident-state"):
        directory.mkdir(mode=0o700, exist_ok=True)
    artifacts = _artifacts(intent)
    decision_record = decision.to_dict()
    for path, data in ((root / "manifest.json", m), (root / "intent.json", intent), (root / "approval.json", approved),
                       (root / "control-plane-decision.json", decision_record), (root / "continuity-policy.json", artifacts["policy"]),
                       (root / "generations/generation-0.json", artifacts["generation"]), (root / "successor-adoption.json", artifacts["successor"]),
                       (root / "resident-adoption.json", artifacts["resident"])): _write(path, data)
    _verify_custody(root, intent, require_complete=False)
    if launch_runner is not None:
        if not allow_synthetic_approval_for_tests: raise CommissioningError("test_launch_adapter_rejected_in_production")
        provenance = dict(launch_runner(artifacts["resident"]))
    else:
        env = _environment(intent, artifacts["resident"])
        child = subprocess.Popen(intent["launch_contract"]["argv"], cwd=m["repository_root"], env=env,
            shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        deadline = time.monotonic() + float(m["launch_timeout_seconds"]); ready = None
        while time.monotonic() < deadline:
            if child.poll() is not None: raise CommissioningError("bounded_initial_launch_failed")
            if (root / "startup-ready.json").is_file():
                ready = _load(root / "startup-ready.json", "initial_startup_ready_invalid"); break
            time.sleep(0.05)
        if ready is None: raise CommissioningError("bounded_initial_launch_timeout")
        candidates = sorted((root / "resident-state/provenance").glob("generation-0/*.json"))
        if len(candidates) != 1: raise CommissioningError("initial_launch_provenance_missing_or_ambiguous")
        provenance = _load(candidates[0], "initial_launch_provenance_invalid")
        expected_ready = {"schema_version": STARTUP_SCHEMA, "intent_digest": intent["intent_digest"],
            "resident_config_digest": artifacts["resident"]["config_digest"],
            "generation_ordinal": 0, "generation_digest": artifacts["generation"]["generation_digest"],
            "provenance_digest": provenance.get("provenance_digest"), "pid": child.pid,
            "process_instance_id": provenance.get("process_instance_id"),
            "environment_digest": _startup_environment_digest(env), "startup_ready_digest": ready.get("startup_ready_digest")}
        if (ready != expected_ready or ready.get("startup_ready_digest") != digest(ready, "startup_ready_digest") or
                provenance.get("pid") != child.pid or provenance.get("represented_generation_ordinal") != 0 or
                provenance.get("represented_generation_digest") != artifacts["generation"]["generation_digest"] or
                provenance.get("observed_commit_sha") != m["expected_commit"] or provenance.get("observed_tree_sha") != m["expected_tree"] or
                provenance.get("config_digest") != artifacts["resident"]["config_digest"] or child.poll() is not None):
            raise CommissioningError("initial_launch_provenance_binding_mismatch")
    provenance_digest = provenance.get("provenance_digest")
    if not isinstance(provenance_digest, str) or provenance_digest != resident.digest(provenance, "provenance_digest"):
        raise CommissioningError("initial_launch_provenance_invalid")
    _write(root / "launch-provenance.json", provenance)
    receipt = {"schema_version": RECEIPT_SCHEMA, "status": "initial_resident_commissioned", "receipt_digest": "",
        "manifest_digest": m["manifest_digest"], "intent_digest": intent["intent_digest"], "approval_id": approved["approval_id"],
        "approval_digest": approved["approval_digest"], "control_plane_decision_ref": decision.admission_decision_ref,
        "control_plane_decision_digest": digest(decision_record),
        "repository_commit": m["expected_commit"], "repository_tree": m["expected_tree"], "host_doctor": intent["host_doctor"],
        "profile_manifest_digest": m["profile_manifest_digest"], "profile_bundle_digest": m["profile_bundle_digest"],
        "continuity_policy_digest": artifacts["policy"]["policy_digest"], "generation_zero_digest": artifacts["generation"]["generation_digest"],
        "initial_wake_adoption_digest": m["initial_wake_adoption_digest"], "successor_adoption_config_digest": artifacts["successor"]["config_digest"],
        "resident_adoption_config_digest": artifacts["resident"]["config_digest"], "launch_provenance": provenance,
        "launch_provenance_digest": provenance_digest, "effects": list(EFFECTS), "initial_launch_performed": True,
        "successor_generation_created": False, "successor_resident_replacement_performed": False,
        "git_mutation_or_publication_performed": False, "network_or_provider_operation_performed": False, "authority_widened": False}
    receipt["receipt_digest"] = digest(receipt, "receipt_digest"); _write(root / "commissioning-receipt.json", receipt)
    _write(root / "COMMISSIONED.json", {"receipt_digest": receipt["receipt_digest"], "status": "initial_resident_commissioned",
        "intent_digest": intent["intent_digest"], "process_instance_id": provenance.get("process_instance_id")})
    (root / "INCOMPLETE.json").unlink()
    return {"status": "initial_resident_commissioned", "receipt_digest": receipt["receipt_digest"],
            "generation_digest": artifacts["generation"]["generation_digest"], "launch_provenance": provenance,
            "initial_launch_performed": True}
