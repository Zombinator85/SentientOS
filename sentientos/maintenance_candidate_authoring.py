"""Operator authoring and inert enqueue custody for maintenance candidates."""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping, cast

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_candidate as candidates
from sentientos import maintenance_candidate_selector as selector
from sentientos import maintenance_loop_activation as activation
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import maintenance_task_journal as journal
from sentientos import maintenance_validation_controller as validation

MANIFEST_SCHEMA = "sentientos.maintenance_candidate_authoring_manifest:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_candidate_authoring_receipt:v1"
VERIFY_SCHEMA = "sentientos.maintenance_candidate_authoring_verification:v1"
ENQUEUE_SCHEMA = "sentientos.maintenance_candidate_enqueue_receipt:v1"
ZERO_DIGEST = "sha256:" + "0" * 64
REQUIRED = {
    "schema_version", "template_no_authority", "manifest_digest", "source_reference",
    "repository_identity", "base_sha", "objective", "bounded_description", "candidate_kind",
    "severity", "confidence", "subject_paths", "validation_expectations", "evidence_references",
    "requested_authority_classes", "constraints", "estimated_file_count",
    "estimated_changed_lines", "estimated_implementation_seconds", "estimated_validation_seconds",
    "operator_priority", "activation_profile_bundle_path", "watchdog_configuration_path",
    "candidate_inbox_path", "intended_output_path",
}
SECRET = re.compile(r"(?:credential|secret|password|token|api[_-]?key|private[_-]?key)", re.I)
SHELL = re.compile(r"(?:^command$|shell|argv|executable|(?:^|_)script(?:_|$))", re.I)
ENVIRONMENT = re.compile(r"(?:^env$|environment)", re.I)
PLACEHOLDER = re.compile(r"(?:REPLACE|PLACEHOLDER|CHOOSE)", re.I)


def canonical_bytes(value: Any) -> bytes:
    return profiles.canonical_bytes(value)


def _load(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("input_not_regular")
    return cast(dict[str, Any], json.loads(p.read_text(encoding="utf-8")))


def _unsafe_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(SECRET.search(str(k)) or SHELL.search(str(k)) or ENVIRONMENT.search(str(k)) or _unsafe_key(v) for k, v in value.items())
    return isinstance(value, list) and any(_unsafe_key(v) for v in value)


def manifest_template() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA, "template_no_authority": True, "manifest_digest": "",
        "source_reference": "REPLACE_SOURCE_REFERENCE", "repository_identity": "REPLACE_REPOSITORY_IDENTITY",
        "base_sha": "REPLACE_WITH_EXACT_40_HEX_SHA", "objective": "REPLACE_OBJECTIVE",
        "bounded_description": "REPLACE_BOUNDED_DESCRIPTION", "candidate_kind": "REPLACE_CANDIDATE_KIND",
        "severity": "REPLACE_SEVERITY", "confidence": "REPLACE_CONFIDENCE",
        "subject_paths": ["REPLACE/RELATIVE_PATH"], "validation_expectations": ["pytest_node:tests/REPLACE.py::test_REPLACE"],
        "evidence_references": ["REPLACE_EVIDENCE_REFERENCE"], "requested_authority_classes": ["REPLACE_EACH_AUTHORITY_CLASS"],
        "constraints": ["REPLACE_EXPLICIT_CONSTRAINT"], "estimated_file_count": 0,
        "estimated_changed_lines": 0, "estimated_implementation_seconds": 0,
        "estimated_validation_seconds": 0, "operator_priority": 0,
        "activation_profile_bundle_path": "/REPLACE/PROFILE_MANIFEST.json",
        "watchdog_configuration_path": "/REPLACE/maintenance_loop_config.json",
        "candidate_inbox_path": "/REPLACE/INBOX", "intended_output_path": "/REPLACE/AUTHORING_OUTPUT",
    }
    value["manifest_digest"] = candidates.digest({k: v for k, v in value.items() if k != "manifest_digest"})
    return value


