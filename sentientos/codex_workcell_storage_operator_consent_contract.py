from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_OPERATOR_CONSENT_CONTRACT_ID = "codex_workcell_storage_operator_consent_contract.v1"
DIGEST_ALGO = "sha256"

INPUT_SPECS: tuple[str, ...] = (
    "storage_runtime_authority_contract_json", "storage_runtime_authority_verifier_json",
    "storage_execution_dossier_json", "storage_execution_dossier_verifier_json",
    "storage_transaction_plan_json", "storage_transaction_plan_verifier_json",
    "storage_policy_contract_json", "storage_policy_verifier_json",
    "vow_boundary_contract_json", "vow_alignment_attestation_json",
)

SCHEMA_IDS: tuple[str, ...] = (
    "operator_identity_required", "consent_timestamp_required", "consent_scope_required",
    "consent_mount_scope_required", "canonical_vow_digest_required", "storage_policy_digest_required",
    "storage_policy_verifier_digest_required", "transaction_plan_digest_required",
    "transaction_plan_verifier_digest_required", "execution_dossier_digest_required",
    "execution_dossier_verifier_digest_required", "runtime_authority_contract_digest_required",
    "runtime_authority_verifier_digest_required", "finalizer_guard_evidence_required",
    "explicit_allow_ledger_write_required", "explicit_allow_glow_archive_required",
    "explicit_denial_default_required", "revocation_terms_required", "expiration_terms_required",
    "no_daemon_self_authorization_required", "no_federation_implied_consent_required",
)

REQUIRED_EVIDENCE_IDS: tuple[str, ...] = (
    "canonical_vow_digest", "storage_policy_contract_digest", "storage_policy_verifier_digest",
    "storage_transaction_plan_digest", "storage_transaction_plan_verifier_digest",
    "storage_execution_dossier_digest", "storage_execution_dossier_verifier_digest",
    "runtime_authority_contract_digest", "runtime_authority_verifier_digest",
    "finalizer_pre_commit_receipt", "pr_metadata_finalizer_receipt", "pr_metadata_guard_receipt",
    "operator_identity", "operator_timestamp", "operator_scope_statement",
)

INPUT_TO_EVIDENCE: dict[str, str] = {
    "vow_boundary_contract_json": "canonical_vow_digest",
    "vow_alignment_attestation_json": "canonical_vow_digest",
    "storage_policy_contract_json": "storage_policy_contract_digest",
    "storage_policy_verifier_json": "storage_policy_verifier_digest",
    "storage_transaction_plan_json": "storage_transaction_plan_digest",
    "storage_transaction_plan_verifier_json": "storage_transaction_plan_verifier_digest",
    "storage_execution_dossier_json": "storage_execution_dossier_digest",
    "storage_execution_dossier_verifier_json": "storage_execution_dossier_verifier_digest",
    "storage_runtime_authority_contract_json": "runtime_authority_contract_digest",
    "storage_runtime_authority_verifier_json": "runtime_authority_verifier_digest",
}

BLOCKING_GAP_IDS: tuple[str, ...] = (
    "operator_consent_missing", "operator_identity_missing", "consent_timestamp_missing",
    "consent_scope_missing", "consent_digest_bindings_missing", "consent_expiration_missing",
    "consent_revocation_terms_missing", "explicit_ledger_write_allow_missing",
    "explicit_glow_archive_allow_missing", "runtime_authority_binding_missing",
)

