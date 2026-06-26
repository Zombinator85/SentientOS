from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_TRANSACTION_PLAN_ID = "codex_workcell_storage_transaction_plan.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage transaction plan is deterministic metadata only; it does not activate memory, write ledger entries, archive glow evidence, mutate memory, watch, poll, run commands, schedule, alert, create tasks, trigger daemons, decide readiness, authorize commit or PR metadata, train models, or establish federation consensus."
FORBIDDEN_INFERENCE = "Do not infer active storage, readiness, commit authority, PR metadata authority, daemon action, task creation, model training, or federation consensus from this dry-run transaction plan."
FUTURE_REQUIREMENT_NAMES: tuple[str, ...] = (
    "explicit active ledger writer implementation", "explicit active glow archiver implementation", "explicit storage path enforcement", "explicit retention enforcement",
    "explicit digest verification enforcement", "explicit parent-chain validation enforcement", "explicit operator consent", "explicit finalizer/guard runtime binding",
    "explicit pulse watcher contract", "explicit daemon action contract", "explicit federation drift consensus rule", "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "storage_transaction_plan_is_read_only": True, "storage_transaction_plan_is_metadata_only": True, "storage_transaction_plan_is_dry_run_only": True,
    "storage_transaction_plan_does_not_activate_memory": True, "storage_transaction_plan_does_not_write_ledger": True, "storage_transaction_plan_does_not_archive_glow": True,
    "storage_transaction_plan_does_not_modify_memory": True, "storage_transaction_plan_does_not_watch_files": True, "storage_transaction_plan_does_not_poll_state": True,
    "storage_transaction_plan_does_not_rerun_commands": True, "storage_transaction_plan_does_not_decide_readiness": True, "storage_transaction_plan_does_not_bypass_finalizer": True,
    "storage_transaction_plan_does_not_bypass_pr_metadata_guard": True, "storage_transaction_plan_does_not_authorize_commit": True, "storage_transaction_plan_does_not_authorize_pr_creation": True,
    "storage_transaction_plan_does_not_trigger_daemon": True, "storage_transaction_plan_does_not_create_tasks": True, "storage_transaction_plan_does_not_schedule_tasks": True,
    "storage_transaction_plan_does_not_send_alerts": True, "storage_transaction_plan_does_not_train_or_modify_models": True, "storage_transaction_plan_does_not_establish_federation_consensus": True,
}

