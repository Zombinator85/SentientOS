from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_POLICY_CONTRACT_ID = "codex_workcell_storage_policy_contract.v1"
DIGEST_ALGO = "sha256"

INPUT_IDS: tuple[str, ...] = (
    "vow_boundary_contract_json",
    "vow_alignment_attestation_json",
    "memory_contract_json",
    "memory_activation_preflight_json",
)

LEDGER_RECORD_TYPES: tuple[str, ...] = (
    "codex_landing_receipt", "matrix_receipt", "finalizer_receipt", "pr_metadata_guard_receipt",
    "evidence_index_receipt", "appendix_provenance_receipt", "health_snapshot_receipt",
    "pulse_contract_receipt", "daemon_recommendation_contract_receipt", "memory_contract_receipt",
    "memory_candidate_bundle_receipt", "memory_candidate_verifier_receipt", "memory_activation_preflight_receipt",
    "vow_boundary_contract_receipt", "vow_alignment_attestation_receipt", "storage_policy_contract_receipt",
)

GLOW_ARCHIVE_ITEM_TYPES: tuple[str, ...] = (
    "workcell_architecture_snapshot", "workcell_health_snapshot", "pulse_contract_snapshot",
    "daemon_recommendation_contract_snapshot", "memory_contract_snapshot", "memory_candidate_bundle_snapshot",
    "memory_candidate_verifier_snapshot", "memory_activation_preflight_snapshot", "vow_boundary_contract_snapshot",
    "vow_alignment_attestation_snapshot", "storage_policy_contract_snapshot", "evidence_index_snapshot",
    "evidence_appendix_markdown", "evidence_appendix_sidecar", "doctrine_map_snapshot", "matrix_report_snapshot",
    "finalizer_report_snapshot", "pr_metadata_guard_snapshot",
)

DIGEST_CHECKS: tuple[str, ...] = (
    "source_artifact_digest_required", "raw_byte_sha256_required", "canonical_vow_digest_required",
    "candidate_bundle_digest_required", "candidate_verifier_digest_required", "preflight_digest_required",
    "ledger_entry_digest_required_for_parent_links", "glow_item_digest_required_for_archive_context",
)
PARENT_CHAIN_CHECKS: tuple[str, ...] = (
    "parent_entry_id_required_after_initial_entry", "parent_entry_digest_required_after_initial_entry",
    "overwrite_requires_prior_receipt", "missing_parent_chain_blocks_active_write",
    "parent_digest_mismatch_blocks_active_write", "parent_chain_validation_is_not_readiness_authority",
)
RETENTION_CLASSES: tuple[str, ...] = (
    "landing_receipt_retention", "matrix_receipt_retention", "finalizer_receipt_retention",
    "pr_guard_receipt_retention", "evidence_archive_retention", "doctrine_archive_retention",
    "vow_boundary_retention", "storage_policy_retention",
)
PATH_SCOPE_IDS: tuple[str, ...] = (
    "ledger_mount_scope", "glow_mount_scope", "no_absolute_host_paths", "no_network_paths",
    "no_hidden_backdoor_paths", "no_temp_paths_as_canonical", "digest_lineage_required", "vow_digest_lineage_required",
)
BLOCKING_GAP_IDS: tuple[str, ...] = (
    "active_writer_implementation_missing", "operator_consent_missing", "active_storage_harness_missing",
    "active_write_tests_missing", "finalizer_guard_runtime_binding_missing", "federation_consensus_missing",
)
FUTURE_REQUIREMENTS: tuple[str, ...] = (
    "explicit active ledger writer implementation", "explicit active glow archiver implementation",
    "explicit storage path enforcement", "explicit retention enforcement", "explicit digest verification enforcement",
    "explicit parent-chain validation enforcement", "explicit operator consent", "explicit finalizer/guard runtime binding",
    "explicit pulse watcher contract", "explicit daemon action contract", "explicit federation drift consensus rule",
    "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "storage_policy_contract_is_read_only": True,
    "storage_policy_contract_is_metadata_only": True,
    "storage_policy_contract_is_policy_only": True,
    "storage_policy_contract_does_not_activate_memory": True,
    "storage_policy_contract_does_not_write_ledger": True,
    "storage_policy_contract_does_not_archive_glow": True,
    "storage_policy_contract_does_not_modify_memory": True,
    "storage_policy_contract_does_not_watch_files": True,
    "storage_policy_contract_does_not_poll_state": True,
    "storage_policy_contract_does_not_rerun_commands": True,
    "storage_policy_contract_does_not_decide_readiness": True,
    "storage_policy_contract_does_not_bypass_finalizer": True,
    "storage_policy_contract_does_not_bypass_pr_metadata_guard": True,
    "storage_policy_contract_does_not_authorize_commit": True,
    "storage_policy_contract_does_not_authorize_pr_creation": True,
    "storage_policy_contract_does_not_trigger_daemon": True,
    "storage_policy_contract_does_not_create_tasks": True,
    "storage_policy_contract_does_not_schedule_tasks": True,
    "storage_policy_contract_does_not_send_alerts": True,
    "storage_policy_contract_does_not_train_or_modify_models": True,
    "storage_policy_contract_does_not_establish_federation_consensus": True,
}
FORBIDDEN_INFERENCE = "Do not infer active storage, readiness, memory mutation, daemon action, task creation, model training, finalizer bypass, PR metadata authority, or federation consensus from this policy metadata."

