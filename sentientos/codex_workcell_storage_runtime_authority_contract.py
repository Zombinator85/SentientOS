from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_RUNTIME_AUTHORITY_CONTRACT_ID = "codex_workcell_storage_runtime_authority_contract.v1"
DIGEST_ALGO = "sha256"

INPUT_SPECS: tuple[str, ...] = (
    "storage_execution_dossier_json",
    "storage_execution_dossier_verifier_json",
    "storage_transaction_plan_json",
    "storage_transaction_plan_verifier_json",
    "storage_policy_contract_json",
    "storage_policy_verifier_json",
    "vow_boundary_contract_json",
    "vow_alignment_attestation_json",
    "memory_activation_preflight_json",
)

BOUNDARY_SPECS: tuple[tuple[str, str, str], ...] = (
    ("finalizer_runtime_binding_required", "finalizer_guard_boundary", "Finalizer ready-to-commit status is not runtime write authority."),
    ("pr_metadata_guard_runtime_binding_required", "finalizer_guard_boundary", "PR metadata guard readiness is not runtime write authority."),
    ("operator_consent_required", "operator_boundary", "Explicit scoped operator consent is required and absent."),
    ("vow_digest_runtime_binding_required", "vow_boundary", "Canonical vow digest must be bound at runtime before active storage."),
    ("storage_policy_runtime_binding_required", "storage_boundary", "Storage policy must be bound by an active implementation before writes."),
    ("transaction_plan_runtime_binding_required", "transaction_boundary", "Transaction plan must be bound by an active implementation before writes."),
    ("transaction_plan_verifier_runtime_binding_required", "transaction_boundary", "Transaction plan verification must be bound before writes."),
    ("storage_execution_dossier_runtime_binding_required", "dossier_boundary", "Execution dossier is review evidence, not runtime authority."),
    ("storage_execution_dossier_verifier_runtime_binding_required", "dossier_boundary", "Dossier verifier is review evidence, not runtime authority."),
    ("ledger_writer_implementation_required", "ledger_glow_boundary", "No active /ledger writer exists here."),
    ("glow_archiver_implementation_required", "ledger_glow_boundary", "No active /glow archiver exists here."),
    ("storage_path_enforcement_required", "storage_boundary", "Runtime path enforcement is future-only and absent."),
    ("retention_enforcement_required", "storage_boundary", "Runtime retention enforcement is future-only and absent."),
    ("digest_verification_runtime_required", "storage_boundary", "Runtime digest verification is future-only and absent."),
    ("parent_chain_runtime_required", "storage_boundary", "Runtime parent-chain validation is future-only and absent."),
    ("pulse_watcher_contract_required", "pulse_daemon_boundary", "Pulse watcher contract is future-only and absent."),
    ("daemon_action_contract_required", "pulse_daemon_boundary", "Daemon action contract is future-only and absent."),
    ("federation_consensus_required", "federation_boundary", "Federation consensus is future-only and absent."),
    ("no_self_authorizing_daemon", "anti_bypass_boundary", "Daemon outputs cannot self-authorize storage."),
    ("no_report_status_as_runtime_authority", "anti_bypass_boundary", "Report statuses cannot become runtime authority."),
    ("no_finalizer_guard_bypass", "anti_bypass_boundary", "Finalizer and PR metadata guard cannot be bypassed."),
    ("no_active_storage_without_all_runtime_bindings", "anti_bypass_boundary", "Active storage remains blocked until every future binding exists."),
)