def validate_manifest(value: Mapping[str, Any], *, production: bool = True) -> dict[str, Any]:
    m = dict(value)
    if set(m) != REQUIRED or m.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("manifest_closed_schema_invalid")
    if _unsafe_key(m): raise ValueError("credential_shell_or_environment_field_forbidden")
    if m.get("manifest_digest") != candidates.digest({k: v for k, v in m.items() if k != "manifest_digest"}): raise ValueError("manifest_digest_invalid")
    if production and (m.get("template_no_authority") is not False or PLACEHOLDER.search(canonical_bytes(m).decode())): raise ValueError("template_has_no_authority")
    if not str(m["objective"]).strip(): raise ValueError("objective_required")
    for key in ("subject_paths", "validation_expectations", "evidence_references", "requested_authority_classes", "constraints"):
        if not isinstance(m[key], list) or not m[key] or any(not str(v).strip() for v in m[key]): raise ValueError(key + "_explicit_nonempty_required")
    for raw in m["subject_paths"]:
        p = Path(str(raw))
        if p.is_absolute() or ".." in p.parts: raise ValueError("unsafe_subject_path")
    auth = m["requested_authority_classes"]
    if len(auth) != len(set(auth)) or any(a not in candidates.AUTHORITY_CLASSES for a in auth) or any(str(a).lower() in {"all", "all_authority", "*"} for a in auth): raise ValueError("authority_classes_invalid")
    if m["severity"] not in candidates.SEVERITIES or m["confidence"] not in candidates.CONFIDENCES: raise ValueError("severity_or_confidence_invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", str(m["base_sha"])): raise ValueError("base_sha_invalid")
    for key in ("estimated_file_count", "estimated_changed_lines", "estimated_implementation_seconds", "estimated_validation_seconds"):
        if not isinstance(m[key], int) or m[key] < 1: raise ValueError(key + "_invalid")
    if not isinstance(m["operator_priority"], int): raise ValueError("operator_priority_invalid")
    for key in ("activation_profile_bundle_path", "watchdog_configuration_path", "candidate_inbox_path", "intended_output_path"):
        if not Path(str(m[key])).is_absolute(): raise ValueError(key + "_must_be_absolute")
    return m


def _external(path: str | Path, repository_root: str | Path) -> Path:
    raw = Path(path)
    repo = Path(repository_root).resolve(strict=True)
    if raw.is_symlink() or any(p.is_symlink() for p in [raw, *raw.parents] if p.exists()): raise ValueError("external_path_symlink")
    resolved = raw.resolve(strict=False)
    if resolved == repo or repo in resolved.parents or resolved == repo / ".git" or (repo / ".git") in resolved.parents: raise ValueError("external_path_inside_repository")
    return resolved


def _write(path: Path, data: bytes) -> str:
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data: raise ValueError("immutable_output_conflict")
        return "reused"
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.is_symlink(): raise ValueError("output_parent_symlink")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    return "created"


def write_candidate_template(path: str | Path) -> dict[str, Any]:
    p = Path(path); status = _write(p, canonical_bytes(manifest_template()) + b"\n")
    return {"schema_version": MANIFEST_SCHEMA, "status": "template_no_authority", "output_path": str(p.resolve()), "write_status": status}


def render_candidate(manifest_path: str | Path) -> dict[str, Any]:
    m = validate_manifest(_load(manifest_path)); profile = profiles.inspect_profile_bundle(m["activation_profile_bundle_path"], _profile_time(m))
    profile_verification = profiles.verify_profile_bundle(m["activation_profile_bundle_path"], _profile_time(m))
    repo_root = profile["manifest"]["repository_root"]
    output = _external(m["intended_output_path"], repo_root); output.mkdir(parents=True, mode=0o700, exist_ok=True)
    record = {"source_reference": m["source_reference"], "base_repository_sha": m["base_sha"], "objective": m["objective"],
        "bounded_description": m["bounded_description"], "candidate_kind": m["candidate_kind"], "severity": m["severity"],
        "confidence": m["confidence"], "declared_subject_paths": m["subject_paths"], "declared_validation_expectations": m["validation_expectations"],
        "evidence_references": m["evidence_references"], "requested_authority_classes": m["requested_authority_classes"],
        "declared_constraints": m["constraints"], "estimated_file_count": m["estimated_file_count"],
        "estimated_changed_line_count": m["estimated_changed_lines"], "estimated_implementation_seconds": m["estimated_implementation_seconds"],
        "estimated_validation_seconds": m["estimated_validation_seconds"], "operator_priority": m["operator_priority"]}
    candidate = candidates.adapt_explicit_candidate(record, base_repository_sha=m["base_sha"])
    stem = candidate.candidate_id + "--" + candidate.candidate_revision_digest.removeprefix("sha256:")
    candidate_path = output / (stem + ".json"); candidate_data = candidate.canonical_bytes() + b"\n"
    receipt = {"schema_version": RECEIPT_SCHEMA, "candidate_id": candidate.candidate_id,
        "candidate_revision_digest": candidate.candidate_revision_digest, "manifest_digest": m["manifest_digest"],
        "candidate_bytes_digest": profiles.bytes_digest(candidate_data), "canonical_candidate_digest": candidate.canonical_candidate_digest,
        "profile_bundle_digest": profile_verification["bundle_digest"], "repository_identity": m["repository_identity"], "receipt_digest": ""}
    receipt["receipt_digest"] = candidates.digest({k: v for k, v in receipt.items() if k != "receipt_digest"})
    receipt_path = output / (stem + ".authoring-receipt.json")
    cs = _write(candidate_path, candidate_data); rs = _write(receipt_path, canonical_bytes(receipt) + b"\n")
    return {"schema_version": RECEIPT_SCHEMA, "status": "candidate_rendered", "candidate_path": str(candidate_path), "receipt_path": str(receipt_path), "candidate_id": candidate.candidate_id, "candidate_revision_digest": candidate.candidate_revision_digest, "write_statuses": {"candidate": cs, "receipt": rs}}