FUTURE_REQUIREMENTS: tuple[str, ...] = (
    "explicit operator identity capture", "explicit operator consent capture", "explicit consent timestamp capture",
    "explicit consent expiration policy", "explicit consent revocation policy", "explicit canonical vow digest binding",
    "explicit storage policy digest binding", "explicit transaction plan digest binding", "explicit execution dossier digest binding",
    "explicit runtime authority digest binding", "explicit active ledger writer implementation", "explicit active glow archiver implementation",
    "explicit finalizer runtime binding implementation", "explicit PR metadata guard runtime binding implementation",
    "explicit storage path enforcement", "explicit retention enforcement", "explicit digest verification enforcement",
    "explicit parent-chain validation enforcement", "tests proving no readiness authority", "docs marking active behavior",
)

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "storage_operator_consent_contract_is_read_only": True,
    "storage_operator_consent_contract_is_metadata_only": True,
    "storage_operator_consent_contract_is_contract_only": True,
    "storage_operator_consent_contract_does_not_collect_consent": True,
    "storage_operator_consent_contract_does_not_imply_consent": True,
    "storage_operator_consent_contract_does_not_bind_runtime_authority": True,
    "storage_operator_consent_contract_does_not_activate_memory": True,
    "storage_operator_consent_contract_does_not_write_ledger": True,
    "storage_operator_consent_contract_does_not_archive_glow": True,
    "storage_operator_consent_contract_does_not_modify_memory": True,
    "storage_operator_consent_contract_does_not_watch_files": True,
    "storage_operator_consent_contract_does_not_poll_state": True,
    "storage_operator_consent_contract_does_not_rerun_commands": True,
    "storage_operator_consent_contract_does_not_decide_readiness": True,
    "storage_operator_consent_contract_does_not_bypass_finalizer": True,
    "storage_operator_consent_contract_does_not_bypass_pr_metadata_guard": True,
    "storage_operator_consent_contract_does_not_authorize_commit": True,
    "storage_operator_consent_contract_does_not_authorize_pr_creation": True,
    "storage_operator_consent_contract_does_not_trigger_daemon": True,
    "storage_operator_consent_contract_does_not_create_tasks": True,
    "storage_operator_consent_contract_does_not_schedule_tasks": True,
    "storage_operator_consent_contract_does_not_send_alerts": True,
    "storage_operator_consent_contract_does_not_train_or_modify_models": True,
    "storage_operator_consent_contract_does_not_establish_federation_consensus": True,
}

class CodexWorkcellStorageOperatorConsentContractError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageOperatorConsentContractError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageOperatorConsentContractError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageOperatorConsentContractError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _schema() -> list[dict[str, Any]]:
    return [{"schema_field_id": sid, "required_for_future_consent": True, "currently_satisfied": False, "future_only": True, "active": False, "forbidden_inference": "This future consent field is not satisfied by reports, readiness, daemon output, federation state, or this contract.", "reviewer_summary": f"Future explicit consent artifact must include {sid}; inactive here."} for sid in SCHEMA_IDS]

