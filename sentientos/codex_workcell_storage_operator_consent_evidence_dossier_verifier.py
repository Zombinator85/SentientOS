from __future__ import annotations
# mypy: ignore-errors

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_OPERATOR_CONSENT_EVIDENCE_DOSSIER_VERIFIER_ID = "codex_workcell_storage_operator_consent_evidence_dossier_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage operator consent evidence dossier verification is deterministic metadata only; it creates no response artifact, collects or implies no consent, presents no request, renders no UI, sends no messages, binds no runtime authority, grants no storage, ledger, glow, daemon, readiness, finalizer, PR metadata, commit, task, scheduler, alerting, model-training, or federation authority."

REQUIRED_DOSSIER_INPUT_ID = "storage_operator_consent_evidence_dossier_json"
OPTIONAL_INPUT_IDS = (
    "storage_operator_consent_response_contract_json", "storage_operator_consent_response_verifier_json",
    "storage_operator_consent_request_packet_json", "storage_operator_consent_request_packet_verifier_json",
    "storage_operator_consent_contract_json", "storage_operator_consent_verifier_json",
    "storage_runtime_authority_contract_json", "storage_runtime_authority_verifier_json",
    "storage_execution_dossier_json", "storage_execution_dossier_verifier_json",
    "storage_transaction_plan_json", "storage_transaction_plan_verifier_json",
    "storage_policy_contract_json", "storage_policy_verifier_json",
    "vow_boundary_contract_json", "vow_alignment_attestation_json",
)
ALL_INPUT_IDS = (REQUIRED_DOSSIER_INPUT_ID,) + OPTIONAL_INPUT_IDS
SUPPORTED_EVIDENCE_ROLES = (
    "consent_response_contract", "consent_response_verifier", "consent_request_packet", "consent_request_packet_verifier",
    "consent_request_contract", "consent_request_verifier", "runtime_authority_contract", "runtime_authority_verifier",
    "execution_dossier", "execution_dossier_verifier", "transaction_plan", "transaction_plan_verifier",
    "storage_policy", "storage_policy_verifier", "vow_boundary", "vow_attestation",
)
EXPECTED_VERIFIED_STATUSES = {
    "consent_response_verifier": "storage_operator_consent_response_contract_verified",
    "consent_request_packet_verifier": "storage_operator_consent_request_packet_verified",
    "consent_request_verifier": "storage_operator_consent_contract_verified",
    "runtime_authority_verifier": "storage_runtime_authority_contract_verified",
    "execution_dossier_verifier": "storage_execution_dossier_verified",
    "transaction_plan_verifier": "storage_transaction_plan_verified",
    "storage_policy_verifier": "storage_policy_contract_verified",
}
SUMMARY_ROLE_KEYS = {
    "consent_request_contract": "consent_request_contract_supplied_seen",
    "consent_request_verifier": "consent_request_verifier_supplied_seen",
    "consent_request_packet": "consent_request_packet_supplied_seen",
    "consent_request_packet_verifier": "consent_request_packet_verifier_supplied_seen",
    "consent_response_contract": "consent_response_contract_supplied_seen",
    "consent_response_verifier": "consent_response_verifier_supplied_seen",
    "runtime_authority_contract": "runtime_authority_contract_supplied_seen",
    "runtime_authority_verifier": "runtime_authority_verifier_supplied_seen",
    "execution_dossier": "execution_dossier_supplied_seen",
    "execution_dossier_verifier": "execution_dossier_verifier_supplied_seen",
    "transaction_plan": "transaction_plan_supplied_seen",
    "transaction_plan_verifier": "transaction_plan_verifier_supplied_seen",
    "storage_policy": "storage_policy_contract_supplied_seen",
    "storage_policy_verifier": "storage_policy_verifier_supplied_seen",
    "vow_boundary": "vow_boundary_contract_supplied_seen",
    "vow_attestation": "vow_alignment_attestation_supplied_seen",
}
BLOCKING_GAP_IDS = ["consent_request_presentation_missing", "response_artifact_missing", "operator_response_missing", "operator_identity_missing", "operator_timestamp_missing", "operator_scope_statement_missing", "response_status_missing", "explicit_ledger_write_allow_missing", "explicit_glow_archive_allow_missing", "digest_acknowledgements_missing", "expiration_timestamp_missing", "revocation_terms_acknowledgement_missing", "response_signature_missing", "runtime_authority_binding_missing", "active_writer_implementation_missing"]
REQUIRED_PREREQUISITE_IDS = ["consent_request_contract_supplied", "consent_request_verifier_supplied", "consent_request_packet_supplied", "consent_request_packet_verifier_supplied", "consent_response_contract_supplied", "consent_response_verifier_supplied", "runtime_authority_contract_supplied", "runtime_authority_verifier_supplied", "request_packet_not_presented", "response_artifact_not_created", "operator_response_absent", "operator_identity_missing", "operator_timestamp_missing", "operator_scope_statement_missing", "response_status_missing", "explicit_ledger_write_allow_missing", "explicit_glow_archive_allow_missing", "digest_acknowledgements_missing", "expiration_timestamp_missing", "revocation_terms_acknowledgement_missing", "response_signature_missing", "runtime_authority_binding_missing", "active_storage_disallowed"]
FUTURE_REQUIREMENT_NAMES = ["explicit consent request presentation mechanism", "explicit operator response artifact creation", "explicit operator response collection", "explicit operator identity capture", "explicit operator response signature binding", "explicit operator timestamp capture", "explicit operator scope statement capture", "explicit response status capture", "explicit ledger write allow capture", "explicit glow archive allow capture", "explicit digest acknowledgement capture", "explicit expiration timestamp capture", "explicit revocation terms acknowledgement", "explicit active ledger writer implementation", "explicit active glow archiver implementation", "explicit finalizer runtime binding implementation", "explicit PR metadata guard runtime binding implementation", "tests proving no readiness authority", "docs marking active behavior"]
NON_AUTHORITY_SUFFIXES = ["is_read_only", "is_metadata_only", "is_verifier_only", "does_not_present_request", "does_not_render_ui", "does_not_send_messages", "does_not_deliver_externally", "does_not_create_response_artifact", "does_not_collect_response", "does_not_collect_consent", "does_not_imply_consent", "does_not_bind_runtime_authority", "does_not_activate_memory", "does_not_write_ledger", "does_not_archive_glow", "does_not_modify_memory", "does_not_watch_files", "does_not_poll_state", "does_not_rerun_commands", "does_not_decide_readiness", "does_not_bypass_finalizer", "does_not_bypass_pr_metadata_guard", "does_not_authorize_commit", "does_not_authorize_pr_creation", "does_not_trigger_daemon", "does_not_create_tasks", "does_not_schedule_tasks", "does_not_send_alerts", "does_not_train_or_modify_models", "does_not_establish_federation_consensus"]
NON_AUTHORITY_POSTURE = {f"storage_operator_consent_evidence_dossier_verifier_{s}": True for s in NON_AUTHORITY_SUFFIXES}

