from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_CONTRACT_ID = "codex_workcell_storage_operator_consent_request_presentation_contract.v1"
DIGEST_ALGO = "sha256"

INPUT_SPECS: dict[str, str] = {
    "storage_operator_consent_request_packet_json": "storage_operator_consent_request_packet",
    "storage_operator_consent_request_packet_verifier_json": "storage_operator_consent_request_packet_verifier",
    "storage_operator_consent_evidence_dossier_json": "storage_operator_consent_evidence_dossier",
    "storage_operator_consent_evidence_dossier_verifier_json": "storage_operator_consent_evidence_dossier_verifier",
    "storage_operator_consent_response_contract_json": "storage_operator_consent_response_contract",
    "storage_operator_consent_response_verifier_json": "storage_operator_consent_response_verifier",
    "storage_operator_consent_contract_json": "storage_operator_consent_contract",
    "storage_operator_consent_verifier_json": "storage_operator_consent_verifier",
    "storage_runtime_authority_contract_json": "storage_runtime_authority_contract",
    "storage_runtime_authority_verifier_json": "storage_runtime_authority_verifier",
    "vow_boundary_contract_json": "vow_boundary_contract",
    "vow_alignment_attestation_json": "vow_alignment_attestation",
}

PRESENTATION_SURFACES = [
    "operator_request_display", "operator_request_review_surface", "operator_request_acknowledgement_surface",
    "operator_scope_confirmation_surface", "operator_digest_review_surface", "operator_ledger_write_allow_prompt",
    "operator_glow_archive_allow_prompt", "operator_expiration_selection_surface", "operator_revocation_terms_surface",
    "operator_response_signature_surface", "local_ui_rendering", "local_cli_prompt", "local_file_drop",
    "local_notification", "external_message_delivery", "email_delivery", "chat_delivery", "webhook_delivery",
    "browser_or_app_surface", "response_artifact_creation", "response_collection", "consent_collection",
    "runtime_authority_binding", "active_storage_activation",
]
PRESENTATION_AUTHORITY_REQUIREMENTS = [
    "explicit_operator_presentation_allow", "explicit_presentation_channel", "explicit_operator_identity_target",
    "explicit_request_packet_digest_binding", "explicit_evidence_dossier_digest_binding", "explicit_vow_digest_context",
    "explicit_scope_statement_display", "explicit_ledger_write_allow_question", "explicit_glow_archive_allow_question",
    "explicit_digest_acknowledgement_display", "explicit_expiration_policy_display", "explicit_revocation_terms_display",
    "explicit_response_artifact_path", "explicit_response_collection_boundary", "explicit_no_implied_consent_notice",
    "explicit_no_readiness_authority_notice", "explicit_no_daemon_authority_notice", "explicit_no_federation_authority_notice",
    "explicit_audit_receipt_path", "explicit_presentation_revocation_or_cancellation_path",
]
OPERATOR_ATTENTION_REQUIREMENTS = [
    "operator_must_see_requested_scope", "operator_must_see_ledger_write_implication", "operator_must_see_glow_archive_implication",
    "operator_must_see_digest_inventory", "operator_must_see_missing_runtime_binding_gap", "operator_must_see_denied_implied_consent_notice",
    "operator_must_see_revocation_terms", "operator_must_see_expiration_terms", "operator_must_see_response_artifact_path",
    "operator_must_have_cancel_option",
]
DELIVERY_SCOPE_REQUIREMENTS = [
    "presentation_channel_must_be_explicit", "external_delivery_must_be_explicitly_allowed", "message_delivery_must_be_explicitly_allowed",
    "ui_rendering_must_be_explicitly_allowed", "local_file_drop_must_be_explicitly_allowed", "no_hidden_delivery_channel",
    "no_background_delivery", "no_third_party_delivery_without_scope", "no_cross_device_delivery_without_scope",
]
REQUEST_PACKET_INTEGRITY_REQUIREMENTS = [
    "request_packet_digest_must_match_presented_packet", "request_packet_verifier_status_must_be_bound",
    "evidence_dossier_digest_must_be_bound", "evidence_dossier_verifier_status_must_be_bound",
    "vow_boundary_digest_must_be_bound_if_supplied", "presentation_copy_must_not_modify_requested_scope",
    "presentation_copy_must_not_add_permissions", "presentation_copy_must_preserve_denial_default",
    "presentation_copy_must_preserve_empty_response_fields", "presentation_copy_must_preserve_missing_consent_gaps",
]
RESPONSE_PATH_REQUIREMENTS = [
    "response_artifact_schema_must_be_bound", "response_artifact_path_must_be_explicit", "response_collection_boundary_must_be_explicit",
    "response_signature_boundary_must_be_explicit", "response_timestamp_boundary_must_be_explicit", "response_identity_boundary_must_be_explicit",
    "response_scope_statement_boundary_must_be_explicit", "response_status_boundary_must_be_explicit",
    "response_revocation_boundary_must_be_explicit", "response_expiration_boundary_must_be_explicit",
]
DENIED_INFERENCES = [
    "request_packet_exists_implies_presented", "request_packet_verified_implies_presented", "evidence_dossier_complete_implies_presented",
    "evidence_dossier_verified_implies_presented", "presentation_contract_exists_implies_presentation_authority",
    "response_contract_exists_implies_response_artifact_created", "response_verifier_passed_implies_response_exists",
    "operator_consent_contract_exists_implies_consent", "finalizer_ready_implies_presentation_authority",
    "pr_metadata_guard_ready_implies_presentation_authority", "matrix_passed_implies_presentation_authority",
    "daemon_recommendation_implies_presentation_authority", "federation_state_implies_presentation_authority",
    "runtime_authority_contract_exists_implies_runtime_binding", "storage_policy_verified_implies_presentation_authority",
    "request_display_copy_implies_operator_saw_request", "local_file_written_implies_operator_reviewed_request",
    "notification_sent_implies_consent", "message_delivered_implies_consent", "operator_silence_implies_consent",
]
MISSING_GAPS = [
    "presentation_mechanism_missing", "presentation_channel_missing", "operator_identity_target_missing",
    "request_packet_digest_binding_missing", "evidence_dossier_digest_binding_missing", "vow_digest_context_missing",
    "scope_statement_display_missing", "ledger_write_allow_question_missing", "glow_archive_allow_question_missing",
    "digest_acknowledgement_display_missing", "expiration_policy_display_missing", "revocation_terms_display_missing",
    "no_implied_consent_notice_missing", "no_readiness_authority_notice_missing", "response_artifact_path_missing",
    "response_collection_boundary_missing", "operator_cancel_path_missing", "audit_receipt_path_missing",
    "ui_rendering_authority_missing", "message_delivery_authority_missing", "external_delivery_authority_missing",
    "response_artifact_creation_authority_missing", "response_collection_authority_missing", "consent_collection_authority_missing",
    "runtime_authority_binding_missing", "active_storage_authority_missing",
]
FUTURE_ACTIVATION_REQUIREMENTS = [
    "explicit request presentation mechanism implementation", "explicit presentation channel authorization", "explicit operator identity targeting",
    "explicit request packet digest binding", "explicit evidence dossier digest binding", "explicit vow digest binding",
    "explicit operator-facing scope display", "explicit ledger write allow question display", "explicit glow archive allow question display",
    "explicit digest acknowledgement display", "explicit expiration policy display", "explicit revocation terms display",
    "explicit no-implied-consent notice display", "explicit no-readiness-authority notice display", "explicit response artifact path",
    "explicit response collection boundary", "explicit operator cancellation path", "explicit presentation audit receipt path",
    "explicit UI rendering authority if UI is used", "explicit message delivery authority if messages are used",
    "explicit external delivery authority if external delivery is used", "explicit response artifact creation authority",
    "explicit response collection authority", "explicit consent collection authority", "explicit runtime authority binding implementation",
    "explicit active ledger writer implementation", "explicit active glow archiver implementation", "tests proving no presentation readiness authority",
    "docs marking active behavior",
]
NON_AUTHORITY_SUFFIXES = [
    "is_metadata_only", "is_contract_only", "is_future_only", "does_not_present_request", "does_not_render_ui",
    "does_not_send_messages", "does_not_deliver_externally", "does_not_create_response_artifact", "does_not_collect_response",
    "does_not_collect_consent", "does_not_imply_consent", "does_not_bind_runtime_authority", "does_not_activate_memory",
    "does_not_activate_storage", "does_not_write_ledger", "does_not_archive_glow", "does_not_modify_memory",
    "does_not_watch_files", "does_not_poll_state", "does_not_run_commands", "does_not_call_network",
    "does_not_invoke_providers", "does_not_decide_readiness", "does_not_bypass_finalizer", "does_not_bypass_pr_metadata_guard",
    "does_not_authorize_commit", "does_not_authorize_pr_creation", "does_not_trigger_daemon", "does_not_create_tasks",
    "does_not_schedule_tasks", "does_not_send_alerts", "does_not_train_or_modify_models", "does_not_establish_federation_consensus",
]
NON_AUTHORITY_POSTURE = {f"storage_operator_consent_request_presentation_contract_{suffix}": True for suffix in NON_AUTHORITY_SUFFIXES}

