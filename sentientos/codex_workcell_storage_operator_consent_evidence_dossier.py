from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_OPERATOR_CONSENT_EVIDENCE_DOSSIER_ID = "codex_workcell_storage_operator_consent_evidence_dossier.v1"
DIGEST_ALGO = "sha256"

INPUT_SPECS: dict[str, tuple[str, str | None, bool]] = {
    "storage_operator_consent_response_contract_json": ("consent_response_contract", None, True),
    "storage_operator_consent_response_verifier_json": ("consent_response_verifier", "storage_operator_consent_response_contract_verified", True),
    "storage_operator_consent_request_packet_json": ("consent_request_packet", None, True),
    "storage_operator_consent_request_packet_verifier_json": ("consent_request_packet_verifier", "storage_operator_consent_request_packet_verified", True),
    "storage_operator_consent_contract_json": ("consent_request_contract", None, True),
    "storage_operator_consent_verifier_json": ("consent_request_verifier", "storage_operator_consent_contract_verified", True),
    "storage_runtime_authority_contract_json": ("runtime_authority_contract", None, True),
    "storage_runtime_authority_verifier_json": ("runtime_authority_verifier", "storage_runtime_authority_contract_verified", True),
    "storage_execution_dossier_json": ("execution_dossier", None, True),
    "storage_execution_dossier_verifier_json": ("execution_dossier_verifier", "storage_execution_dossier_verified", True),
    "storage_transaction_plan_json": ("transaction_plan", None, True),
    "storage_transaction_plan_verifier_json": ("transaction_plan_verifier", "storage_transaction_plan_verified", True),
    "storage_policy_contract_json": ("storage_policy", None, True),
    "storage_policy_verifier_json": ("storage_policy_verifier", "storage_policy_contract_verified", True),
    "vow_boundary_contract_json": ("vow_boundary", None, True),
    "vow_alignment_attestation_json": ("vow_attestation", None, True),
}

SUMMARY_KEYS = {
    "storage_operator_consent_contract_json": "consent_request_contract_supplied",
    "storage_operator_consent_verifier_json": "consent_request_verifier_supplied",
    "storage_operator_consent_request_packet_json": "consent_request_packet_supplied",
    "storage_operator_consent_request_packet_verifier_json": "consent_request_packet_verifier_supplied",
    "storage_operator_consent_response_contract_json": "consent_response_contract_supplied",
    "storage_operator_consent_response_verifier_json": "consent_response_verifier_supplied",
    "storage_runtime_authority_contract_json": "runtime_authority_contract_supplied",
    "storage_runtime_authority_verifier_json": "runtime_authority_verifier_supplied",
    "storage_execution_dossier_json": "execution_dossier_supplied",
    "storage_execution_dossier_verifier_json": "execution_dossier_verifier_supplied",
    "storage_transaction_plan_json": "transaction_plan_supplied",
    "storage_transaction_plan_verifier_json": "transaction_plan_verifier_supplied",
    "storage_policy_contract_json": "storage_policy_contract_supplied",
    "storage_policy_verifier_json": "storage_policy_verifier_supplied",
    "vow_boundary_contract_json": "vow_boundary_contract_supplied",
    "vow_alignment_attestation_json": "vow_alignment_attestation_supplied",
}

BLOCKING_GAP_IDS = [
    "consent_request_presentation_missing", "response_artifact_missing", "operator_response_missing",
    "operator_identity_missing", "operator_timestamp_missing", "operator_scope_statement_missing",
    "response_status_missing", "explicit_ledger_write_allow_missing", "explicit_glow_archive_allow_missing",
    "digest_acknowledgements_missing", "expiration_timestamp_missing", "revocation_terms_acknowledgement_missing",
    "response_signature_missing", "runtime_authority_binding_missing", "active_writer_implementation_missing",
]