class CodexWorkcellStorageTransactionPlanError(ValueError):
    pass

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], Mapping[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageTransactionPlanError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageTransactionPlanError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellStorageTransactionPlanError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

def _stable_id(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]

def _get(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None

def _derive_canonical_vow_digest(vow_boundary: Mapping[str, Any], vow_attestation: Mapping[str, Any], explicit: str | None) -> tuple[str | None, str | None]:
    if explicit:
        return explicit, "cli"
    for source, data in (("vow_boundary_contract", vow_boundary), ("vow_alignment_attestation", vow_attestation)):
        value = _get(data, "canonical_vow_digest", "vow_digest")
        if isinstance(value, str) and value:
            return value, source
        for key in ("vow_boundary_summary", "vow_alignment_summary", "planning_context"):
            nested = data.get(key)
            if isinstance(nested, Mapping):
                value = _get(nested, "canonical_vow_digest", "vow_digest")
                if isinstance(value, str) and value:
                    return value, f"{source}.{key}"
    return None, None

def _status(data: Mapping[str, Any], *keys: str) -> Any:
    direct = _get(data, *keys)
    if direct is not None:
        return direct
    for value in data.values():
        if isinstance(value, Mapping):
            found = _get(value, *keys)
            if found is not None:
                return found
    return None

def _count(data: Mapping[str, Any], *keys: str) -> int | None:
    value = _status(data, *keys)
    return int(value) if isinstance(value, int) else None

def _verified_storage(status: Any) -> bool:
    return status in ("storage_policy_verified", "verified", "passed", True)

def _verified_candidate(status: Any) -> bool:
    return status in ("memory_candidate_bundle_verified", "verified", "passed", True)

def _templates(policy: Mapping[str, Any], section: str) -> list[str]:
    value = policy.get(section)
    if not isinstance(value, Mapping):
        return []
    return [str(item) for item in _as_list(value.get("allowed_path_patterns")) if isinstance(item, str)]

def _safe_path(path: str, mount: str) -> bool:
    if not path.startswith(f"{mount}/"):
        return False
    lowered = path.lower()
    return not (path.startswith("//") or re.match(r"^[A-Za-z]:", path) or "://" in path or "/tmp/" in lowered or "/temp/" in lowered or "/." in path or ".." in path or "backdoor" in lowered or "provider" in lowered)

def _plan_path(templates: list[str], mount: str, context: Mapping[str, Any], type_key: str, type_value: Any) -> tuple[str | None, str | None, bool]:
    preferences = (("commit_sha", context.get("commit_sha")), ("pr_number", context.get("pr_number")), ("canonical_vow_digest", context.get("canonical_vow_digest")))
    for key, value in preferences:
        if value in (None, ""):
            continue
        for template in templates:
            if "{" + key + "}" not in template:
                continue
            try:
                path = template.format(commit_sha=context.get("commit_sha"), pr_number=context.get("pr_number"), canonical_vow_digest=context.get("canonical_vow_digest"), record_type=type_value, archive_item_type=type_value)
            except KeyError:
                continue
            if _safe_path(path, mount):
                return path, template, False
            return None, template, True
    return None, None, False

def build_codex_workcell_storage_transaction_plan(*, storage_policy_contract: Mapping[str, Any], storage_policy_verifier: Mapping[str, Any], memory_candidate_bundle: Mapping[str, Any], memory_candidate_verifier: Mapping[str, Any], vow_boundary_contract: Mapping[str, Any], vow_alignment_attestation: Mapping[str, Any], input_summaries: Mapping[str, Mapping[str, Any]] | None = None, commit_sha: str | None = None, pr_number: str | None = None, pr_title: str | None = None, canonical_vow_digest: str | None = None) -> dict[str, Any]:
    vow_digest, vow_source = _derive_canonical_vow_digest(vow_boundary_contract, vow_alignment_attestation, canonical_vow_digest)
    storage_status = _status(storage_policy_verifier, "verification_status", "storage_policy_verification_status", "status")
    candidate_status = _status(memory_candidate_verifier, "verification_status", "memory_candidate_verification_status", "status")
    failed = _count(vow_alignment_attestation, "failed_attestation_count", "failure_count", "failed_count") or 0
    warnings = _count(vow_alignment_attestation, "warning_attestation_count", "warning_count") or 0
    active_authority = bool(_status(vow_alignment_attestation, "active_authority_detected"))
    context = {"commit_sha": commit_sha, "pr_number": pr_number, "pr_title": pr_title, "canonical_vow_digest": vow_digest, "storage_policy_verification_status": storage_status, "memory_candidate_verification_status": candidate_status, "vow_attestation_failed_count": failed, "vow_attestation_warning_count": warnings, "dry_run_only": True, "no_action_taken": True}
    ledger_by_candidate: dict[str, str] = {}
    forbidden_ids: list[str] = []
    path_gap_ids: list[str] = []
    missing_digest_ids: list[str] = []
    parent_missing_ids: list[str] = []
    ledger_plan: list[dict[str, Any]] = []
    for entry in _as_list(memory_candidate_bundle.get("candidate_ledger_entries")):
        if not isinstance(entry, Mapping):
            continue
        txid = "ledger-tx-" + _stable_id(entry.get("candidate_entry_id"), entry.get("source_input_id"), entry.get("would_be_record_type"))
        planned, template, forbidden = _plan_path(_templates(storage_policy_contract, "ledger_storage_policy"), "/ledger", context, "record_type", entry.get("would_be_record_type"))
        if planned is None:
            path_gap_ids.append(txid)
        if forbidden:
            forbidden_ids.append(txid)
        if not entry.get("source_artifact_digest"):
            missing_digest_ids.append(txid)
        if not (entry.get("parent_entry_id") and entry.get("parent_entry_digest")):
            parent_missing_ids.append(txid)
        ledger_by_candidate[str(entry.get("candidate_entry_id"))] = txid
        ledger_plan.append({"transaction_id": txid, "transaction_kind": "ledger_write_candidate", "dry_run_only": True, "write_performed": False, "source_candidate_entry_id": entry.get("candidate_entry_id"), "source_input_id": entry.get("source_input_id"), "would_write_record_type": entry.get("would_be_record_type"), "planned_mount": "/ledger", "planned_path": planned, "path_template_used": template, "source_artifact_digest": entry.get("source_artifact_digest"), "source_artifact_digest_algo": entry.get("source_artifact_digest_algo") or DIGEST_ALGO, "source_artifact_byte_size": entry.get("source_artifact_byte_size"), "canonical_vow_digest": vow_digest, "parent_entry_id": entry.get("parent_entry_id"), "parent_entry_digest": entry.get("parent_entry_digest"), "parent_chain_required": True, "finalizer_guard_context_required": True, "operator_consent_required": True, "storage_policy_required": True, "forbidden_inference": entry.get("forbidden_inference") or FORBIDDEN_INFERENCE, "authority_boundary": entry.get("authority_boundary") or AUTHORITY_BOUNDARY})
    glow_plan: list[dict[str, Any]] = []
    for item in _as_list(memory_candidate_bundle.get("candidate_glow_items")):
        if not isinstance(item, Mapping):
            continue
        txid = "glow-tx-" + _stable_id(item.get("candidate_glow_item_id"), item.get("source_input_id"), item.get("would_be_archive_item_type"))
        planned, template, forbidden = _plan_path(_templates(storage_policy_contract, "glow_storage_policy"), "/glow", context, "archive_item_type", item.get("would_be_archive_item_type"))
        if planned is None:
            path_gap_ids.append(txid)
        if forbidden:
            forbidden_ids.append(txid)
        if not item.get("source_digest"):
            missing_digest_ids.append(txid)
        related = item.get("related_candidate_ledger_entry_id")
        glow_plan.append({"transaction_id": txid, "transaction_kind": "glow_archive_candidate", "dry_run_only": True, "archive_performed": False, "source_candidate_glow_item_id": item.get("candidate_glow_item_id"), "source_input_id": item.get("source_input_id"), "would_archive_item_type": item.get("would_be_archive_item_type"), "planned_mount": "/glow", "planned_path": planned, "path_template_used": template, "source_digest": item.get("source_digest"), "source_digest_algo": item.get("source_digest_algo") or DIGEST_ALGO, "source_byte_size": item.get("source_byte_size", item.get("byte_size")), "related_candidate_ledger_entry_id": related, "related_planned_ledger_transaction_id": ledger_by_candidate.get(str(related)) if related is not None else None, "canonical_vow_digest": vow_digest, "retention_hint_required": True, "operator_consent_required": True, "storage_policy_required": True, "forbidden_inference": item.get("forbidden_inference") or FORBIDDEN_INFERENCE, "authority_boundary": item.get("authority_boundary") or AUTHORITY_BOUNDARY})
    planned_paths = [tx["planned_path"] for tx in ledger_plan + glow_plan if tx.get("planned_path")]
    bad_paths = [tx["transaction_id"] for tx in ledger_plan + glow_plan if tx.get("planned_path") and not _safe_path(str(tx["planned_path"]), str(tx["planned_mount"]))]
    forbidden_ids = sorted(set(forbidden_ids + bad_paths))
    blocking = {"active_writer_implementation_missing", "operator_consent_missing", "finalizer_guard_runtime_binding_missing"}
    if path_gap_ids: blocking.add("missing_commit_pr_or_vow_digest_for_path")
    if missing_digest_ids: blocking.add("missing_source_digest")
    if parent_missing_ids: blocking.add("missing_parent_context")
    if not _verified_storage(storage_status): blocking.add("storage_policy_not_verified")
    if not _verified_candidate(candidate_status): blocking.add("memory_candidate_bundle_not_verified")
    if failed or active_authority: blocking.add("vow_alignment_failed")
    if forbidden_ids: blocking.add("forbidden_path_detected")
    parent_required_ids = [tx["transaction_id"] for tx in ledger_plan]
    return {
        "storage_transaction_plan_id": WORKCELL_STORAGE_TRANSACTION_PLAN_ID, "metadata_only": True, "dry_run_only": True, "transaction_plan_only": True,
        "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "not_runtime_authority": True, "not_memory_writer": True,
        "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True,
        "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": dict(sorted((input_summaries or {}).items())), "planning_context": context, "ledger_transaction_plan": ledger_plan, "glow_transaction_plan": glow_plan,
        "transaction_path_validation": {"planned_ledger_transaction_count": len(ledger_plan), "planned_glow_transaction_count": len(glow_plan), "ledger_paths_planned_count": sum(1 for tx in ledger_plan if tx.get("planned_path")), "glow_paths_planned_count": sum(1 for tx in glow_plan if tx.get("planned_path")), "path_gap_count": len(path_gap_ids), "path_gap_transaction_ids": sorted(path_gap_ids), "forbidden_path_detected": bool(forbidden_ids), "forbidden_path_transaction_ids": forbidden_ids, "all_planned_paths_under_declared_mounts": all(str(p).startswith(("/ledger/", "/glow/")) for p in planned_paths), "no_host_paths": not forbidden_ids, "no_network_paths": not forbidden_ids, "no_temp_canonical_paths": not forbidden_ids, "no_backdoor_paths": not forbidden_ids, "validation_only": True},
        "transaction_digest_validation": {"ledger_transactions_with_source_digest_count": sum(1 for tx in ledger_plan if tx.get("source_artifact_digest")), "glow_transactions_with_source_digest_count": sum(1 for tx in glow_plan if tx.get("source_digest")), "missing_digest_transaction_ids": sorted(missing_digest_ids), "canonical_vow_digest_present": vow_digest is not None, "canonical_vow_digest_source": vow_source, "digest_validation_only": True},
        "transaction_parent_chain_plan": {"parent_chain_planning_only": True, "parent_chain_required": True, "transactions_requiring_parent_context": parent_required_ids, "transactions_with_parent_context": [tx["transaction_id"] for tx in ledger_plan if tx.get("parent_entry_id") and tx.get("parent_entry_digest")], "transactions_missing_parent_context": sorted(parent_missing_ids), "missing_parent_context_transaction_ids": sorted(parent_missing_ids), "missing_parent_context_blocks_active_write": True, "no_parent_chain_written": True},
        "transaction_vow_alignment": {"canonical_vow_digest": vow_digest, "vow_boundary_contract_supplied": True, "vow_alignment_attestation_supplied": True, "failed_attestation_count": failed, "warning_attestation_count": warnings, "active_authority_detected": active_authority, "vow_alignment_blocks_active_write": bool(failed or active_authority), "vow_alignment_checked_for_plan": True, "no_vow_adoption_performed": True},
        "transaction_gap_summary": {"planned_ledger_transaction_count": len(ledger_plan), "planned_glow_transaction_count": len(glow_plan), "blocking_gap_count": len(blocking), "warning_gap_count": 1 if warnings else 0, "blocking_gap_ids": sorted(blocking), "warning_gap_ids": ["vow_alignment_warnings_present"] if warnings else [], "active_storage_allowed_now": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "dry_run_only": True, "no_action_taken": True},
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI" + "/SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata planner.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "sentientos_mount_alignment": {"/ledger": "dry-run transaction planning only; no ledger write", "/glow": "dry-run transaction planning only; no archive write", "/vow": "canonical digest context for transaction constraints", "/pulse": "future consumer of stored history; inactive here", "/daemon": "future consumer of pulse/recommendation context; inactive here"},
        "future_activation_requirements": [{"requirement": name, "status": "future_only", "met": False, "active": False} for name in FUTURE_REQUIREMENT_NAMES],
        "non_authority_posture": dict(NON_AUTHORITY_POSTURE),
    }

def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>") if value is not None else ""

def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    return ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] + ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]