def _profile_time(m: Mapping[str, Any]) -> str:
    profile = _load(m["activation_profile_bundle_path"])
    return str(profile["not_before"])


def _reasoned_verify(manifest_path: str | Path, candidate_path: str | Path, receipt_path: str | Path, evaluation_time: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    reasons: list[str] = []
    try:
        m = validate_manifest(_load(manifest_path)); pv = profiles.verify_profile_bundle(m["activation_profile_bundle_path"], evaluation_time)
        if pv["status"] != "profile_bundle_ready": raise ValueError("profile_bundle_not_ready")
        inspection = profiles.inspect_profile_bundle(m["activation_profile_bundle_path"], evaluation_time); pm = inspection["manifest"]
        cfg = watchdog.load_config(m["watchdog_configuration_path"]); cp = Path(candidate_path); rp = Path(receipt_path)
        raw = cp.read_bytes(); cdict = _load(cp); receipt = _load(rp); candidate = selector.candidate_from_dict(cdict)
        adapted = candidates.adapt_explicit_candidate({"source_reference": candidate.source_reference, "base_repository_sha": candidate.base_repository_sha,
            "objective": candidate.objective, "bounded_description": candidate.bounded_description, "candidate_kind": candidate.candidate_kind,
            "severity": candidate.severity, "confidence": candidate.confidence, "recurrence_count": candidate.recurrence_count,
            "declared_subject_paths": candidate.declared_subject_paths, "declared_validation_expectations": candidate.declared_validation_expectations,
            "evidence_references": candidate.evidence_references, "requested_authority_classes": candidate.requested_authority_classes,
            "declared_constraints": candidate.declared_constraints, "estimated_file_count": candidate.estimated_file_count,
            "estimated_changed_line_count": candidate.estimated_changed_line_count, "estimated_implementation_seconds": candidate.estimated_implementation_seconds,
            "estimated_validation_seconds": candidate.estimated_validation_seconds, "operator_priority": candidate.operator_priority}, base_repository_sha=m["base_sha"])
        if adapted.to_dict() != candidate.to_dict() or candidate.lifecycle_disposition != "candidate_ready": reasons.append("canonical_candidate_invalid")
        if m["repository_identity"] != pm["repository_identity"] or m["base_sha"] != pm["base_sha"] or candidate.base_repository_sha != pm["base_sha"]: reasons.append("repository_or_base_mismatch")
        policy = selector.build_policy(_load(Path(inspection["manifest"]["output_directory"]) / profiles.FILENAMES["selector_policy"]))
        selection = selector.select_candidate({"schema_version": candidates.CANDIDATE_SET_SCHEMA, "canonical_candidates": [candidate.to_dict()], "aggregate_digest": candidates.digest([candidate.to_dict()])}, policy, journal_state_root=cfg["state_root"])
        if selection["result_status"] != "ready_for_scope_admission": reasons.extend(selection.get("ineligible_candidate_ids", {}).get(candidate.candidate_id, [selection["result_status"]]))
        grant = _load(Path(inspection["manifest"]["output_directory"]) / profiles.FILENAMES["standing_grant"])
        if set(candidate.requested_authority_classes) - set(grant["allowed_authority_classes"]): reasons.append("grant_authority_unavailable")
        vp = validation.ValidationPolicy.from_mapping(_load(Path(inspection["manifest"]["output_directory"]) / profiles.FILENAMES["validation_policy"]))
        allowed = set(vp.to_dict()["allowed_expectation_kinds"])
        for exp in candidate.declared_validation_expectations:
            kind, _ = validation.validate_expectation(exp, candidate.declared_subject_paths, candidate.declared_subject_paths)
            if kind not in allowed: reasons.append("validation_expectation_not_allowed")
        if not candidate.evidence_references or not candidate.declared_constraints: reasons.append("evidence_or_constraints_missing")
        if cfg["base_sha"] != m["base_sha"] or cfg["candidate_inbox_roots"] != [str(Path(m["candidate_inbox_path"]).resolve())]: reasons.append("activation_configuration_mismatch")
        expected_receipt = dict(receipt); rd = expected_receipt.pop("receipt_digest", None)
        if receipt.get("schema_version") != RECEIPT_SCHEMA or rd != candidates.digest(expected_receipt) or receipt.get("manifest_digest") != m["manifest_digest"] or receipt.get("candidate_bytes_digest") != profiles.bytes_digest(raw) or receipt.get("canonical_candidate_digest") != candidate.canonical_candidate_digest or receipt.get("profile_bundle_digest") != pv["bundle_digest"]: reasons.append("authoring_receipt_mismatch")
        expected_name = candidate.candidate_id + "--" + candidate.candidate_revision_digest.removeprefix("sha256:") + ".json"
        if cp.name != expected_name: reasons.append("candidate_filename_invalid")
        context = {"manifest": m, "candidate": candidate.to_dict(), "candidate_path": str(cp.resolve()), "receipt_path": str(rp.resolve()), "profile": inspection, "profile_bundle_digest": pv["bundle_digest"], "config": cfg, "verification_receipt": receipt}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        reasons.append(str(exc)); context = None
    result = {"schema_version": VERIFY_SCHEMA, "status": "candidate_blocked" if reasons else "candidate_ready_for_inbox", "reason_codes": sorted(set(reasons))}
    if context:
        result.update({"candidate_id": context["candidate"]["candidate_id"], "candidate_revision_digest": context["candidate"]["candidate_revision_digest"], "profile_bundle_digest": context["profile_bundle_digest"], "candidate_bytes_digest": profiles.bytes_digest(Path(context["candidate_path"]).read_bytes())})
    result["verification_digest"] = candidates.digest(result)
    return result, context


def verify_candidate(manifest_path: str | Path, candidate_path: str | Path, receipt_path: str | Path, evaluation_time: str) -> dict[str, Any]:
    return _reasoned_verify(manifest_path, candidate_path, receipt_path, evaluation_time)[0]


def enqueue_candidate(manifest_path: str | Path, candidate_path: str | Path, receipt_path: str | Path, evaluation_time: str) -> dict[str, Any]:
    verified, ctx = _reasoned_verify(manifest_path, candidate_path, receipt_path, evaluation_time)
    if verified["status"] != "candidate_ready_for_inbox" or ctx is None: return verified
    m = ctx["manifest"]; inbox = _external(m["candidate_inbox_path"], ctx["profile"]["manifest"]["repository_root"])
    if inbox.is_symlink() or not inbox.is_dir(): raise ValueError("candidate_inbox_unsafe")
    destination = inbox / Path(ctx["candidate_path"]).name; status = _write(destination, Path(ctx["candidate_path"]).read_bytes())
    log = Path(ctx["config"]["state_root"]) / "maintenance_candidate_enqueue_receipts.jsonl"
    prior = [] if not log.exists() else [json.loads(line) for line in log.read_text().splitlines() if line]
    existing = next((r for r in prior if r.get("candidate_revision_digest") == ctx["candidate"]["candidate_revision_digest"]), None)
    if existing:
        if existing.get("candidate_bytes_digest") != verified["candidate_bytes_digest"]: raise ValueError("enqueue_receipt_conflict")
        return {**existing, "write_status": "reused"}
    receipt = {"schema_version": ENQUEUE_SCHEMA, "status": "candidate_enqueued", "sequence": len(prior) + 1,
        "previous_receipt_digest": prior[-1]["enqueue_receipt_digest"] if prior else ZERO_DIGEST,
        "candidate_id": ctx["candidate"]["candidate_id"], "candidate_revision_digest": ctx["candidate"]["candidate_revision_digest"],
        "candidate_bytes_digest": verified["candidate_bytes_digest"], "verification_digest": verified["verification_digest"],
        "inbox_path": str(inbox), "destination_path": str(destination), "enqueue_receipt_digest": ""}
    receipt["enqueue_receipt_digest"] = candidates.digest({k: v for k, v in receipt.items() if k != "enqueue_receipt_digest"})
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle: handle.write(canonical_bytes(receipt).decode() + "\n"); handle.flush(); os.fsync(handle.fileno())
    return {**receipt, "write_status": status}


def inspect_candidate(manifest_path: str | Path, candidate_path: str | Path, receipt_path: str | Path, evaluation_time: str) -> dict[str, Any]:
    verification, ctx = _reasoned_verify(manifest_path, candidate_path, receipt_path, evaluation_time)
    if ctx is None: return verification
    c = ctx["candidate"]; log = Path(ctx["config"]["state_root"]) / "maintenance_candidate_enqueue_receipts.jsonl"
    enqueues = [] if not log.exists() else [json.loads(x) for x in log.read_text().splitlines() if x]
    return {"schema_version": "sentientos.maintenance_candidate_authoring_inspection:v1", "status": verification["status"],
        "objective": c["objective"], "candidate_identity": {"candidate_id": c["candidate_id"], "revision_digest": c["candidate_revision_digest"]},
        "base_sha": c["base_repository_sha"], "paths": c["declared_subject_paths"], "validations": c["declared_validation_expectations"],
        "authority": c["requested_authority_classes"], "constraints": c["declared_constraints"], "budgets": {k: c[k] for k in ("estimated_file_count", "estimated_changed_line_count", "estimated_implementation_seconds", "estimated_validation_seconds")},
        "operator_priority": c["operator_priority"], "profile_bundle_digest": ctx["profile_bundle_digest"], "inbox_identity": str(Path(ctx["manifest"]["candidate_inbox_path"]).resolve()),
        "verification_receipt": verification, "authoring_receipt": ctx["verification_receipt"], "enqueue_receipts": [r for r in enqueues if r.get("candidate_revision_digest") == c["candidate_revision_digest"]]}


def print_pilot_plan(manifest_path: str | Path, candidate_path: str | Path, receipt_path: str | Path, evaluation_time: str) -> dict[str, Any]:
    m = validate_manifest(_load(manifest_path)); cfg = watchdog.load_config(m["watchdog_configuration_path"]); repo = Path(cfg["repository_root"]); py = str(_load(m["activation_profile_bundle_path"])["python_executable"])
    activation_cli = str(repo / "scripts" / "maintenance_loop_activation.py"); author_cli = str(repo / "scripts" / "maintenance_candidate_authoring.py"); watch_cli = str(repo / "scripts" / "maintenance_loop_watchdog.py")
    common = ["--config", m["watchdog_configuration_path"], "--evaluation-time", evaluation_time]
    candidate_args = ["--manifest", str(Path(manifest_path).resolve()), "--candidate", str(Path(candidate_path).resolve()), "--receipt", str(Path(receipt_path).resolve()), "--evaluation-time", evaluation_time]
    argv = {"doctor_live": [py, activation_cli, "doctor-live", *common], "smoke_idle": [py, activation_cli, "smoke-idle", *common],
        "verify_candidate": [py, author_cli, "verify-candidate", *candidate_args], "enqueue_candidate": [py, author_cli, "enqueue-candidate", *candidate_args],
        "run_bounded": [py, watch_cli, "--config", m["watchdog_configuration_path"], "--evaluation-time", evaluation_time, "run-bounded"],
        "watchdog_inspect": [py, watch_cli, "--config", m["watchdog_configuration_path"], "--evaluation-time", evaluation_time, "inspect"],
        "inspect_base_cursor": [py, watch_cli, "--config", m["watchdog_configuration_path"], "--evaluation-time", evaluation_time, "inspect-base-cursor"],
        "inspect_activation": [py, activation_cli, "inspect-activation", "--receipts", str(Path(cfg["state_root"]) / "maintenance_activation_receipts.jsonl")]}
    return {"schema_version": "sentientos.maintenance_candidate_pilot_plan:v1", "status": "manual_review_required",
        "operator_instruction": "Review the candidate and every readiness report before manually invoking run_bounded.", "argv": argv, "shell_command": None, "scheduler_installation": False}