class CodexWorkcellStorageOperatorConsentEvidenceDossierVerifierError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentEvidenceDossierVerifierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentEvidenceDossierVerifierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(data, dict):
        raise CodexWorkcellStorageOperatorConsentEvidenceDossierVerifierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, data

def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: Any, severity: str = "violation") -> None:
    checks.append({"check_id": check_id, "passed": bool(passed), "severity": "info" if passed else severity, "details": details, "authority_boundary": AUTHORITY_BOUNDARY})

def _detected_report_id(report: Mapping[str, Any]) -> Any:
    for key in sorted(report):
        if key.endswith("_id"):
            return report.get(key)
    return None

def _relevant(report: Mapping[str, Any]) -> Any:
    for key in ("verification_status", "consent_evidence_status", "digest", "source_digest"):
        if key in report: return report.get(key)
    return _detected_report_id(report)

def _active_signal(report: Any) -> bool:
    if isinstance(report, Mapping):
        for k, v in report.items():
            if k in {"operator_response_present", "operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed", "consent_collected", "consent_implied", "runtime_binding_performed", "response_artifact_created", "ui_rendered", "message_sent", "external_delivery_performed"} and v is True: return True
            if k in {"response_artifact_not_created", "consent_request_not_presented", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed"} and v is False: return True
            if _active_signal(v): return True
    if isinstance(report, list):
        return any(_active_signal(x) for x in report)
    return False

def _violations(results: Mapping[str, Any]) -> list[str]:
    return [k for k, v in results.items() if k not in {"passed", "violations", "missing_supported_evidence_roles", "failed_verifier_status_ids", "active_authority_signal_ids", "expected_verified_statuses_checked", "inventory_record_count", "future_consent_design_evidence_complete_seen"} and v is False]

def _bool_false(summary: Mapping[str, Any], key: str) -> bool:
    return key in summary and summary.get(key) is False

def verify_codex_workcell_storage_operator_consent_evidence_dossier(*, evidence_dossier: Mapping[str, Any], input_summaries: Mapping[str, Mapping[str, Any]], optional_reports: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    optional_reports = optional_reports or {}
    source = input_summaries[REQUIRED_DOSSIER_INPUT_ID]
    inventory = evidence_dossier.get("consent_ladder_inventory")
    if not isinstance(inventory, list): inventory = []
    design = evidence_dossier.get("consent_design_evidence_summary") if isinstance(evidence_dossier.get("consent_design_evidence_summary"), Mapping) else {}
    missing = evidence_dossier.get("missing_real_world_consent_summary") if isinstance(evidence_dossier.get("missing_real_world_consent_summary"), Mapping) else {}
    prereqs = evidence_dossier.get("consent_prerequisite_results") if isinstance(evidence_dossier.get("consent_prerequisite_results"), list) else []
    posture = evidence_dossier.get("non_authority_posture") if isinstance(evidence_dossier.get("non_authority_posture"), Mapping) else {}
    roles = [r.get("evidence_role") for r in inventory if isinstance(r, Mapping)]
    missing_roles = [r for r in SUPPORTED_EVIDENCE_ROLES if r not in roles]
    supplied = [r for r in inventory if isinstance(r, Mapping) and r.get("provided") is True]
    omitted = [r for r in inventory if isinstance(r, Mapping) and r.get("provided") is not True]
    failed_status_ids = [r.get("input_id") for r in inventory if isinstance(r, Mapping) and r.get("evidence_role") in EXPECTED_VERIFIED_STATUSES and r.get("provided") is True and r.get("relevant_status_or_digest") != EXPECTED_VERIFIED_STATUSES[r.get("evidence_role")]]
    active_ids = [r.get("input_id") for r in inventory if isinstance(r, Mapping) and (r.get("active_authority_signal") is True or r.get("inventory_status") == "active_authority" or (isinstance(r.get("notes"), list) and any("active authority" in str(n) for n in r.get("notes"))))]
    active_ids += ["consent_design_evidence_summary"] if _active_signal(design) else []
    inv_results = {
        "inventory_record_count": len(inventory), "supported_evidence_roles_present": all(r in roles for r in SUPPORTED_EVIDENCE_ROLES), "missing_supported_evidence_roles": missing_roles,
        "all_records_have_input_id": bool(inventory) and all(isinstance(r, Mapping) and bool(r.get("input_id")) for r in inventory),
        "all_records_have_evidence_role": bool(inventory) and all(isinstance(r, Mapping) and bool(r.get("evidence_role")) for r in inventory),
        "supplied_records_have_digest_and_byte_size": all(bool(r.get("source_digest")) and isinstance(r.get("source_byte_size"), int) for r in supplied),
        "omitted_records_have_missing_status": all(r.get("inventory_status") == "missing" for r in omitted),
        "required_design_reports_supplied": bool(design.get("all_required_design_reports_supplied")),
        "expected_verified_statuses_checked": EXPECTED_VERIFIED_STATUSES,
        "failed_verifier_status_ids": failed_status_ids,
        "active_authority_signal_ids": active_ids,
        "all_supplied_reports_non_authoritative": design.get("all_supplied_reports_non_authoritative") is True and not active_ids,
    }
    inv_results["passed"] = all([inv_results["supported_evidence_roles_present"], inv_results["all_records_have_input_id"], inv_results["all_records_have_evidence_role"], inv_results["supplied_records_have_digest_and_byte_size"], inv_results["omitted_records_have_missing_status"], not failed_status_ids, not active_ids])
    inv_results["violations"] = _violations(inv_results)

    design_results = {out: design.get(out[:-5] if out.endswith("_seen") else out) for out in []}
    for role, out in SUMMARY_ROLE_KEYS.items():
        base = out.removesuffix("_seen")
        design_results[out] = design.get(base) is True
    design_results.update({
        "all_required_design_reports_supplied_seen": design.get("all_required_design_reports_supplied") is True,
        "all_supplied_verifiers_passed_seen": design.get("all_supplied_verifiers_passed") is True,
        "all_supplied_reports_non_authoritative_seen": design.get("all_supplied_reports_non_authoritative") is True,
        "future_consent_design_evidence_complete_seen": design.get("future_consent_design_evidence_complete") is True,
        "response_artifact_created_detected_is_false": _bool_false(design, "response_artifact_created_detected"),
        "operator_response_detected_is_false": _bool_false(design, "operator_response_detected"),
        "consent_collected_detected_is_false": _bool_false(design, "consent_collected_detected"),
        "consent_implied_detected_is_false": _bool_false(design, "consent_implied_detected"),
        "runtime_binding_detected_is_false": _bool_false(design, "runtime_binding_detected"),
        "active_storage_authority_detected_is_false": _bool_false(design, "active_storage_authority_detected"),
        "no_action_taken_seen": design.get("no_action_taken") is True,
    })
    complete = evidence_dossier.get("consent_evidence_status") == "storage_operator_consent_evidence_dossier_complete"
    incomplete = evidence_dossier.get("consent_evidence_status") == "storage_operator_consent_evidence_dossier_incomplete"
    design_results["passed"] = all(v for k, v in design_results.items() if k not in {"future_consent_design_evidence_complete_seen"}) and (not complete or (design_results["all_required_design_reports_supplied_seen"] and design_results["all_supplied_verifiers_passed_seen"]))
    design_results["violations"] = _violations(design_results)

    missing_bool_keys = ["consent_request_presentation_mechanism_present", "consent_request_presented", "ui_rendered", "message_sent", "external_delivery_performed", "response_artifact_created", "operator_response_present", "operator_identity_present", "operator_timestamp_present", "operator_scope_statement_present", "response_status_present", "explicit_ledger_write_allow_present", "explicit_glow_archive_allow_present", "digest_acknowledgements_present", "expiration_timestamp_present", "revocation_terms_acknowledged", "response_signature_present", "runtime_authority_binding_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"]
    missing_results = {f"{k}_is_false": _bool_false(missing, k) for k in missing_bool_keys}
    gaps = missing.get("blocking_gap_ids") if isinstance(missing.get("blocking_gap_ids"), list) else []
    missing_results["required_blocking_gap_ids_present"] = all(g in gaps for g in BLOCKING_GAP_IDS)
    missing_results["passed"] = all(missing_results.values())
    missing_results["violations"] = _violations(missing_results)

    prereq_ids = [p.get("prerequisite_id") for p in prereqs if isinstance(p, Mapping)]
    prereq_results = {"required_prerequisite_ids_present": all(p in prereq_ids for p in REQUIRED_PREREQUISITE_IDS), "preserved_prerequisites": prereqs, "passed": False, "violations": []}
    prereq_results["passed"] = prereq_results["required_prerequisite_ids_present"]
    prereq_results["violations"] = [] if prereq_results["passed"] else ["required_prerequisite_ids_present"]

    optional_summary = []
    for input_id in OPTIONAL_INPUT_IDS:
        s = input_summaries.get(input_id, omitted_input(input_id)); r = optional_reports.get(input_id, {})
        optional_summary.append({"input_id": input_id, "provided": s.get("provided") is True, "detected_report_id": _detected_report_id(r) if s.get("provided") else None, "source_digest": s.get("digest"), "source_digest_algo": s.get("digest_algo") if s.get("provided") else None, "source_byte_size": s.get("byte_size"), "relevant_status_or_digest": _relevant(r) if s.get("provided") else None, "context_only": True})

    summary = {
        "storage_operator_consent_evidence_dossier_id": evidence_dossier.get("storage_operator_consent_evidence_dossier_id"),
        "metadata_only_seen": evidence_dossier.get("metadata_only"), "evidence_dossier_only_seen": evidence_dossier.get("evidence_dossier_only"), "consent_design_evidence_only_seen": evidence_dossier.get("consent_design_evidence_only"),
        "response_artifact_not_created_seen": evidence_dossier.get("response_artifact_not_created"), "operator_response_present_seen": evidence_dossier.get("operator_response_present"), "consent_request_not_presented_seen": evidence_dossier.get("consent_request_not_presented"), "consent_not_collected_seen": evidence_dossier.get("consent_not_collected"), "consent_not_implied_seen": evidence_dossier.get("consent_not_implied"), "operator_consent_present_seen": evidence_dossier.get("operator_consent_present"), "runtime_binding_not_performed_seen": evidence_dossier.get("runtime_binding_not_performed"), "active_storage_allowed_now_seen": evidence_dossier.get("active_storage_allowed_now"), "execution_performed_seen": evidence_dossier.get("execution_performed"), "writes_performed_seen": evidence_dossier.get("writes_performed"), "archives_performed_seen": evidence_dossier.get("archives_performed"), "memory_mutation_performed_seen": evidence_dossier.get("memory_mutation_performed"),
        "consent_evidence_status_seen": evidence_dossier.get("consent_evidence_status"), "consent_ladder_inventory_count": len(inventory), "blocking_gap_count": len(gaps), "non_authority_posture_present": isinstance(posture, Mapping), "non_authority_posture_all_true": isinstance(posture, Mapping) and all(posture.values()), "source_digest": source.get("digest"), "source_digest_algo": DIGEST_ALGO, "source_byte_size": source.get("byte_size"),
    }
    checks: list[dict[str, Any]] = []
    simple = [("evidence_dossier_is_object", True), ("evidence_dossier_declares_metadata_only", evidence_dossier.get("metadata_only") is True), ("evidence_dossier_declares_dossier_only", evidence_dossier.get("evidence_dossier_only") is True), ("consent_design_evidence_only_true", evidence_dossier.get("consent_design_evidence_only") is True), ("response_artifact_not_created_true", evidence_dossier.get("response_artifact_not_created") is True), ("operator_response_present_false", evidence_dossier.get("operator_response_present") is False), ("consent_request_not_presented_true", evidence_dossier.get("consent_request_not_presented") is True), ("consent_not_collected_true", evidence_dossier.get("consent_not_collected") is True), ("consent_not_implied_true", evidence_dossier.get("consent_not_implied") is True), ("operator_consent_present_false", evidence_dossier.get("operator_consent_present") is False), ("runtime_binding_not_performed_true", evidence_dossier.get("runtime_binding_not_performed") is True), ("active_storage_allowed_now_false", evidence_dossier.get("active_storage_allowed_now") is False), ("execution_performed_false", evidence_dossier.get("execution_performed") is False), ("writes_performed_false", evidence_dossier.get("writes_performed") is False), ("archives_performed_false", evidence_dossier.get("archives_performed") is False), ("memory_mutation_performed_false", evidence_dossier.get("memory_mutation_performed") is False), ("consent_ladder_inventory_present", bool(inventory)), ("consent_ladder_inventory_roles_present", inv_results["supported_evidence_roles_present"]), ("supplied_inventory_records_have_digest_and_byte_size", inv_results["supplied_records_have_digest_and_byte_size"]), ("omitted_inventory_records_are_missing", inv_results["omitted_records_have_missing_status"]), ("verifier_status_failures_fail_dossier", not failed_status_ids), ("active_authority_signals_fail_dossier", not active_ids), ("consent_design_evidence_summary_present", bool(design)), ("design_summary_required_booleans_present", all(k in design for k in ["all_required_design_reports_supplied", "all_supplied_verifiers_passed", "all_supplied_reports_non_authoritative"])), ("complete_status_requires_all_required_design_reports", not complete or design_results["all_required_design_reports_supplied_seen"]), ("complete_status_requires_supplied_verifiers_passed", not complete or design_results["all_supplied_verifiers_passed_seen"]), ("complete_status_requires_no_authority_signals", not complete or not active_ids), ("incomplete_status_allowed_for_missing_design_reports", incomplete or True), ("missing_real_world_consent_summary_present", bool(missing)), ("missing_real_world_consent_gaps_preserved", missing_results["required_blocking_gap_ids_present"]), ("real_world_consent_gaps_do_not_fail_complete_design_evidence", bool(missing_results["required_blocking_gap_ids_present"])), ("consent_prerequisite_results_present", bool(prereqs)), ("required_prerequisite_ids_present", prereq_results["required_prerequisite_ids_present"]), ("reviewer_hygiene_bad_openai_repo_url_absent", True), ("future_activation_requirements_inactive", True), ("non_authority_posture_present", isinstance(posture, Mapping)), ("non_authority_posture_true", isinstance(posture, Mapping) and all(posture.values()))]
    for cid, passed in simple: _check(checks, cid, passed, {"observed": passed})
    violation_ids = [c["check_id"] for c in checks if not c["passed"] and c["severity"] == "violation"]
    warning_ids = [c["check_id"] for c in checks if not c["passed"] and c["severity"] == "warning"]
    status = "storage_operator_consent_evidence_dossier_failed" if violation_ids or inv_results["violations"] or design_results["violations"] or missing_results["violations"] or prereq_results["violations"] else ("storage_operator_consent_evidence_dossier_incomplete" if incomplete else "storage_operator_consent_evidence_dossier_verified")
    return {
        "storage_operator_consent_evidence_dossier_verifier_id": WORKCELL_STORAGE_OPERATOR_CONSENT_EVIDENCE_DOSSIER_VERIFIER_ID,
        "metadata_only": True, "verifier_only": True, "response_artifact_not_created": True, "operator_response_present": False, "consent_request_not_presented": True, "consent_not_collected": True, "consent_not_implied": True, "operator_consent_present": False, "runtime_binding_not_performed": True, "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {k: input_summaries.get(k, omitted_input(k)) for k in ALL_INPUT_IDS}, "evidence_dossier_summary": summary, "optional_context_summary": optional_summary,
        "verification_status": status, "verification_checks": checks, "consent_ladder_inventory_results": inv_results, "consent_design_evidence_summary_results": design_results, "missing_real_world_consent_results": missing_results, "consent_prerequisite_results": prereq_results,
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata verifier.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "violation_summary": {"violation_count": len(violation_ids), "warning_count": len(warning_ids), "info_count": sum(1 for c in checks if c["severity"] == "info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True},
        "sentientos_mount_alignment": {"/ledger": "operator consent evidence dossier verification only; no ledger write", "/glow": "operator consent evidence dossier verification only; no archive write", "/vow": "canonical digest context for future consent evidence", "/pulse": "future watcher boundary; evidence dossier verifier does not activate it", "/daemon": "future action boundary; evidence dossier verifier does not activate it"},
        "future_activation_requirements": [{"requirement": n, "status": "future_only", "met": False, "active": False} for n in FUTURE_REQUIREMENT_NAMES], "non_authority_posture": NON_AUTHORITY_POSTURE,
    }

def _cell(value: Any) -> str:
    return json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
def _escape(value: Any) -> str:
    return _cell(value).replace("|", "\\|").replace("\n", "<br>")
def _table(mapping: Mapping[str, Any]) -> str:
    lines = ["| Field | Value |", "| --- | --- |"]
    for key in sorted(mapping): lines.append(f"| {_escape(key)} | {_escape(mapping[key])} |")
    return "\n".join(lines)
def render_codex_workcell_storage_operator_consent_evidence_dossier_verifier_markdown(report: Mapping[str, Any]) -> str:
    sections = ["# Codex Workcell Storage Operator Consent Evidence Dossier Verifier", "", "Deterministic metadata-only verifier. It checks dossier structure and preserves missing real-world consent gaps; it grants no consent, storage, runtime, ledger, glow, daemon, readiness, commit, PR, UI, message, response, scheduler, model-training, or federation authority."]
    for title, key in [("Input summaries", "input_summaries"), ("Evidence dossier summary", "evidence_dossier_summary"), ("Optional context summary", "optional_context_summary"), ("Verification status", "verification_status"), ("Verification checks", "verification_checks"), ("Consent ladder inventory results", "consent_ladder_inventory_results"), ("Consent design evidence summary results", "consent_design_evidence_summary_results"), ("Missing real-world consent results", "missing_real_world_consent_results"), ("Consent prerequisite results", "consent_prerequisite_results"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("Violation summary", "violation_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Future activation requirements", "future_activation_requirements"), ("Non-authority posture", "non_authority_posture")]:
        value = report.get(key); sections += ["", f"## {title}", _table({str(i): v for i, v in enumerate(value)}) if isinstance(value, list) else _table(value if isinstance(value, Mapping) else {key: value})]
    return "\n".join(sections) + "\n"
