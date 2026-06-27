from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PACKET_ID = "codex_workcell_storage_operator_consent_request_packet.v1"
DIGEST_ALGO = "sha256"

INPUT_SPECS: dict[str, str] = {
    "storage_operator_consent_contract_json": "consent_contract",
    "storage_operator_consent_verifier_json": "consent_contract_verifier",
    "storage_runtime_authority_contract_json": "runtime_authority_contract",
    "storage_runtime_authority_verifier_json": "runtime_authority_verifier",
    "storage_execution_dossier_json": "execution_dossier",
    "storage_execution_dossier_verifier_json": "execution_dossier_verifier",
    "storage_transaction_plan_json": "transaction_plan",
    "storage_transaction_plan_verifier_json": "transaction_plan_verifier",
    "storage_policy_contract_json": "storage_policy",
    "storage_policy_verifier_json": "storage_policy_verifier",
    "vow_boundary_contract_json": "vow_boundary",
    "vow_alignment_attestation_json": "vow_attestation",
}

FORBIDDEN_SCOPE = ["/vow", "/pulse", "/daemon", "host_absolute_paths", "network_paths", "temp_paths_as_canonical", "hidden_backdoor_paths"]
REQUIRED_DIGEST_BINDINGS = [
    "canonical_vow_digest", "storage_policy_contract_digest", "storage_policy_verifier_digest",
    "storage_transaction_plan_digest", "storage_transaction_plan_verifier_digest",
    "storage_execution_dossier_digest", "storage_execution_dossier_verifier_digest",
    "runtime_authority_contract_digest", "runtime_authority_verifier_digest",
]
BLOCKING_GAP_IDS = [
    "consent_request_not_presented", "operator_response_missing", "operator_identity_missing",
    "operator_timestamp_missing", "operator_scope_statement_missing", "explicit_ledger_write_allow_missing",
    "explicit_glow_archive_allow_missing", "consent_expiration_missing", "consent_revocation_terms_missing",
    "consent_digest_acknowledgements_missing", "runtime_authority_binding_missing",
]
FUTURE_REQUIREMENT_NAMES = [
    "explicit operator identity capture", "explicit operator consent response capture", "explicit consent request presentation mechanism",
    "explicit consent timestamp capture", "explicit consent expiration policy", "explicit consent revocation policy",
    "explicit canonical vow digest acknowledgement", "explicit storage policy digest acknowledgement",
    "explicit transaction plan digest acknowledgement", "explicit execution dossier digest acknowledgement",
    "explicit runtime authority digest acknowledgement", "explicit active ledger writer implementation",
    "explicit active glow archiver implementation", "explicit finalizer runtime binding implementation",
    "explicit PR metadata guard runtime binding implementation", "explicit storage path enforcement", "explicit retention enforcement",
    "explicit digest verification enforcement", "explicit parent-chain validation enforcement", "tests proving no readiness authority",
    "docs marking active behavior",
]
NON_AUTHORITY_POSTURE = {name: True for name in [
    "storage_operator_consent_request_packet_is_read_only",
    "storage_operator_consent_request_packet_is_metadata_only",
    "storage_operator_consent_request_packet_is_packet_only",
    "storage_operator_consent_request_packet_does_not_present_request",
    "storage_operator_consent_request_packet_does_not_collect_consent",
    "storage_operator_consent_request_packet_does_not_imply_consent",
    "storage_operator_consent_request_packet_does_not_bind_runtime_authority",
    "storage_operator_consent_request_packet_does_not_activate_memory",
    "storage_operator_consent_request_packet_does_not_write_ledger",
    "storage_operator_consent_request_packet_does_not_archive_glow",
    "storage_operator_consent_request_packet_does_not_modify_memory",
    "storage_operator_consent_request_packet_does_not_watch_files",
    "storage_operator_consent_request_packet_does_not_poll_state",
    "storage_operator_consent_request_packet_does_not_rerun_commands",
    "storage_operator_consent_request_packet_does_not_decide_readiness",
    "storage_operator_consent_request_packet_does_not_bypass_finalizer",
    "storage_operator_consent_request_packet_does_not_bypass_pr_metadata_guard",
    "storage_operator_consent_request_packet_does_not_authorize_commit",
    "storage_operator_consent_request_packet_does_not_authorize_pr_creation",
    "storage_operator_consent_request_packet_does_not_trigger_daemon",
    "storage_operator_consent_request_packet_does_not_create_tasks",
    "storage_operator_consent_request_packet_does_not_schedule_tasks",
    "storage_operator_consent_request_packet_does_not_send_alerts",
    "storage_operator_consent_request_packet_does_not_train_or_modify_models",
    "storage_operator_consent_request_packet_does_not_establish_federation_consensus",
]}