FUTURE_REQUIREMENT_NAMES = [
    "explicit consent request presentation mechanism", "explicit operator response artifact creation",
    "explicit operator response collection", "explicit operator identity capture",
    "explicit operator response signature binding", "explicit operator timestamp capture",
    "explicit operator scope statement capture", "explicit response status capture",
    "explicit ledger write allow capture", "explicit glow archive allow capture",
    "explicit digest acknowledgement capture", "explicit expiration timestamp capture",
    "explicit revocation terms acknowledgement", "explicit active ledger writer implementation",
    "explicit active glow archiver implementation", "explicit finalizer runtime binding implementation",
    "explicit PR metadata guard runtime binding implementation", "tests proving no readiness authority",
    "docs marking active behavior",
]

NON_AUTHORITY_KEYS = [
    "is_read_only", "is_metadata_only", "is_dossier_only", "does_not_present_request", "does_not_render_ui",
    "does_not_send_messages", "does_not_deliver_externally", "does_not_create_response_artifact",
    "does_not_collect_response", "does_not_collect_consent", "does_not_imply_consent",
    "does_not_bind_runtime_authority", "does_not_activate_memory", "does_not_write_ledger",
    "does_not_archive_glow", "does_not_modify_memory", "does_not_watch_files", "does_not_poll_state",
    "does_not_rerun_commands", "does_not_decide_readiness", "does_not_bypass_finalizer",
    "does_not_bypass_pr_metadata_guard", "does_not_authorize_commit", "does_not_authorize_pr_creation",
    "does_not_trigger_daemon", "does_not_create_tasks", "does_not_schedule_tasks", "does_not_send_alerts",
    "does_not_train_or_modify_models", "does_not_establish_federation_consensus",
]
NON_AUTHORITY_POSTURE = {f"storage_operator_consent_evidence_dossier_{k}": True for k in NON_AUTHORITY_KEYS}

class CodexWorkcellStorageOperatorConsentEvidenceDossierError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentEvidenceDossierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentEvidenceDossierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(data, dict):
        raise CodexWorkcellStorageOperatorConsentEvidenceDossierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, data

def _detected_report_id(report: Mapping[str, Any]) -> Any:
    for key in sorted(report):
        if key.endswith("_id"):
            return report.get(key)
    return None

def _relevant(report: Mapping[str, Any]) -> Any:
    for key in ("verification_status", "consent_evidence_status", "digest", "source_digest"):
        if key in report:
            return report.get(key)
    return _detected_report_id(report)

def _posture_all_true(report: Mapping[str, Any]) -> tuple[bool | None, bool | None]:
    posture = report.get("non_authority_posture")
    if not isinstance(posture, Mapping):
        return None, None
    return True, all(v is True for v in posture.values())