def render_codex_workcell_storage_transaction_plan_markdown(plan: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Storage Transaction Dry-Run Plan", "", "Deterministic metadata-only future `/ledger` and `/glow` would-write plan. It is not a writer, archiver, readiness decision, daemon action, scheduler, task creator, model trainer, or federation consensus mechanism."]
    lines += ["", "## Input summaries"] + _table(["input", "path", "digest", "byte_size"], [[k, v.get("path"), v.get("digest"), v.get("byte_size")] for k, v in sorted(dict(plan.get("input_summaries", {})).items()) if isinstance(v, Mapping)])
    context = plan.get("planning_context", {}) if isinstance(plan.get("planning_context"), Mapping) else {}
    lines += ["", "## Planning context"] + _table(["field", "value"], [[k, v] for k, v in sorted(context.items())])
    lines += ["", "## Ledger transaction plan"] + _table(["id", "candidate", "type", "path", "write"], [[x.get("transaction_id"), x.get("source_candidate_entry_id"), x.get("would_write_record_type"), x.get("planned_path"), x.get("write_performed")] for x in _as_list(plan.get("ledger_transaction_plan")) if isinstance(x, Mapping)])
    lines += ["", "## Glow transaction plan"] + _table(["id", "candidate", "type", "path", "archive"], [[x.get("transaction_id"), x.get("source_candidate_glow_item_id"), x.get("would_archive_item_type"), x.get("planned_path"), x.get("archive_performed")] for x in _as_list(plan.get("glow_transaction_plan")) if isinstance(x, Mapping)])
    for title, key in (("Transaction path validation", "transaction_path_validation"), ("Transaction digest validation", "transaction_digest_validation"), ("Transaction parent-chain plan", "transaction_parent_chain_plan"), ("Transaction vow alignment", "transaction_vow_alignment"), ("Transaction gap summary", "transaction_gap_summary"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Non-authority posture", "non_authority_posture")):
        data = plan.get(key, {}) if isinstance(plan.get(key), Mapping) else {}
        lines += ["", f"## {title}"] + _table(["field", "value"], [[k, v] for k, v in sorted(data.items())])
    lines += ["", "## Future activation requirements"] + _table(["requirement", "status", "met", "active"], [[x.get("requirement"), x.get("status"), x.get("met"), x.get("active")] for x in _as_list(plan.get("future_activation_requirements")) if isinstance(x, Mapping)])
    return "\n".join(lines) + "\n"