class CodexWorkcellStoragePolicyContractError(ValueError):
    pass

def _omitted() -> dict[str, Any]:
    return {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str | None, input_id: str) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    if path_text is None:
        return _omitted(), None
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStoragePolicyContractError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStoragePolicyContractError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellStoragePolicyContractError(f"json_not_object:{input_id}:{path_text}")
    return {"provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _count_list(data: Mapping[str, Any] | None, key: str) -> int | None:
    value = data.get(key) if data else None
    return len(value) if isinstance(value, list) else None

def _vow_adoption_summary(inputs: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any] | None]]) -> dict[str, Any]:
    vb_sum, vb = inputs["vow_boundary_contract_json"]
    va_sum, va = inputs["vow_alignment_attestation_json"]
    records = va.get("attestation_records") if va else None
    return {
        "vow_boundary_contract": ({"provided": False, "vow_adoption_policy": "future_only_unmet"} if not vb_sum.get("provided") else {
            "provided": True, "vow_boundary_contract_id": vb.get("vow_boundary_contract_id") if vb else None,
            "canonical_vow_digest": vb.get("canonical_vow_digest") if vb else None,
            "canonical_vow_digest_algo": vb.get("canonical_vow_digest_algo") if vb else None,
            "canonical_constraint_count": _count_list(vb, "canonical_vow_constraints"),
            "forbidden_inference_count": _count_list(vb, "forbidden_inference_catalog"),
            "source_digest": vb_sum.get("digest"), "source_digest_algo": vb_sum.get("digest_algo"), "source_byte_size": vb_sum.get("byte_size"),
        }),
        "vow_alignment_attestation": ({"provided": False, "vow_adoption_policy": "future_only_unmet"} if not va_sum.get("provided") else {
            "provided": True, "vow_alignment_attestation_id": va.get("vow_alignment_attestation_id") if va else None,
            "canonical_vow_digest": va.get("canonical_vow_digest") if va else None,
            "attestation_record_count": len(records) if isinstance(records, list) else None,
            "failed_attestation_count": (va.get("attestation_gap_summary", {}) or {}).get("failed_attestation_count") if va else None,
            "warning_attestation_count": (va.get("attestation_gap_summary", {}) or {}).get("warning_attestation_count") if va else None,
            "source_digest": va_sum.get("digest"), "source_digest_algo": va_sum.get("digest_algo"), "source_byte_size": va_sum.get("byte_size"),
        }),
        "policy_status": "future_only_unmet" if not (vb_sum.get("provided") and va_sum.get("provided")) else "vow_bound_inputs_supplied_for_review_only",
        "adoption_not_performed": True,
    }

def _records(ids: tuple[str, ...], id_key: str, **extra: Any) -> list[dict[str, Any]]:
    return [{id_key: item, **extra, "forbidden_inference": FORBIDDEN_INFERENCE, "reviewer_summary": f"{item} is a policy-only requirement for a future active writer; inactive here."} for item in ids]

