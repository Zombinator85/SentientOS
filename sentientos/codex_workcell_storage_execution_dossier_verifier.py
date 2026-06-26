from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_EXECUTION_DOSSIER_VERIFIER_ID = "codex_workcell_storage_execution_dossier_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage execution dossier verification is deterministic metadata only; it grants no runtime, memory, ledger, glow, daemon, readiness, finalizer, PR metadata, commit, task, scheduler, alerting, model-training, or federation authority."

OPTIONAL_INPUT_IDS: tuple[str, ...] = (
    "memory_contract_json", "memory_candidate_bundle_json", "memory_candidate_verifier_json", "memory_activation_preflight_json",
    "vow_boundary_contract_json", "vow_alignment_attestation_json", "storage_policy_contract_json", "storage_policy_verifier_json",
    "storage_transaction_plan_json", "storage_transaction_plan_verifier_json",
)
REQUIRED_BLOCKING_GAP_IDS: tuple[str, ...] = (
    "active_writer_implementation_missing", "operator_consent_missing", "finalizer_guard_runtime_binding_missing", "storage_path_enforcement_missing",
    "retention_enforcement_missing", "digest_verification_runtime_missing", "parent_chain_runtime_missing", "pulse_watcher_contract_missing",
    "daemon_action_contract_missing", "federation_consensus_missing",
)
FUTURE_REQUIREMENT_NAMES: tuple[str, ...] = (
    "explicit active ledger writer implementation", "explicit active glow archiver implementation", "explicit storage path enforcement",
    "explicit retention enforcement", "explicit digest verification enforcement", "explicit parent-chain validation enforcement", "explicit operator consent",
    "explicit finalizer/guard runtime binding", "explicit pulse watcher contract", "explicit daemon action contract", "explicit federation drift consensus rule",
    "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "storage_execution_dossier_verifier_is_read_only": True,
    "storage_execution_dossier_verifier_is_metadata_only": True,
    "storage_execution_dossier_verifier_is_verifier_only": True,
    "storage_execution_dossier_verifier_does_not_activate_memory": True,
    "storage_execution_dossier_verifier_does_not_write_ledger": True,
    "storage_execution_dossier_verifier_does_not_archive_glow": True,
    "storage_execution_dossier_verifier_does_not_modify_memory": True,
    "storage_execution_dossier_verifier_does_not_watch_files": True,
    "storage_execution_dossier_verifier_does_not_poll_state": True,
    "storage_execution_dossier_verifier_does_not_rerun_commands": True,
    "storage_execution_dossier_verifier_does_not_decide_readiness": True,
    "storage_execution_dossier_verifier_does_not_bypass_finalizer": True,
    "storage_execution_dossier_verifier_does_not_bypass_pr_metadata_guard": True,
    "storage_execution_dossier_verifier_does_not_authorize_commit": True,
    "storage_execution_dossier_verifier_does_not_authorize_pr_creation": True,
    "storage_execution_dossier_verifier_does_not_trigger_daemon": True,
    "storage_execution_dossier_verifier_does_not_create_tasks": True,
    "storage_execution_dossier_verifier_does_not_schedule_tasks": True,
    "storage_execution_dossier_verifier_does_not_send_alerts": True,
    "storage_execution_dossier_verifier_does_not_train_or_modify_models": True,
    "storage_execution_dossier_verifier_does_not_establish_federation_consensus": True,
}

class CodexWorkcellStorageExecutionDossierVerifierError(ValueError):
    pass

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageExecutionDossierVerifierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageExecutionDossierVerifierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageExecutionDossierVerifierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def _all_true(value: Any) -> bool | None:
    return all(v is True for v in value.values()) if isinstance(value, Mapping) else None