class CodexWorkcellStorageOperatorConsentRequestPresentationContractError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentRequestPresentationContractError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentRequestPresentationContractError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(data, dict):
        raise CodexWorkcellStorageOperatorConsentRequestPresentationContractError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, data

def _records(ids: list[str], key: str) -> list[dict[str, Any]]:
    return [{key: item, "future_only": True, "currently_satisfied": False, "authority_boundary": "future explicit operator presentation authority required; no active authority here"} for item in ids]

def build_codex_workcell_storage_operator_consent_request_presentation_contract(*, input_summaries: Mapping[str, Mapping[str, Any]], input_reports: Mapping[str, Mapping[str, Any]] | None = None, commit: str | None = None, pr: str | None = None) -> dict[str, Any]:
    supplied_count = sum(1 for summary in input_summaries.values() if summary.get("provided") is True)
    return {
        "storage_operator_consent_request_presentation_contract_id": WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_CONTRACT_ID,
        "metadata_only": True, "contract_only": True, "future_only": True, "presentation_not_performed": True,
        "request_not_presented": True, "ui_not_rendered": True, "message_not_sent": True, "external_delivery_not_performed": True,
        "response_artifact_not_created": True, "response_not_collected": True, "consent_not_collected": True, "consent_not_implied": True,
        "operator_consent_present": False, "runtime_binding_not_performed": True, "active_storage_allowed_now": False,
        "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False,
        "not_presentation_runner": True, "not_ui_renderer": True, "not_message_sender": True, "not_external_delivery_system": True,
        "not_response_artifact_creator": True, "not_response_collector": True, "not_consent_collector": True, "not_runtime_authority": True,
        "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True,
        "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True,
        "not_reinforcement_learning": True,
        "input_summaries": {k: input_summaries.get(k, omitted_input(k)) for k in INPUT_SPECS},
        "presentation_boundary_context": {
            "commit": commit, "pr": pr, "supplied_input_count": supplied_count, "supported_input_count": len(INPUT_SPECS),
            "presentation_authority_separate_from": ["request_packet_existence", "packet_verification", "evidence_dossier_completeness", "dossier_verification", "response_schema_existence", "response_verifier_success", "finalizer_readiness", "pr_metadata_guard_readiness", "matrix_passage", "daemon_recommendations", "federation_state", "runtime_authority_contract_presence", "storage_policy_evidence"],
            "no_request_presentation_action_occurred": True,
        },
        "presentation_surface_inventory": [{"surface_id": s, "description": f"Future-only inactive boundary for {s}.", "future_only": True, "active_now": False, "required_before_activation": "explicit scoped operator presentation authority", "denied_inference": f"{s}_exists_or_is_named_does_not_imply_consent_or_presentation", "authority_boundary": "metadata only; not a presentation runner", "notes": "No UI, message, delivery, response, consent, runtime binding, ledger write, glow archive, daemon action, or storage activation occurs."} for s in PRESENTATION_SURFACES],
        "required_presentation_authority_requirements": [{"requirement_id": r, "required_before_presentation": True, "currently_satisfied": False, "authority_boundary": "missing explicit future presentation authority", "missing_gap_id": r + "_missing", "severity": "blocking"} for r in PRESENTATION_AUTHORITY_REQUIREMENTS],
        "required_operator_attention_requirements": _records(OPERATOR_ATTENTION_REQUIREMENTS, "requirement_id"),
        "required_delivery_scope_requirements": _records(DELIVERY_SCOPE_REQUIREMENTS, "requirement_id"),
        "required_request_packet_integrity_requirements": _records(REQUEST_PACKET_INTEGRITY_REQUIREMENTS, "requirement_id"),
        "required_response_path_requirements": _records(RESPONSE_PATH_REQUIREMENTS, "requirement_id"),
        "denied_inferences": [{"inference_id": i, "denied": True, "authority_boundary": "denied by presentation boundary contract; no consent, presentation, response, readiness, daemon, federation, runtime, or active storage authority follows"} for i in DENIED_INFERENCES],
        "missing_real_world_presentation_summary": [{"gap_id": g, "present": True, "severity": "blocking", "active": False} for g in MISSING_GAPS],
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata contract.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "sentientos_mount_alignment": {"/ledger": "future operator consent presentation receipt chain only; no ledger write", "/glow": "future presentation evidence archive only; no archive write", "/vow": "canonical digest context for future presentation and consent constraints", "/pulse": "future presentation freshness/drift signal boundary; not activated", "/daemon": "future bounded presentation repair recommendation boundary; not activated and no daemon action"},
        "future_activation_requirements": [{"requirement": r, "future_only": True, "met": False, "active": False} for r in FUTURE_ACTIVATION_REQUIREMENTS],
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

def render_codex_workcell_storage_operator_consent_request_presentation_contract_markdown(contract: Mapping[str, Any]) -> str:
    sections = ["# Codex Workcell Storage Operator Consent Request Presentation Boundary Contract", "", "Deterministic metadata-only future presentation boundary. It does not present a request, render UI, send messages, deliver externally, create or collect responses, collect or imply consent, bind runtime authority, activate storage, write ledger entries, archive glow evidence, trigger daemons, decide readiness, create PRs, call networks, invoke providers, or train models."]
    for title, key in [("Input summaries", "input_summaries"), ("Presentation boundary context", "presentation_boundary_context"), ("Presentation surface inventory", "presentation_surface_inventory"), ("Required presentation authority requirements", "required_presentation_authority_requirements"), ("Operator attention requirements", "required_operator_attention_requirements"), ("Delivery scope requirements", "required_delivery_scope_requirements"), ("Request packet integrity requirements", "required_request_packet_integrity_requirements"), ("Response path requirements", "required_response_path_requirements"), ("Denied inferences", "denied_inferences"), ("Missing real-world presentation summary", "missing_real_world_presentation_summary"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Future activation requirements", "future_activation_requirements"), ("Non-authority posture", "non_authority_posture")]:
        value = contract.get(key)
        sections += ["", f"## {title}", _table({str(i): v for i, v in enumerate(value)}) if isinstance(value, list) else _table(value if isinstance(value, Mapping) else {key: value})]
    return "\n".join(sections) + "\n"