def build_codex_workcell_storage_policy_contract(inputs: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any] | None]] | None = None) -> dict[str, Any]:
    normalized = {input_id: (dict(inputs[input_id][0]), inputs[input_id][1]) if inputs and input_id in inputs else (_omitted(), None) for input_id in INPUT_IDS}
    return {
        "storage_policy_contract_id": WORKCELL_STORAGE_POLICY_CONTRACT_ID,
        "metadata_only": True, "storage_policy_contract_only": True,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True,
        "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True,
        "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {key: value[0] for key, value in sorted(normalized.items())},
        "vow_adoption_summary": _vow_adoption_summary(normalized),
        "ledger_storage_policy": {"policy_id": "codex_workcell_ledger_storage_policy.v1", "mount": "/ledger", "policy_only": True, "write_not_performed": True, "allowed_record_types": list(LEDGER_RECORD_TYPES), "required_source_digest": True, "required_parent_chain_validation": True, "required_vow_digest": True, "required_finalizer_guard_non_bypass": True, "required_operator_consent": True, "allowed_path_patterns": ["/ledger/codex/workcell/{commit_sha}/{record_type}.json", "/ledger/codex/workcell/{pr_number}/{record_type}.json", "/ledger/codex/workcell/{canonical_vow_digest}/{record_type}.json"], "forbidden_path_patterns": ["absolute host paths outside declared mount", "hidden backdoor paths", "temp paths as canonical ledger storage", "network paths", "provider-specific opaque paths", "paths missing digest or commit/pr lineage"], "forbidden_write_modes": ["append_without_parent_digest", "overwrite_without_prior_receipt", "write_without_vow_digest", "write_without_source_digest", "write_without_finalizer_guard_context", "write_as_readiness_authority"], "reviewer_summary": "Static future /ledger policy only; no ledger write is performed."},
        "glow_storage_policy": {"policy_id": "codex_workcell_glow_storage_policy.v1", "mount": "/glow", "policy_only": True, "archive_not_performed": True, "allowed_archive_item_types": list(GLOW_ARCHIVE_ITEM_TYPES), "required_source_digest": True, "required_related_ledger_entry": True, "required_vow_digest": True, "required_retention_hint": True, "required_operator_consent": True, "allowed_path_patterns": ["/glow/codex/workcell/{commit_sha}/{archive_item_type}.json", "/glow/codex/workcell/{pr_number}/{archive_item_type}.json", "/glow/codex/workcell/{canonical_vow_digest}/{archive_item_type}.json", "/glow/codex/workcell/{commit_sha}/review/{archive_item_type}.md"], "forbidden_path_patterns": ["absolute host paths outside declared mount", "hidden backdoor paths", "temp paths as canonical glow archive", "network paths", "provider-specific opaque paths", "archive paths missing source digest", "archive paths missing vow digest"], "forbidden_archive_modes": ["archive_without_source_digest", "archive_without_related_ledger_context", "archive_without_vow_digest", "archive_without_retention_hint", "archive_as_readiness_authority", "archive_as_model_training_data"], "reviewer_summary": "Static future /glow policy only; no glow archive is performed."},
        "digest_verification_policy": _records(DIGEST_CHECKS, "verification_id", digest_algo=DIGEST_ALGO, required=True, policy_only=True),
        "parent_chain_validation_policy": _records(PARENT_CHAIN_CHECKS, "validation_id", required_for_active_writer=True, policy_only=True),
        "retention_policy": _records(RETENTION_CLASSES, "retention_id", retention_scope="future_codex_workcell_storage", retention_hint="retain until explicit future retention authority defines disposal", policy_only=True, deletion_not_performed=True),
        "path_scope_policy": _records(PATH_SCOPE_IDS, "path_scope_id", applies_to_mounts=["/ledger", "/glow"], allowed=False, policy_only=True),
        "storage_activation_gap_summary": {"vow_boundary_contract_supplied": bool(normalized["vow_boundary_contract_json"][0].get("provided")), "vow_alignment_attestation_supplied": bool(normalized["vow_alignment_attestation_json"][0].get("provided")), "memory_contract_supplied": bool(normalized["memory_contract_json"][0].get("provided")), "activation_preflight_supplied": bool(normalized["memory_activation_preflight_json"][0].get("provided")), "storage_policy_contract_only": True, "active_writer_implementation_present": False, "operator_consent_present": False, "ledger_write_performed": False, "glow_archive_performed": False, "memory_mutation_performed": False, "active_storage_allowed_now": False, "blocking_gap_ids": list(BLOCKING_GAP_IDS)},
        "sentientos_mount_alignment": {"/ledger": "future consumer of ledger storage policy; inactive here", "/glow": "future consumer of glow storage policy; inactive here", "/vow": "canonical digest required for future storage adoption", "/pulse": "future consumer of stored history; inactive here", "/daemon": "future consumer of pulse/recommendation context; inactive here"},
        "future_activation_requirements": [{"requirement": req, "status": "future_only", "met": False, "active": False} for req in FUTURE_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")

def render_codex_workcell_storage_policy_contract_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Storage Policy Contract", "", "Deterministic metadata-only storage policy for future /ledger and /glow writers. It is not a writer, archiver, watcher, scheduler, readiness decision, daemon action, task creator, model trainer, or federation consensus mechanism.", "", "## Input summaries", "| input | provided | path | digest | byte_size |", "| --- | --- | --- | --- | --- |"]
    for key, value in sorted(report["input_summaries"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value.get('provided'))} | {_cell(value.get('path'))} | {_cell(value.get('digest'))} | {_cell(value.get('byte_size'))} |")
    sections = (("Vow adoption summary", "vow_adoption_summary"), ("Ledger storage policy", "ledger_storage_policy"), ("Glow storage policy", "glow_storage_policy"), ("Storage activation gap summary", "storage_activation_gap_summary"))
    for title, key in sections:
        lines += ["", f"## {title}", f"`{_cell(report[key])}`"]
    for title, key, id_key in (("Digest verification policy", "digest_verification_policy", "verification_id"), ("Parent-chain validation policy", "parent_chain_validation_policy", "validation_id"), ("Retention policy", "retention_policy", "retention_id"), ("Path scope policy", "path_scope_policy", "path_scope_id")):
        lines += ["", f"## {title}", f"| {id_key} | summary |", "| --- | --- |"]
        for item in report[key]:
            lines.append(f"| {_cell(item[id_key])} | {_cell(item['reviewer_summary'])} |")
    lines += ["", "## SentientOS mount alignment", "| mount | alignment |", "| --- | --- |"]
    for key, value in sorted(report["sentientos_mount_alignment"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value)} |")
    lines += ["", "## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in report["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"] + [f"- **{key}:** {str(value).lower()}" for key, value in sorted(report["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)

def write_codex_workcell_storage_policy_contract_json(report: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_codex_workcell_storage_policy_contract_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