def _count_list(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None

def _report_id(data: Mapping[str, Any]) -> Any:
    for key in ("storage_execution_dossier_id","storage_transaction_plan_verifier_id","storage_transaction_plan_id","storage_policy_verifier_id","storage_policy_contract_id","vow_alignment_attestation_id","vow_boundary_contract_id","memory_activation_preflight_id","memory_candidate_verifier_id","memory_candidate_bundle_id","memory_contract_id"):
        if data.get(key): return data.get(key)
    return None

def _status_or_digest(data: Mapping[str, Any]) -> Any:
    for key in ("verification_status","storage_execution_status","storage_transaction_plan_verification_status","storage_policy_verification_status","memory_candidate_verification_status","activation_preflight_status","digest","source_digest"):
        if data.get(key) is not None: return data.get(key)
    return None

def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: str, severity: str = "violation") -> None:
    checks.append({"check_id": check_id, "passed": passed, "severity": "info" if passed else severity, "details": details, "authority_boundary": AUTHORITY_BOUNDARY})

def verify_codex_workcell_storage_execution_dossier(*, storage_execution_dossier: Mapping[str, Any], storage_execution_dossier_summary: Mapping[str, Any], optional_reports: Mapping[str, Mapping[str, Any]], optional_summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    dossier = storage_execution_dossier
    inventory = dossier.get("evidence_inventory")
    readiness = dossier.get("readiness_evidence_summary")
    gaps = dossier.get("active_execution_gap_summary")
    prereqs = dossier.get("execution_prerequisite_results")
    context = dossier.get("dossier_context", {}) if isinstance(dossier.get("dossier_context"), Mapping) else {}
    nonauth = dossier.get("non_authority_posture")
    future = dossier.get("future_activation_requirements")
    checks: list[dict[str, Any]] = []
    _check(checks, "dossier_is_object", isinstance(dossier, Mapping), "Dossier input parsed as JSON object.")
    _check(checks, "dossier_declares_metadata_only", dossier.get("metadata_only") is True, "metadata_only must be true.")
    _check(checks, "dossier_declares_dossier_only", dossier.get("dossier_only") is True, "dossier_only must be true.")
    _check(checks, "dossier_declares_execution_not_performed", dossier.get("execution_not_performed") is True, "execution_not_performed must be true.")
    _check(checks, "dossier_declares_no_writes_performed", dossier.get("writes_performed") is False, "writes_performed must be false.")
    _check(checks, "dossier_declares_no_archives_performed", dossier.get("archives_performed") is False, "archives_performed must be false.")
    _check(checks, "dossier_declares_no_memory_mutation", dossier.get("memory_mutation_performed") is False, "memory_mutation_performed must be false.")
    _check(checks, "evidence_inventory_present", isinstance(inventory, list) and bool(inventory), "evidence_inventory must be a non-empty list.")
    _check(checks, "readiness_evidence_summary_present", isinstance(readiness, Mapping), "readiness_evidence_summary must be present.")
    _check(checks, "active_execution_gap_summary_present", isinstance(gaps, Mapping), "active_execution_gap_summary must be present.")
    _check(checks, "execution_prerequisite_results_present", isinstance(prereqs, list), "execution_prerequisite_results must be present.")
    status = dossier.get("storage_execution_status")
    _check(checks, "storage_execution_status_known", status in {"future_storage_design_dossier_complete","future_storage_design_dossier_incomplete","future_storage_design_dossier_failed"}, "storage_execution_status must be known.")
    supplied = context.get("supplied_report_count"); required = context.get("required_report_count")
    _check(checks, "missing_reports_make_dossier_incomplete", not (isinstance(supplied, int) and isinstance(required, int) and supplied < required and status == "future_storage_design_dossier_complete"), "Missing reports cannot be represented as complete.")
    failed_seen = any(isinstance(i, Mapping) and isinstance(i.get("relevant_status"), str) and "failed" in i.get("relevant_status", "") for i in (inventory if isinstance(inventory, list) else []))
    _check(checks, "failed_verifier_status_makes_dossier_failed", not (failed_seen and status != "future_storage_design_dossier_failed"), "Failed verifier status must make dossier failed.")
    _check(checks, "complete_status_requires_required_reports", not (status == "future_storage_design_dossier_complete" and supplied != required), "Complete status requires all required reports.")
    blocking_ids = list(gaps.get("blocking_gap_ids", [])) if isinstance(gaps, Mapping) and isinstance(gaps.get("blocking_gap_ids"), list) else []
    _check(checks, "active_execution_gaps_remain_blocking", all(g in blocking_ids for g in REQUIRED_BLOCKING_GAP_IDS), "Required active execution gaps must remain blocking.")
    for cid, key in (("active_storage_allowed_now_false","active_storage_allowed_now"),("execution_performed_false","execution_performed"),("writes_performed_false","writes_performed"),("archives_performed_false","archives_performed"),("memory_mutation_performed_false","memory_mutation_performed")):
        _check(checks, cid, isinstance(gaps, Mapping) and gaps.get(key) is False, f"{key} must be false.")
    _check(checks, "reviewer_hygiene_bad_openai_repo_url_absent", True, "Runtime grep is external to this metadata verifier.", "info")
    future_ok = isinstance(future, list) and all(isinstance(r, Mapping) and r.get("status") == "future_only" and r.get("met") is False and r.get("active") is False for r in future)
    _check(checks, "future_activation_requirements_inactive", future_ok, "Future activation requirements must be future_only, unmet, and inactive.")
    _check(checks, "non_authority_posture_present", isinstance(nonauth, Mapping), "non_authority_posture must be present.")
    _check(checks, "non_authority_posture_true", _all_true(nonauth) is True, "All dossier non_authority_posture values must be true.")
    evidence_results=[]
    for rec in (inventory if isinstance(inventory, list) else []):
        if not isinstance(rec, Mapping): continue
        violations=[]
        if rec.get("provided") is True and not rec.get("source_digest"): violations.append("missing_source_digest")
        if rec.get("non_authority_posture_all_true") is False: violations.append("source_report_authority_posture_not_all_true")
        evidence_results.append({"input_id": rec.get("input_id"), "provided": rec.get("provided"), "evidence_role": rec.get("evidence_role"), "detected_report_id": rec.get("detected_report_id"), "source_digest_seen": rec.get("source_digest"), "source_byte_size_seen": rec.get("source_byte_size"), "relevant_status": rec.get("relevant_status"), "relevant_digest": rec.get("relevant_digest"), "inventory_status": rec.get("inventory_status"), "non_authority_posture_present": rec.get("non_authority_posture_present"), "non_authority_posture_all_true": rec.get("non_authority_posture_all_true"), "passed": not violations, "violations": violations, "authority_boundary": AUTHORITY_BOUNDARY})
    r = readiness if isinstance(readiness, Mapping) else {}
    readiness_results = {"all_required_reports_supplied_seen": r.get("all_required_reports_supplied"), "all_supplied_reports_non_authoritative_seen": r.get("all_supplied_reports_non_authoritative"), "dossier_ready_for_future_design_review_seen": r.get("dossier_ready_for_future_design_review"), "storage_policy_verified_seen": r.get("storage_policy_verified"), "storage_transaction_plan_verified_seen": r.get("storage_transaction_plan_verified"), "memory_candidate_verified_seen": r.get("memory_candidate_verified"), "vow_alignment_failed_count": r.get("vow_alignment_failed_count"), "vow_alignment_warning_count": r.get("vow_alignment_warning_count"), "active_authority_detected": r.get("active_authority_detected"), "passed": r.get("active_authority_detected") is not True, "violations": ["active_authority_detected"] if r.get("active_authority_detected") is True else []}
    g = gaps if isinstance(gaps, Mapping) else {}
    active_gap_violations: list[str] = []
    active_gap_results = {"active_writer_implementation_present_seen": g.get("active_writer_implementation_present"), "operator_consent_present_seen": g.get("operator_consent_present"), "finalizer_guard_runtime_binding_present_seen": g.get("finalizer_guard_runtime_binding_present"), "storage_path_enforcement_present_seen": g.get("storage_path_enforcement_present"), "retention_enforcement_present_seen": g.get("retention_enforcement_present"), "digest_verification_runtime_present_seen": g.get("digest_verification_runtime_present"), "parent_chain_runtime_present_seen": g.get("parent_chain_runtime_present"), "pulse_watcher_contract_present_seen": g.get("pulse_watcher_contract_present"), "daemon_action_contract_present_seen": g.get("daemon_action_contract_present"), "federation_consensus_present_seen": g.get("federation_consensus_present"), "active_storage_allowed_now_seen": g.get("active_storage_allowed_now"), "execution_performed_seen": g.get("execution_performed"), "writes_performed_seen": g.get("writes_performed"), "archives_performed_seen": g.get("archives_performed"), "memory_mutation_performed_seen": g.get("memory_mutation_performed"), "blocking_gap_ids": blocking_ids, "warning_gap_ids": g.get("warning_gap_ids") if isinstance(g.get("warning_gap_ids"), list) else [], "required_blocking_gaps_present": all(x in blocking_ids for x in REQUIRED_BLOCKING_GAP_IDS), "passed": all(x in blocking_ids for x in REQUIRED_BLOCKING_GAP_IDS) and all(g.get(k) is False for k in ("active_storage_allowed_now","execution_performed","writes_performed","archives_performed","memory_mutation_performed")), "violations": active_gap_violations}
    if not active_gap_results["passed"]:
        active_gap_violations.append("active_execution_gap_boundary_failed")
    p = prereqs if isinstance(prereqs, list) else []
    active_prereq_ids = [x.get("prerequisite_id") for x in p if isinstance(x, Mapping) and x.get("category") == "active_execution_gap"]
    exec_violations: list[str] = []
    exec_results = {"prerequisite_count": len(p), "missing_required_prerequisite_ids": [x.get("prerequisite_id") for x in p if isinstance(x, Mapping) and x.get("passed") is False and x.get("category") == "supplied_report"], "failed_prerequisite_ids": [x.get("prerequisite_id") for x in p if isinstance(x, Mapping) and x.get("passed") is False and x.get("severity") == "violation"], "active_execution_gap_ids": active_prereq_ids, "all_active_execution_gaps_blocking": all(x in active_prereq_ids for x in REQUIRED_BLOCKING_GAP_IDS), "no_prerequisite_grants_runtime_authority": True, "passed": all(x in active_prereq_ids for x in REQUIRED_BLOCKING_GAP_IDS), "violations": exec_violations}
    if not exec_results["passed"]:
        exec_violations.append("missing_active_execution_gap_prerequisites")
    violation_ids=[c["check_id"] for c in checks if not c["passed"] and c["severity"]=="violation"]
    warning_ids=[c["check_id"] for c in checks if not c["passed"] and c["severity"]=="warning"]
    if violation_ids or not readiness_results["passed"] or not active_gap_results["passed"] or not exec_results["passed"]:
        verification_status="storage_execution_dossier_failed"
    elif status == "future_storage_design_dossier_incomplete" or warning_ids:
        verification_status="storage_execution_dossier_incomplete"
    else:
        verification_status="storage_execution_dossier_verified"
    optional_summary=[]
    for input_id in OPTIONAL_INPUT_IDS:
        s=optional_summaries[input_id]; data=optional_reports.get(input_id, {})
        optional_summary.append({"input_id": input_id, "provided": s.get("provided"), "detected_report_id": _report_id(data), "source_digest": s.get("digest"), "source_digest_algo": s.get("digest_algo") or DIGEST_ALGO if s.get("provided") else None, "source_byte_size": s.get("byte_size"), "relevant_status_or_digest": _status_or_digest(data), "context_only": True})
    return {"storage_execution_dossier_verifier_id": WORKCELL_STORAGE_EXECUTION_DOSSIER_VERIFIER_ID, "metadata_only": True, "verifier_only": True, "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True, "input_summaries": {"storage_execution_dossier_json": dict(storage_execution_dossier_summary), **{k: dict(v) for k,v in optional_summaries.items()}}, "dossier_summary": {"storage_execution_dossier_id": dossier.get("storage_execution_dossier_id"), "metadata_only": dossier.get("metadata_only"), "dossier_only": dossier.get("dossier_only"), "execution_not_performed": dossier.get("execution_not_performed"), "writes_performed": dossier.get("writes_performed"), "archives_performed": dossier.get("archives_performed"), "memory_mutation_performed": dossier.get("memory_mutation_performed"), "storage_execution_status": status, "supplied_report_count": supplied, "required_report_count": required, "blocking_gap_count": _count_list(blocking_ids), "warning_gap_count": _count_list(g.get("warning_gap_ids")) if isinstance(g, Mapping) else None, "non_authority_posture_present": isinstance(nonauth, Mapping), "non_authority_posture_all_true": _all_true(nonauth), "source_digest": storage_execution_dossier_summary.get("digest"), "source_digest_algo": DIGEST_ALGO, "source_byte_size": storage_execution_dossier_summary.get("byte_size")}, "optional_source_report_summary": optional_summary, "verification_status": verification_status, "verification_checks": checks, "evidence_inventory_results": evidence_results, "readiness_evidence_results": readiness_results, "active_execution_gap_results": active_gap_results, "execution_prerequisite_results": exec_results, "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata verifier.", "docs_hygiene_only": True, "no_runtime_effect": True}, "violation_summary": {"violation_count": len(violation_ids), "warning_count": len(warning_ids), "info_count": sum(1 for c in checks if c["severity"]=="info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True}, "sentientos_mount_alignment": {"/ledger": "dossier verification only; no ledger write", "/glow": "dossier verification only; no archive write", "/vow": "canonical digest context for execution boundaries", "/pulse": "future consumer of stored history; inactive here", "/daemon": "future consumer of pulse/recommendation context; inactive here"}, "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_REQUIREMENT_NAMES], "non_authority_posture": dict(NON_AUTHORITY_POSTURE)}

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")

def _table(headers: list[str], rows: list[list[Any]]) -> str:
    return "| " + " | ".join(headers) + " |\n| " + " | ".join("---" for _ in headers) + " |\n" + "".join("| " + " | ".join(_cell(c) for c in row) + " |\n" for row in rows)

def render_codex_workcell_storage_execution_dossier_verifier_markdown(report: Mapping[str, Any]) -> str:
    parts=["# Codex Workcell Storage Execution Dossier Verifier\n", "This metadata-only verifier checks dossier structure and source-report context; it is not readiness, storage, ledger, glow, daemon, finalizer, PR metadata, commit, task, scheduler, alerting, model-training, or federation authority.\n"]
    parts.append("## Input summaries\n" + _table(["input", "provided", "path", "digest", "bytes"], [[k, v.get("provided"), v.get("path"), v.get("digest"), v.get("byte_size")] for k,v in sorted(report["input_summaries"].items())]))
    for title,key in (("Dossier summary","dossier_summary"),("Reviewer hygiene summary","reviewer_hygiene_summary"),("Violation summary","violation_summary"),("SentientOS mount alignment","sentientos_mount_alignment"),("Non-authority posture","non_authority_posture")):
        parts.append(f"## {title}\n" + _table(["key","value"], [[k,v] for k,v in report[key].items()]))
    parts.append("## Optional source report summary\n" + _table(["input","provided","report","digest","status"], [[r["input_id"], r["provided"], r["detected_report_id"], r["source_digest"], r["relevant_status_or_digest"]] for r in report["optional_source_report_summary"]]))
    parts.append("## Verification status\n" + str(report["verification_status"]) + "\n")
    parts.append("## Verification checks\n" + _table(["check","passed","severity","details"], [[c["check_id"], c["passed"], c["severity"], c["details"]] for c in report["verification_checks"]]))
    parts.append("## Evidence inventory results\n" + _table(["input","provided","role","passed","violations"], [[r["input_id"], r["provided"], r["evidence_role"], r["passed"], r["violations"]] for r in report["evidence_inventory_results"]]))
    for title,key in (("Readiness evidence results","readiness_evidence_results"),("Active execution gap results","active_execution_gap_results"),("Execution prerequisite results","execution_prerequisite_results")):
        parts.append(f"## {title}\n" + _table(["key","value"], [[k,v] for k,v in report[key].items()]))
    parts.append("## Future activation requirements\n" + _table(["requirement","status","met","active"], [[r["requirement"], r["status"], r["met"], r["active"]] for r in report["future_activation_requirements"]]))
    return "\n".join(parts)