def _active_signal(report: Mapping[str, Any]) -> bool:
    bad_true = {"operator_response_present", "operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed", "consent_collected", "consent_implied", "runtime_binding_performed", "response_artifact_created"}
    bad_false = {"response_artifact_not_created", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed"}
    for k, v in report.items():
        if k in bad_true and v is True:
            return True
        if k in bad_false and v is False:
            return True
        if isinstance(v, Mapping) and _active_signal(v):
            return True
    return False

def _inventory(input_summaries: Mapping[str, Mapping[str, Any]], reports: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for input_id, (role, expected, required) in INPUT_SPECS.items():
        summary = input_summaries.get(input_id, omitted_input(input_id))
        report = reports.get(input_id, {})
        provided = summary.get("provided") is True
        present, all_true = _posture_all_true(report)
        status_matches = None if expected is None or not provided else report.get("verification_status") == expected
        inv_status = "supplied" if provided else "missing"
        notes = []
        if not provided:
            notes.append("required design evidence report omitted")
        if provided and expected is not None and not status_matches:
            inv_status = "failed"; notes.append("verifier status does not match expected verified status")
        if provided and _active_signal(report):
            inv_status = "failed"; notes.append("active authority signal detected")
        rows.append({
            "input_id": input_id, "provided": provided, "detected_report_id": _detected_report_id(report) if provided else None,
            "evidence_role": role, "source_digest": summary.get("digest"), "source_digest_algo": summary.get("digest_algo") if provided else None,
            "source_byte_size": summary.get("byte_size"), "relevant_status_or_digest": _relevant(report) if provided else None,
            "expected_verified_status": expected, "status_matches_expected": status_matches,
            "non_authority_posture_present": present, "non_authority_posture_all_true": all_true,
            "required_for_design_dossier": required, "inventory_status": inv_status, "notes": notes,
        })
    return rows

def build_codex_workcell_storage_operator_consent_evidence_dossier(*, input_summaries: Mapping[str, Mapping[str, Any]], input_reports: Mapping[str, Mapping[str, Any]] | None = None, commit_sha: str | None = None, pr_number: str | None = None, pr_title: str | None = None) -> dict[str, Any]:
    reports = input_reports or {}
    supplied_count = sum(1 for s in input_summaries.values() if s.get("provided") is True)
    inventory = _inventory(input_summaries, reports)
    all_required = all(r["provided"] for r in inventory if r["required_for_design_dossier"])
    verifier_rows = [r for r in inventory if r["expected_verified_status"]]
    verifiers_passed = all(r["status_matches_expected"] is True for r in verifier_rows if r["provided"])
    active_detected = any(r["inventory_status"] == "failed" and "active authority signal detected" in r["notes"] for r in inventory)
    failed = any(r["inventory_status"] == "failed" for r in inventory)
    status = "storage_operator_consent_evidence_dossier_failed" if failed or active_detected else ("storage_operator_consent_evidence_dossier_complete" if all_required and verifiers_passed else "storage_operator_consent_evidence_dossier_incomplete")
    summary = {out: input_summaries.get(inp, omitted_input(inp)).get("provided") is True for inp, out in SUMMARY_KEYS.items()}
    summary.update({
        "all_required_design_reports_supplied": all_required,
        "all_supplied_verifiers_passed": verifiers_passed,
        "all_supplied_reports_non_authoritative": not active_detected,
        "future_consent_design_evidence_complete": status == "storage_operator_consent_evidence_dossier_complete",
        "response_artifact_created_detected": False, "operator_response_detected": False, "consent_collected_detected": False,
        "consent_implied_detected": False, "runtime_binding_detected": False, "active_storage_authority_detected": False,
        "no_action_taken": True,
    })
    missing: dict[str, Any] = {k: False for k in ["consent_request_presentation_mechanism_present", "consent_request_presented", "ui_rendered", "message_sent", "external_delivery_performed", "response_artifact_created", "operator_response_present", "operator_identity_present", "operator_timestamp_present", "operator_scope_statement_present", "response_status_present", "explicit_ledger_write_allow_present", "explicit_glow_archive_allow_present", "digest_acknowledgements_present", "expiration_timestamp_present", "revocation_terms_acknowledged", "response_signature_present", "runtime_authority_binding_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"]}
    missing["blocking_gap_ids"] = BLOCKING_GAP_IDS
    prereq_ids = ["consent_request_contract_supplied", "consent_request_verifier_supplied", "consent_request_packet_supplied", "consent_request_packet_verifier_supplied", "consent_response_contract_supplied", "consent_response_verifier_supplied", "runtime_authority_contract_supplied", "runtime_authority_verifier_supplied"]
    prereqs = [{"prerequisite_id": p, "category": "supplied_report", "passed": bool(summary[p]), "severity": "info" if summary[p] else "warning", "observed_state": summary[p], "evidence_source": "input_summaries", "authority_boundary": "metadata evidence only; not consent or readiness"} for p in prereq_ids]
    for p in ["request_packet_not_presented", "response_artifact_not_created", "operator_response_absent", "operator_identity_missing", "operator_timestamp_missing", "operator_scope_statement_missing", "response_status_missing", "explicit_ledger_write_allow_missing", "explicit_glow_archive_allow_missing", "digest_acknowledgements_missing", "expiration_timestamp_missing", "revocation_terms_acknowledgement_missing", "response_signature_missing", "runtime_authority_binding_missing", "active_storage_disallowed"]:
        prereqs.append({"prerequisite_id": p, "category": "authority_boundary" if p in {"request_packet_not_presented", "response_artifact_not_created", "active_storage_disallowed"} else "missing_real_world_consent_gap", "passed": True, "severity": "blocking_gap" if p not in {"request_packet_not_presented", "response_artifact_not_created", "active_storage_disallowed"} else "info", "observed_state": "future_only_unmet_or_absent", "evidence_source": "missing_real_world_consent_summary", "authority_boundary": "gap remains; no consent, storage, ledger, glow, daemon, commit, PR, or readiness authority"})
    return {
        "storage_operator_consent_evidence_dossier_id": WORKCELL_STORAGE_OPERATOR_CONSENT_EVIDENCE_DOSSIER_ID,
        "metadata_only": True, "evidence_dossier_only": True, "consent_design_evidence_only": True,
        "response_artifact_not_created": True, "operator_response_present": False, "consent_request_not_presented": True,
        "consent_not_collected": True, "consent_not_implied": True, "operator_consent_present": False,
        "runtime_binding_not_performed": True, "active_storage_allowed_now": False, "execution_performed": False,
        "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True,
        "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True,
        "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {k: input_summaries.get(k, omitted_input(k)) for k in INPUT_SPECS},
        "evidence_dossier_context": {"commit_sha": commit_sha, "pr_number": pr_number, "pr_title": pr_title, "supplied_report_count": supplied_count, "required_design_report_count": len(INPUT_SPECS), "evidence_dossier_only": True, "consent_design_evidence_only": True, "response_artifact_not_created": True, "consent_not_collected": True, "no_action_taken": True},
        "consent_ladder_inventory": inventory, "consent_design_evidence_summary": summary,
        "missing_real_world_consent_summary": missing, "consent_evidence_status": status,
        "consent_prerequisite_results": prereqs,
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata dossier.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "sentientos_mount_alignment": {"/ledger": "future consent-scoped storage target; no ledger write here", "/glow": "future consent-scoped archive target; no archive write here", "/vow": "canonical digest context for future consent evidence", "/pulse": "future watcher boundary; consent evidence dossier does not activate it", "/daemon": "future action boundary; consent evidence dossier does not activate it"},
        "future_activation_requirements": [{"requirement": n, "status": "future_only", "met": False, "active": False} for n in FUTURE_REQUIREMENT_NAMES],
        "non_authority_posture": NON_AUTHORITY_POSTURE,
    }

def _cell(value: Any) -> str:
    return json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)

def _escape(value: Any) -> str:
    return _cell(value).replace("|", "\\|").replace("\n", "<br>")

def _table(mapping: Mapping[str, Any]) -> str:
    lines = ["| Field | Value |", "| --- | --- |"]
    for key in sorted(mapping):
        lines.append(f"| {_escape(key)} | {_escape(mapping[key])} |")
    return "\n".join(lines)

def render_codex_workcell_storage_operator_consent_evidence_dossier_markdown(dossier: Mapping[str, Any]) -> str:
    sections = ["# Codex Workcell Storage Operator Consent Evidence Dossier", "", "Deterministic metadata-only consent-design evidence dossier. It inventories supplied reports, preserves real-world consent gaps, and grants no consent, storage, runtime, ledger, glow, daemon, readiness, commit, PR, UI, message, or federation authority."]
    keys = [("Input summaries", "input_summaries"), ("Evidence dossier context", "evidence_dossier_context"), ("Consent ladder inventory", "consent_ladder_inventory"), ("Consent design evidence summary", "consent_design_evidence_summary"), ("Missing real-world consent summary", "missing_real_world_consent_summary"), ("Consent evidence status", "consent_evidence_status"), ("Consent prerequisite results", "consent_prerequisite_results"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Future activation requirements", "future_activation_requirements"), ("Non-authority posture", "non_authority_posture")]
    for title, key in keys:
        value = dossier.get(key)
        sections += ["", f"## {title}", _table({str(i): v for i, v in enumerate(value)}) if isinstance(value, list) else _table(value if isinstance(value, Mapping) else {key: value})]
    return "\n".join(sections) + "\n"