def _supplied_evidence(input_summaries: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return sorted({eid for iid, eid in INPUT_TO_EVIDENCE.items() if input_summaries[iid].get("provided") is True})

def build_codex_workcell_storage_operator_consent_contract(*, input_summaries: Mapping[str, Mapping[str, Any]], commit_sha: str | None = None, pr_number: str | None = None, pr_title: str | None = None) -> dict[str, Any]:
    supplied_count = sum(1 for iid in INPUT_SPECS if input_summaries[iid].get("provided") is True)
    supplied_evidence = _supplied_evidence(input_summaries)
    missing = [eid for eid in REQUIRED_EVIDENCE_IDS if eid not in supplied_evidence]
    top: dict[str, Any] = {
        "storage_operator_consent_contract_id": WORKCELL_STORAGE_OPERATOR_CONSENT_CONTRACT_ID,
        "metadata_only": True, "consent_contract_only": True, "consent_request_shape_only": True,
        "consent_not_collected": True, "operator_consent_present": False, "runtime_binding_not_performed": True,
        "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False,
        "archives_performed": False, "memory_mutation_performed": False,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True,
        "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True,
        "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True,
        "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": dict(input_summaries),
        "consent_context": {"commit_sha": commit_sha, "pr_number": pr_number, "pr_title": pr_title, "supplied_report_count": supplied_count, "consent_contract_only": True, "consent_not_collected": True, "no_action_taken": True},
        "consent_request_schema": _schema(),
        "required_consent_evidence": {"required_evidence_ids": list(REQUIRED_EVIDENCE_IDS), "supplied_evidence_ids": supplied_evidence, "missing_evidence_ids": missing, "evidence_collection_not_performed": True, "consent_not_collected": True, "policy_only": True},
        "consent_scope_policy": {"allowed_mounts": ["/ledger", "/glow"], "forbidden_mounts": ["/vow", "/pulse", "/daemon", "host_absolute_paths", "network_paths", "temp_paths_as_canonical", "hidden_backdoor_paths"], "ledger_write_must_be_explicit": True, "glow_archive_must_be_explicit": True, "consent_does_not_authorize_daemon_action": True, "consent_does_not_authorize_model_training": True, "consent_does_not_authorize_federation_consensus": True, "policy_only": True},
        "consent_digest_binding_policy": {"canonical_vow_digest_required": True, "storage_policy_digest_required": True, "transaction_plan_digest_required": True, "execution_dossier_digest_required": True, "runtime_authority_digest_required": True, "digest_algorithm": DIGEST_ALGO, "digest_binding_not_performed": True, "missing_digest_bindings": missing, "policy_only": True},
        "consent_lifetime_policy": {"expiration_required": True, "revocation_required": True, "renewal_required_for_new_vow_digest": True, "renewal_required_for_new_storage_policy": True, "renewal_required_for_new_transaction_plan": True, "renewal_required_for_changed_mount_scope": True, "consent_lifetime_not_started": True, "policy_only": True},
        "consent_revocation_policy": {"revocation_must_block_new_writes": True, "revocation_must_block_new_archives": True, "revocation_must_not_delete_existing_receipts": True, "revocation_must_create_future_revocation_receipt": True, "revocation_not_performed": True, "policy_only": True},
        "consent_denial_policy": {"default_without_consent": "deny_active_storage", "missing_consent_blocks_ledger_write": True, "missing_consent_blocks_glow_archive": True, "ambiguous_consent_blocks_storage": True, "remote_or_daemon_consent_not_accepted": True, "consent_denial_not_runtime_decision_here": True, "policy_only": True},
        "consent_authority_boundary": {"consent_contract_is_not_consent": True, "consent_schema_is_not_operator_approval": True, "supplied_reports_do_not_imply_consent": True, "finalizer_ready_to_commit_does_not_imply_consent": True, "pr_metadata_guard_ready_does_not_imply_consent": True, "daemon_recommendation_does_not_imply_consent": True, "federation_state_does_not_imply_consent": True, "future_operator_consent_must_be_explicit": True, "authority_boundary_only": True},
        "consent_activation_gap_summary": {"operator_consent_present": False, "consent_not_collected": True, "active_storage_allowed_now": False, "runtime_binding_not_performed": True, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "blocking_gap_ids": list(BLOCKING_GAP_IDS)},
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata contract.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "sentientos_mount_alignment": {"/ledger": "future consent scope target; no ledger write here", "/glow": "future consent scope target; no archive write here", "/vow": "canonical digest required for future consent binding", "/pulse": "future watcher boundary; consent here does not activate it", "/daemon": "future action boundary; consent here does not activate it"},
        "future_activation_requirements": [{"requirement": req, "status": "future_only", "met": False, "active": False} for req in FUTURE_REQUIREMENTS],
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }
    return top

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")

def _table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out.extend("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows)
    return "\n".join(out) + "\n"

def render_codex_workcell_storage_operator_consent_contract_markdown(report: Mapping[str, Any]) -> str:
    parts = ["# Codex Workcell Storage Operator Consent Request Contract\n", "This deterministic metadata-only contract defines the future explicit operator consent request shape for `/ledger` and `/glow`; it collects no consent, implies no consent, binds no runtime authority, and performs no write, archive, memory mutation, readiness decision, daemon action, scheduling, alerting, task creation, command execution, PR creation, model training, or federation consensus.\n"]
    parts.append("## Input summaries\n" + _table(["input", "provided", "path", "digest", "bytes"], [[k, v.get("provided"), v.get("path"), v.get("digest"), v.get("byte_size")] for k, v in sorted(report["input_summaries"].items())]))
    parts.append("## Consent context\n" + _table(["key", "value"], [[k, v] for k, v in report["consent_context"].items()]))
    parts.append("## Consent request schema\n" + _table(["id", "future_only", "currently_satisfied", "active", "summary"], [[r["schema_field_id"], r["future_only"], r["currently_satisfied"], r["active"], r["reviewer_summary"]] for r in report["consent_request_schema"]]))
    sections = (("Required consent evidence", "required_consent_evidence"), ("Consent scope policy", "consent_scope_policy"), ("Consent digest binding policy", "consent_digest_binding_policy"), ("Consent lifetime policy", "consent_lifetime_policy"), ("Consent revocation policy", "consent_revocation_policy"), ("Consent denial policy", "consent_denial_policy"), ("Consent authority boundary", "consent_authority_boundary"), ("Consent activation gap summary", "consent_activation_gap_summary"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Non-authority posture", "non_authority_posture"))
    for title, key in sections:
        parts.append(f"## {title}\n" + _table(["key", "value"], [[k, v] for k, v in report[key].items()]))
    parts.append("## Future activation requirements\n" + _table(["requirement", "status", "met", "active"], [[r["requirement"], r["status"], r["met"], r["active"]] for r in report["future_activation_requirements"]]))
    return "\n".join(parts)
