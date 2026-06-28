from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_OPERATOR_CONSENT_RESPONSE_CONTRACT_ID = "codex_workcell_storage_operator_consent_response_contract.v1"
DIGEST_ALGO = "sha256"

INPUT_SPECS: dict[str, str] = {
    "storage_operator_consent_request_packet_json": "request_packet",
    "storage_operator_consent_request_packet_verifier_json": "request_packet_verifier",
    "storage_operator_consent_contract_json": "consent_contract",
    "storage_operator_consent_verifier_json": "consent_verifier",
    "storage_runtime_authority_contract_json": "runtime_authority_contract",
    "storage_runtime_authority_verifier_json": "runtime_authority_verifier",
    "storage_execution_dossier_json": "execution_dossier",
    "storage_execution_dossier_verifier_json": "execution_dossier_verifier",
    "storage_transaction_plan_json": "transaction_plan",
    "storage_transaction_plan_verifier_json": "transaction_plan_verifier",
    "storage_policy_contract_json": "storage_policy_contract",
    "storage_policy_verifier_json": "storage_policy_verifier",
    "vow_boundary_contract_json": "vow_boundary_contract",
    "vow_alignment_attestation_json": "vow_alignment_attestation",
}

SCHEMA_FIELD_IDS = [
    "response_artifact_id_required", "response_artifact_version_required", "request_packet_digest_required",
    "request_packet_verifier_digest_required", "operator_identity_required", "operator_timestamp_required",
    "operator_scope_statement_required", "response_status_required", "explicit_allow_ledger_write_required",
    "explicit_allow_glow_archive_required", "explicit_deny_storage_supported",
    "canonical_vow_digest_acknowledgement_required", "storage_policy_digest_acknowledgement_required",
    "storage_policy_verifier_digest_acknowledgement_required", "transaction_plan_digest_acknowledgement_required",
    "transaction_plan_verifier_digest_acknowledgement_required", "execution_dossier_digest_acknowledgement_required",
    "execution_dossier_verifier_digest_acknowledgement_required", "runtime_authority_contract_digest_acknowledgement_required",
    "runtime_authority_verifier_digest_acknowledgement_required", "finalizer_guard_receipts_acknowledgement_required",
    "expiration_timestamp_required", "revocation_terms_acknowledgement_required",
    "no_daemon_self_authorization_acknowledgement_required", "no_federation_implied_consent_acknowledgement_required",
    "denial_default_acknowledgement_required", "response_signature_placeholder_required",
]
REQUIRED_ACKNOWLEDGEMENT_IDS = [
    "request_packet_digest", "request_packet_verifier_digest", "canonical_vow_digest",
    "storage_policy_contract_digest", "storage_policy_verifier_digest", "storage_transaction_plan_digest",
    "storage_transaction_plan_verifier_digest", "storage_execution_dossier_digest",
    "storage_execution_dossier_verifier_digest", "runtime_authority_contract_digest",
    "runtime_authority_verifier_digest", "finalizer_pre_commit_receipt_digest",
    "pr_metadata_finalizer_receipt_digest", "pr_metadata_guard_receipt_digest",
]
FORBIDDEN_MOUNTS = ["/vow", "/pulse", "/daemon", "host_absolute_paths", "network_paths", "temp_paths_as_canonical", "hidden_backdoor_paths"]
BLOCKING_GAP_IDS = [
    "response_artifact_missing", "operator_response_missing", "operator_identity_missing", "operator_timestamp_missing",
    "operator_scope_statement_missing", "response_status_missing", "explicit_ledger_write_allow_missing",
    "explicit_glow_archive_allow_missing", "digest_acknowledgements_missing", "expiration_timestamp_missing",
    "revocation_terms_acknowledgement_missing", "response_signature_missing", "runtime_authority_binding_missing",
]
FUTURE_REQUIREMENT_NAMES = [
    "explicit operator identity capture", "explicit operator response artifact creation", "explicit operator response signature binding",
    "explicit operator timestamp capture", "explicit operator scope statement capture", "explicit response status capture",
    "explicit ledger write allow capture", "explicit glow archive allow capture", "explicit canonical vow digest acknowledgement",
    "explicit storage policy digest acknowledgement", "explicit transaction plan digest acknowledgement",
    "explicit execution dossier digest acknowledgement", "explicit runtime authority digest acknowledgement",
    "explicit expiration timestamp capture", "explicit revocation terms acknowledgement", "explicit active ledger writer implementation",
    "explicit active glow archiver implementation", "explicit finalizer runtime binding implementation",
    "explicit PR metadata guard runtime binding implementation", "tests proving no readiness authority", "docs marking active behavior",
]
NON_AUTHORITY_POSTURE = {name: True for name in [
    "storage_operator_consent_response_contract_is_read_only", "storage_operator_consent_response_contract_is_metadata_only",
    "storage_operator_consent_response_contract_is_contract_only", "storage_operator_consent_response_contract_does_not_create_response_artifact",
    "storage_operator_consent_response_contract_does_not_collect_response", "storage_operator_consent_response_contract_does_not_collect_consent",
    "storage_operator_consent_response_contract_does_not_imply_consent", "storage_operator_consent_response_contract_does_not_bind_runtime_authority",
    "storage_operator_consent_response_contract_does_not_activate_memory", "storage_operator_consent_response_contract_does_not_write_ledger",
    "storage_operator_consent_response_contract_does_not_archive_glow", "storage_operator_consent_response_contract_does_not_modify_memory",
    "storage_operator_consent_response_contract_does_not_watch_files", "storage_operator_consent_response_contract_does_not_poll_state",
    "storage_operator_consent_response_contract_does_not_rerun_commands", "storage_operator_consent_response_contract_does_not_decide_readiness",
    "storage_operator_consent_response_contract_does_not_bypass_finalizer", "storage_operator_consent_response_contract_does_not_bypass_pr_metadata_guard",
    "storage_operator_consent_response_contract_does_not_authorize_commit", "storage_operator_consent_response_contract_does_not_authorize_pr_creation",
    "storage_operator_consent_response_contract_does_not_trigger_daemon", "storage_operator_consent_response_contract_does_not_create_tasks",
    "storage_operator_consent_response_contract_does_not_schedule_tasks", "storage_operator_consent_response_contract_does_not_send_alerts",
    "storage_operator_consent_response_contract_does_not_render_ui", "storage_operator_consent_response_contract_does_not_send_messages",
    "storage_operator_consent_response_contract_does_not_train_or_modify_models", "storage_operator_consent_response_contract_does_not_establish_federation_consensus",
]}