BLOCKING_GAP_IDS: tuple[str, ...] = (
    "active_writer_implementation_missing", "operator_consent_missing", "finalizer_guard_runtime_binding_missing",
    "storage_path_enforcement_missing", "retention_enforcement_missing", "digest_verification_runtime_missing",
    "parent_chain_runtime_missing", "pulse_watcher_contract_missing", "daemon_action_contract_missing", "federation_consensus_missing",
)
FUTURE_REQUIREMENTS: tuple[str, ...] = (
    "explicit active ledger writer implementation", "explicit active glow archiver implementation", "explicit finalizer runtime binding implementation",
    "explicit PR metadata guard runtime binding implementation", "explicit operator consent capture", "explicit storage path enforcement",
    "explicit retention enforcement", "explicit digest verification enforcement", "explicit parent-chain validation enforcement",
    "explicit pulse watcher contract", "explicit daemon action contract", "explicit federation drift consensus rule",
    "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE = {
    "storage_runtime_authority_contract_is_read_only": True,
    "storage_runtime_authority_contract_is_metadata_only": True,
    "storage_runtime_authority_contract_is_contract_only": True,
    "storage_runtime_authority_contract_does_not_bind_runtime_authority": True,
    "storage_runtime_authority_contract_does_not_activate_memory": True,
    "storage_runtime_authority_contract_does_not_write_ledger": True,
    "storage_runtime_authority_contract_does_not_archive_glow": True,
    "storage_runtime_authority_contract_does_not_modify_memory": True,
    "storage_runtime_authority_contract_does_not_watch_files": True,
    "storage_runtime_authority_contract_does_not_poll_state": True,
    "storage_runtime_authority_contract_does_not_rerun_commands": True,
    "storage_runtime_authority_contract_does_not_decide_readiness": True,
    "storage_runtime_authority_contract_does_not_bypass_finalizer": True,
    "storage_runtime_authority_contract_does_not_bypass_pr_metadata_guard": True,
    "storage_runtime_authority_contract_does_not_authorize_commit": True,
    "storage_runtime_authority_contract_does_not_authorize_pr_creation": True,
    "storage_runtime_authority_contract_does_not_trigger_daemon": True,
    "storage_runtime_authority_contract_does_not_create_tasks": True,
    "storage_runtime_authority_contract_does_not_schedule_tasks": True,
    "storage_runtime_authority_contract_does_not_send_alerts": True,
    "storage_runtime_authority_contract_does_not_train_or_modify_models": True,
    "storage_runtime_authority_contract_does_not_establish_federation_consensus": True,
}

class CodexWorkcellStorageRuntimeAuthorityContractError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageRuntimeAuthorityContractError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageRuntimeAuthorityContractError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageRuntimeAuthorityContractError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _boundary_catalog() -> list[dict[str, Any]]:
    return [{"boundary_id": bid, "category": cat, "required_for_active_storage": True, "currently_bound": False, "future_only": True, "active": False, "forbidden_inference": summary, "reviewer_summary": summary} for bid, cat, summary in BOUNDARY_SPECS]