class CodexWorkcellStorageOperatorConsentRequestPacketError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentRequestPacketError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentRequestPacketError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageOperatorConsentRequestPacketError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _report_id(data: Mapping[str, Any]) -> Any:
    for key in ("storage_operator_consent_contract_id", "storage_operator_consent_verifier_id", "storage_runtime_authority_contract_id", "storage_runtime_authority_verifier_id", "storage_execution_dossier_id", "storage_execution_dossier_verifier_id", "storage_transaction_plan_id", "storage_transaction_plan_verifier_id", "storage_policy_contract_id", "storage_policy_verifier_id", "vow_boundary_contract_id", "vow_alignment_attestation_id"):
        if data.get(key) is not None:
            return data[key]
    return None

def _status_or_digest(data: Mapping[str, Any]) -> Any:
    for key in ("verification_status", "storage_execution_status", "storage_transaction_plan_verification_status", "storage_policy_verification_status", "digest", "source_digest"):
        if data.get(key) is not None:
            return data[key]
    return None

def build_codex_workcell_storage_operator_consent_request_packet(*, input_summaries: Mapping[str, Mapping[str, Any]], input_reports: Mapping[str, Mapping[str, Any]] | None = None, commit_sha: str | None = None, pr_number: str | None = None, pr_title: str | None = None) -> dict[str, Any]:
    reports = input_reports or {}
    evidence = []
    supplied_bindings: dict[str, str] = {}
    binding_by_input = {
        "vow_boundary_contract_json": "canonical_vow_digest", "storage_policy_contract_json": "storage_policy_contract_digest",
        "storage_policy_verifier_json": "storage_policy_verifier_digest", "storage_transaction_plan_json": "storage_transaction_plan_digest",
        "storage_transaction_plan_verifier_json": "storage_transaction_plan_verifier_digest", "storage_execution_dossier_json": "storage_execution_dossier_digest",
        "storage_execution_dossier_verifier_json": "storage_execution_dossier_verifier_digest", "storage_runtime_authority_contract_json": "runtime_authority_contract_digest",
        "storage_runtime_authority_verifier_json": "runtime_authority_verifier_digest",
    }
    for input_id, role in INPUT_SPECS.items():
        summary = input_summaries.get(input_id, omitted_input(input_id))
        data = reports.get(input_id, {})
        provided = summary.get("provided") is True
        digest = summary.get("digest") if provided else None
        if provided and input_id in binding_by_input and isinstance(digest, str):
            supplied_bindings[binding_by_input[input_id]] = digest
        evidence.append({
            "input_id": input_id, "provided": provided, "detected_report_id": _report_id(data), "evidence_role": role,
            "source_digest": digest, "source_digest_algo": DIGEST_ALGO if provided else None, "source_byte_size": summary.get("byte_size") if provided else None,
            "relevant_status_or_digest": _status_or_digest(data), "required_for_future_consent": True, "included_in_request_packet": provided,
            "missing_reason": None if provided else "optional_input_not_supplied",
        })
    missing_bindings = [b for b in REQUIRED_DIGEST_BINDINGS if b not in supplied_bindings]
    supplied_count = sum(1 for s in input_summaries.values() if s.get("provided") is True)
    return {
        "storage_operator_consent_request_packet_id": WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PACKET_ID,
        "metadata_only": True, "request_packet_only": True, "consent_request_not_presented": True, "consent_not_collected": True,
        "consent_not_implied": True, "operator_consent_present": False, "runtime_binding_not_performed": True,
        "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False, "archives_performed": False,
        "memory_mutation_performed": False, "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True,
        "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True,
        "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {k: input_summaries.get(k, omitted_input(k)) for k in INPUT_SPECS},
        "request_packet_context": {"commit_sha": commit_sha, "pr_number": pr_number, "pr_title": pr_title, "supplied_report_count": supplied_count, "request_packet_only": True, "consent_request_not_presented": True, "consent_not_collected": True, "no_action_taken": True},
        "evidence_digest_packet": evidence,
        "operator_request_template": {"template_id": "storage_operator_consent_request_template.v1", "template_not_presented": True, "response_not_collected": True, "intended_operator_action": "future_explicit_review_only", "requested_scope": ["/ledger", "/glow"], "forbidden_scope": FORBIDDEN_SCOPE, "requested_permissions": ["explicit_allow_ledger_write", "explicit_allow_glow_archive"], "default_without_response": "deny_active_storage", "template_body_sections": ["evidence_summary", "requested_mount_scope", "digest_bindings", "lifetime_and_expiration", "revocation_terms", "denial_default", "non_authority_disclaimers"], "no_message_sent": True, "no_ui_rendered": True, "no_external_delivery": True},
        "required_operator_response_fields": {"operator_identity": None, "operator_timestamp": None, "operator_scope_statement": None, "explicit_allow_ledger_write": False, "explicit_allow_glow_archive": False, "consent_expiration": None, "consent_revocation_terms_acknowledged": False, "canonical_vow_digest_acknowledged": False, "storage_policy_digest_acknowledged": False, "transaction_plan_digest_acknowledged": False, "execution_dossier_digest_acknowledged": False, "runtime_authority_digest_acknowledged": False, "finalizer_guard_receipts_acknowledged": False, "no_daemon_self_authorization_acknowledged": False, "no_federation_implied_consent_acknowledged": False, "response_complete": False, "consent_artifact_created": False},
        "consent_scope_statement": {"allowed_mounts": ["/ledger", "/glow"], "ledger_write_requires_explicit_allow": True, "glow_archive_requires_explicit_allow": True, "forbidden_mounts": FORBIDDEN_SCOPE, "daemon_action_not_authorized": True, "model_training_not_authorized": True, "federation_consensus_not_authorized": True},
        "consent_digest_binding_statement": {"digest_algorithm": DIGEST_ALGO, "required_digest_bindings": REQUIRED_DIGEST_BINDINGS, "supplied_digest_bindings": supplied_bindings, "missing_digest_bindings": missing_bindings, "digest_binding_not_acknowledged": True},
        "consent_lifetime_statement": {"expiration_required": True, "expiration_supplied": False, "renewal_required_for_new_vow_digest": True, "renewal_required_for_new_storage_policy": True, "renewal_required_for_new_transaction_plan": True, "renewal_required_for_changed_mount_scope": True, "lifetime_not_started": True},
        "consent_revocation_statement": {"revocation_terms_required": True, "revocation_terms_acknowledged": False, "revocation_must_block_new_writes": True, "revocation_must_block_new_archives": True, "revocation_must_not_delete_existing_receipts": True, "future_revocation_receipt_required": True, "revocation_not_performed": True},
        "consent_denial_statement": {"default_without_response": "deny_active_storage", "missing_response_blocks_ledger_write": True, "missing_response_blocks_glow_archive": True, "incomplete_response_blocks_storage": True, "ambiguous_response_blocks_storage": True, "remote_or_daemon_response_not_accepted": True, "denial_not_runtime_decision_here": True},
        "consent_authority_boundary_statement": {"request_packet_is_not_consent": True, "request_template_is_not_consent": True, "supplied_evidence_does_not_imply_consent": True, "finalizer_ready_to_commit_does_not_imply_consent": True, "pr_metadata_guard_ready_does_not_imply_consent": True, "daemon_recommendation_does_not_imply_consent": True, "federation_state_does_not_imply_consent": True, "future_operator_response_must_be_explicit": True, "authority_boundary_only": True},
        "consent_request_gap_summary": {"consent_request_not_presented": True, "consent_not_collected": True, "consent_not_implied": True, "operator_consent_present": False, "active_storage_allowed_now": False, "runtime_binding_not_performed": True, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "blocking_gap_ids": BLOCKING_GAP_IDS},
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata packet.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "sentientos_mount_alignment": {"/ledger": "future requested consent scope; no ledger write here", "/glow": "future requested consent scope; no archive write here", "/vow": "canonical digest evidence for future consent binding", "/pulse": "future watcher boundary; consent packet does not activate it", "/daemon": "future action boundary; consent packet does not activate it"},
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

def render_codex_workcell_storage_operator_consent_request_packet_markdown(packet: Mapping[str, Any]) -> str:
    sections = ["# Codex Workcell Storage Operator Consent Request Packet", "", "Deterministic metadata-only request packet shape. It is not presented, does not collect or imply consent, and grants no runtime authority."]
    for title, key in [
        ("Input summaries", "input_summaries"), ("Request packet context", "request_packet_context"), ("Evidence digest packet", "evidence_digest_packet"),
        ("Operator request template", "operator_request_template"), ("Required operator response fields", "required_operator_response_fields"),
        ("Consent scope statement", "consent_scope_statement"), ("Consent digest binding statement", "consent_digest_binding_statement"),
        ("Consent lifetime statement", "consent_lifetime_statement"), ("Consent revocation statement", "consent_revocation_statement"),
        ("Consent denial statement", "consent_denial_statement"), ("Consent authority boundary statement", "consent_authority_boundary_statement"),
        ("Consent request gap summary", "consent_request_gap_summary"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"),
        ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Future activation requirements", "future_activation_requirements"),
        ("Non-authority posture", "non_authority_posture"),
    ]:
        value = packet.get(key)
        sections += ["", f"## {title}", _table({str(i): v for i, v in enumerate(value)}) if isinstance(value, list) else _table(value if isinstance(value, Mapping) else {key: value})]
    return "\n".join(sections) + "\n"