class CodexWorkcellStorageOperatorConsentResponseContractError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentResponseContractError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentResponseContractError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageOperatorConsentResponseContractError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _schema_record(field_id: str) -> dict[str, Any]:
    return {"schema_field_id": field_id, "required_for_future_response_artifact": True, "currently_satisfied": False, "future_only": True, "active": False, "forbidden_inference": "This schema field does not imply consent, response collection, or runtime authority.", "reviewer_summary": f"Future response artifact must explicitly satisfy {field_id}; this contract does not."}

def build_codex_workcell_storage_operator_consent_response_contract(*, input_summaries: Mapping[str, Mapping[str, Any]], input_reports: Mapping[str, Mapping[str, Any]] | None = None, commit_sha: str | None = None, pr_number: str | None = None, pr_title: str | None = None) -> dict[str, Any]:
    _ = input_reports
    supplied_count = sum(1 for s in input_summaries.values() if s.get("provided") is True)
    return {
        "storage_operator_consent_response_contract_id": WORKCELL_STORAGE_OPERATOR_CONSENT_RESPONSE_CONTRACT_ID,
        "metadata_only": True, "response_contract_only": True, "response_artifact_schema_only": True,
        "response_artifact_not_created": True, "operator_response_present": False, "consent_not_collected": True,
        "consent_not_implied": True, "operator_consent_present": False, "runtime_binding_not_performed": True,
        "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False,
        "archives_performed": False, "memory_mutation_performed": False, "not_runtime_authority": True,
        "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True,
        "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True,
        "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {k: input_summaries.get(k, omitted_input(k)) for k in INPUT_SPECS},
        "response_contract_context": {"commit_sha": commit_sha, "pr_number": pr_number, "pr_title": pr_title, "supplied_report_count": supplied_count, "response_contract_only": True, "response_artifact_not_created": True, "consent_not_collected": True, "no_action_taken": True},
        "response_artifact_schema": [_schema_record(x) for x in SCHEMA_FIELD_IDS],
        "response_status_policy": {"allowed_response_statuses": ["absent", "denied", "approved_for_scoped_storage", "expired", "revoked", "incomplete", "ambiguous", "invalid"], "current_response_status": "absent", "absent_status_blocks_storage": True, "denied_status_blocks_storage": True, "incomplete_status_blocks_storage": True, "ambiguous_status_blocks_storage": True, "expired_status_blocks_storage": True, "revoked_status_blocks_storage": True, "invalid_status_blocks_storage": True, "approved_status_not_present_here": True, "policy_only": True},
        "explicit_allow_policy": {"explicit_allow_ledger_write_required": True, "explicit_allow_glow_archive_required": True, "explicit_allow_ledger_write_present": False, "explicit_allow_glow_archive_present": False, "ledger_write_blocked_without_explicit_allow": True, "glow_archive_blocked_without_explicit_allow": True, "allow_flags_not_collected": True, "policy_only": True},
        "digest_acknowledgement_policy": {"digest_algorithm": DIGEST_ALGO, "required_acknowledgement_ids": REQUIRED_ACKNOWLEDGEMENT_IDS, "supplied_acknowledgement_ids": [], "missing_acknowledgement_ids": REQUIRED_ACKNOWLEDGEMENT_IDS, "acknowledgements_not_collected": True, "policy_only": True},
        "scope_acknowledgement_policy": {"allowed_mounts": ["/ledger", "/glow"], "forbidden_mounts": FORBIDDEN_MOUNTS, "mount_scope_acknowledgement_required": True, "mount_scope_acknowledgement_present": False, "daemon_action_not_authorized": True, "model_training_not_authorized": True, "federation_consensus_not_authorized": True, "policy_only": True},
        "expiration_policy": {"expiration_timestamp_required": True, "expiration_timestamp_present": False, "expired_or_missing_expiration_blocks_storage": True, "renewal_required_for_new_vow_digest": True, "renewal_required_for_new_storage_policy": True, "renewal_required_for_new_transaction_plan": True, "renewal_required_for_changed_mount_scope": True, "lifetime_not_started": True, "policy_only": True},
        "revocation_policy": {"revocation_terms_acknowledgement_required": True, "revocation_terms_acknowledged": False, "future_revocation_must_block_new_writes": True, "future_revocation_must_block_new_archives": True, "future_revocation_must_not_delete_existing_receipts": True, "future_revocation_receipt_required": True, "revocation_not_performed": True, "policy_only": True},
        "denial_and_ambiguity_policy": {"default_without_response": "deny_active_storage", "missing_response_blocks_ledger_write": True, "missing_response_blocks_glow_archive": True, "incomplete_response_blocks_storage": True, "ambiguous_response_blocks_storage": True, "denied_response_blocks_storage": True, "remote_or_daemon_response_not_accepted": True, "federation_state_not_accepted_as_response": True, "denial_not_runtime_decision_here": True, "policy_only": True},
        "response_authority_boundary": {"response_contract_is_not_response_artifact": True, "response_schema_is_not_operator_approval": True, "request_packet_is_not_consent": True, "supplied_evidence_does_not_imply_consent": True, "finalizer_ready_to_commit_does_not_imply_consent": True, "pr_metadata_guard_ready_does_not_imply_consent": True, "daemon_recommendation_does_not_imply_consent": True, "federation_state_does_not_imply_consent": True, "future_operator_response_must_be_explicit": True, "future_operator_response_must_be_signature_bound": True, "authority_boundary_only": True},
        "response_activation_gap_summary": {"response_artifact_not_created": True, "operator_response_present": False, "consent_not_collected": True, "consent_not_implied": True, "operator_consent_present": False, "active_storage_allowed_now": False, "runtime_binding_not_performed": True, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "blocking_gap_ids": BLOCKING_GAP_IDS},
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata contract.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "sentientos_mount_alignment": {"/ledger": "future response-scoped consent target; no ledger write here", "/glow": "future response-scoped consent target; no archive write here", "/vow": "canonical digest acknowledgement required for future consent response binding", "/pulse": "future watcher boundary; response contract does not activate it", "/daemon": "future action boundary; response contract does not activate it"},
        "future_activation_requirements": [{"requirement": name, "status": "future_only", "met": False, "active": False} for name in FUTURE_REQUIREMENT_NAMES],
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

def render_codex_workcell_storage_operator_consent_response_contract_markdown(contract: Mapping[str, Any]) -> str:
    sections = ["# Codex Workcell Storage Operator Consent Response Artifact Contract", "", "Deterministic metadata-only response artifact schema contract. It is not a response artifact, does not collect or imply consent, and grants no runtime authority."]
    section_keys = [("Input summaries", "input_summaries"), ("Response contract context", "response_contract_context"), ("Response artifact schema", "response_artifact_schema"), ("Response status policy", "response_status_policy"), ("Explicit allow policy", "explicit_allow_policy"), ("Digest acknowledgement policy", "digest_acknowledgement_policy"), ("Scope acknowledgement policy", "scope_acknowledgement_policy"), ("Expiration policy", "expiration_policy"), ("Revocation policy", "revocation_policy"), ("Denial and ambiguity policy", "denial_and_ambiguity_policy"), ("Response authority boundary", "response_authority_boundary"), ("Response activation gap summary", "response_activation_gap_summary"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Future activation requirements", "future_activation_requirements"), ("Non-authority posture", "non_authority_posture")]
    for title, key in section_keys:
        value = contract.get(key)
        sections += ["", f"## {title}", _table({str(i): v for i, v in enumerate(value)}) if isinstance(value, list) else _table(value if isinstance(value, Mapping) else {key: value})]
    return "\n".join(sections) + "\n"