def build_codex_workcell_storage_runtime_authority_contract(*, input_summaries: Mapping[str, Mapping[str, Any]], commit_sha: str | None = None, pr_number: str | None = None, pr_title: str | None = None) -> dict[str, Any]:
    supplied = sum(1 for input_id in INPUT_SPECS if input_summaries[input_id].get("provided") is True)
    return {
        "storage_runtime_authority_contract_id": WORKCELL_STORAGE_RUNTIME_AUTHORITY_CONTRACT_ID,
        "metadata_only": True, "runtime_authority_contract_only": True, "runtime_binding_not_performed": True,
        "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": dict(input_summaries),
        "runtime_context": {"commit_sha": commit_sha, "pr_number": pr_number, "pr_title": pr_title, "supplied_report_count": supplied, "runtime_authority_contract_only": True, "no_action_taken": True},
        "runtime_authority_boundary_catalog": _boundary_catalog(),
        "finalizer_guard_binding_policy": {"finalizer_runtime_binding_required": True, "pr_metadata_guard_runtime_binding_required": True, "finalizer_ready_to_commit_is_not_runtime_write_authority": True, "pr_metadata_guard_ready_is_not_runtime_write_authority": True, "no_finalizer_guard_bypass": True, "currently_bound": False, "binding_not_performed": True, "policy_only": True, "required_future_evidence": ["finalizer_runtime_binding_implementation", "pr_metadata_guard_runtime_binding_implementation", "negative_tests_for_no_write_authority"]},
        "operator_consent_policy": {"operator_consent_required": True, "operator_consent_present": False, "consent_not_collected": True, "consent_must_be_explicit": True, "consent_must_be_scoped_to_mounts": ["/ledger", "/glow"], "consent_must_reference_vow_digest": True, "consent_must_reference_storage_policy": True, "consent_must_reference_transaction_plan": True, "policy_only": True},
        "storage_enforcement_policy": {"storage_path_enforcement_required": True, "retention_enforcement_required": True, "active_ledger_writer_required": True, "active_glow_archiver_required": True, "active_ledger_writer_present": False, "active_glow_archiver_present": False, "enforcement_not_performed": True, "policy_only": True, "forbidden_runtime_write_modes": ["write_without_operator_consent", "write_without_finalizer_guard_runtime_binding", "write_without_vow_digest", "write_without_storage_policy", "write_without_transaction_plan", "write_without_transaction_plan_verification", "write_without_digest_verification", "write_without_parent_chain_validation", "archive_without_related_ledger_context", "archive_as_model_training_data", "report_status_as_runtime_authority"]},
        "digest_and_parent_runtime_policy": {"digest_verification_runtime_required": True, "parent_chain_runtime_required": True, "digest_verification_runtime_present": False, "parent_chain_runtime_present": False, "runtime_verification_not_performed": True, "policy_only": True, "required_digest_bindings": ["source_artifact_digest", "canonical_vow_digest", "storage_policy_digest", "transaction_plan_digest", "transaction_plan_verifier_digest", "dossier_digest", "dossier_verifier_digest"], "required_parent_chain_bindings": ["prior_ledger_entry_id", "prior_ledger_entry_digest", "overwrite_receipt_context", "missing_parent_blocks_write", "parent_digest_mismatch_blocks_write"]},
        "pulse_daemon_runtime_boundary": {"pulse_watcher_contract_required": True, "daemon_action_contract_required": True, "pulse_watcher_contract_present": False, "daemon_action_contract_present": False, "daemon_self_authorization_forbidden": True, "pulse_signals_are_not_actions": True, "daemon_recommendations_are_not_commands": True, "boundary_only": True},
        "federation_runtime_boundary": {"federation_consensus_required": True, "federation_consensus_present": False, "federation_consensus_not_established": True, "local_storage_authority_not_implied_by_remote_state": True, "remote_consensus_not_implied": True, "boundary_only": True},
        "runtime_activation_gap_summary": {"active_storage_allowed_now": False, "runtime_binding_not_performed": True, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "active_writer_implementation_present": False, "operator_consent_present": False, "finalizer_guard_runtime_binding_present": False, "storage_path_enforcement_present": False, "retention_enforcement_present": False, "digest_verification_runtime_present": False, "parent_chain_runtime_present": False, "pulse_watcher_contract_present": False, "daemon_action_contract_present": False, "federation_consensus_present": False, "blocking_gap_ids": list(BLOCKING_GAP_IDS)},
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata contract.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "sentientos_mount_alignment": {"/ledger": "future runtime storage target; no ledger write here", "/glow": "future runtime archive target; no archive write here", "/vow": "canonical digest context required for runtime authority boundaries", "/pulse": "future watcher boundary; inactive here", "/daemon": "future action boundary; inactive here"},
        "future_activation_requirements": [{"requirement": req, "status": "future_only", "met": False, "active": False} for req in FUTURE_REQUIREMENTS],
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")

def _table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out.extend("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows)
    return "\n".join(out) + "\n"

def render_codex_workcell_storage_runtime_authority_contract_markdown(report: Mapping[str, Any]) -> str:
    parts = ["# Codex Workcell Storage Runtime Authority Boundary Contract\n", "This deterministic metadata-only contract defines future runtime authority bindings for active `/ledger` and `/glow` storage; it performs no binding, readiness decision, write, archive, memory mutation, daemon action, task creation, scheduling, command execution, or federation consensus.\n"]
    parts.append("## Input summaries\n" + _table(["input", "provided", "path", "digest", "bytes"], [[k, v.get("provided"), v.get("path"), v.get("digest"), v.get("byte_size")] for k, v in sorted(report["input_summaries"].items())]))
    parts.append("## Runtime context\n" + _table(["key", "value"], [[k, v] for k, v in report["runtime_context"].items()]))
    parts.append("## Runtime authority boundary catalog\n" + _table(["id", "category", "future_only", "currently_bound", "active", "summary"], [[b["boundary_id"], b["category"], b["future_only"], b["currently_bound"], b["active"], b["reviewer_summary"]] for b in report["runtime_authority_boundary_catalog"]]))
    for title, key in (("Finalizer/guard binding policy", "finalizer_guard_binding_policy"), ("Operator consent policy", "operator_consent_policy"), ("Storage enforcement policy", "storage_enforcement_policy"), ("Digest and parent runtime policy", "digest_and_parent_runtime_policy"), ("Pulse/daemon runtime boundary", "pulse_daemon_runtime_boundary"), ("Federation runtime boundary", "federation_runtime_boundary"), ("Runtime activation gap summary", "runtime_activation_gap_summary"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Non-authority posture", "non_authority_posture")):
        parts.append(f"## {title}\n" + _table(["key", "value"], [[k, v] for k, v in report[key].items()]))
    parts.append("## Future activation requirements\n" + _table(["requirement", "status", "met", "active"], [[r["requirement"], r["status"], r["met"], r["active"]] for r in report["future_activation_requirements"]]))
    return "\n".join(parts)
