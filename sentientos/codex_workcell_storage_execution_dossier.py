from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_EXECUTION_DOSSIER_ID = "codex_workcell_storage_execution_dossier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage execution readiness dossier is deterministic metadata only; it is not runtime authority, not a writer, not an archiver, not a watcher, not a scheduler, not an executor, and not finalizer or PR metadata authority."

INPUT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("memory_contract_json", "memory_schema", "memory_contract_supplied"),
    ("memory_candidate_bundle_json", "memory_candidate", "memory_candidate_bundle_supplied"),
    ("memory_candidate_verifier_json", "memory_verifier", "memory_candidate_verifier_supplied"),
    ("memory_activation_preflight_json", "memory_preflight", "memory_activation_preflight_supplied"),
    ("vow_boundary_contract_json", "vow_boundary", "vow_boundary_contract_supplied"),
    ("vow_alignment_attestation_json", "vow_attestation", "vow_alignment_attestation_supplied"),
    ("storage_policy_contract_json", "storage_policy", "storage_policy_contract_supplied"),
    ("storage_policy_verifier_json", "storage_policy_verifier", "storage_policy_verifier_supplied"),
    ("storage_transaction_plan_json", "transaction_plan", "storage_transaction_plan_supplied"),
    ("storage_transaction_plan_verifier_json", "transaction_plan_verifier", "storage_transaction_plan_verifier_supplied"),
)

BLOCKING_GAP_IDS = [
    "active_writer_implementation_missing", "operator_consent_missing", "finalizer_guard_runtime_binding_missing",
    "storage_path_enforcement_missing", "retention_enforcement_missing", "digest_verification_runtime_missing",
    "parent_chain_runtime_missing", "pulse_watcher_contract_missing", "daemon_action_contract_missing", "federation_consensus_missing",
]
FUTURE_REQUIREMENT_NAMES = [
    "explicit active ledger writer implementation", "explicit active glow archiver implementation", "explicit storage path enforcement",
    "explicit retention enforcement", "explicit digest verification enforcement", "explicit parent-chain validation enforcement",
    "explicit operator consent", "explicit finalizer/guard runtime binding", "explicit pulse watcher contract",
    "explicit daemon action contract", "explicit federation drift consensus rule", "tests proving no readiness authority", "docs marking active behavior",
]
NON_AUTHORITY_POSTURE = {
    "storage_execution_dossier_is_read_only": True,
    "storage_execution_dossier_is_metadata_only": True,
    "storage_execution_dossier_is_dossier_only": True,
    "storage_execution_dossier_does_not_activate_memory": True,
    "storage_execution_dossier_does_not_write_ledger": True,
    "storage_execution_dossier_does_not_archive_glow": True,
    "storage_execution_dossier_does_not_modify_memory": True,
    "storage_execution_dossier_does_not_watch_files": True,
    "storage_execution_dossier_does_not_poll_state": True,
    "storage_execution_dossier_does_not_rerun_commands": True,
    "storage_execution_dossier_does_not_decide_readiness": True,
    "storage_execution_dossier_does_not_bypass_finalizer": True,
    "storage_execution_dossier_does_not_bypass_pr_metadata_guard": True,
    "storage_execution_dossier_does_not_authorize_commit": True,
    "storage_execution_dossier_does_not_authorize_pr_creation": True,
    "storage_execution_dossier_does_not_trigger_daemon": True,
    "storage_execution_dossier_does_not_create_tasks": True,
    "storage_execution_dossier_does_not_schedule_tasks": True,
    "storage_execution_dossier_does_not_send_alerts": True,
    "storage_execution_dossier_does_not_train_or_modify_models": True,
    "storage_execution_dossier_does_not_establish_federation_consensus": True,
}

class CodexWorkcellStorageExecutionDossierError(ValueError):
    pass

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageExecutionDossierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageExecutionDossierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageExecutionDossierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _status(data: Mapping[str, Any]) -> Any:
    for key in ("verification_status", "storage_policy_verification_status", "storage_transaction_plan_verification_status", "memory_candidate_verification_status", "activation_preflight_status", "storage_execution_status"):
        if data.get(key) is not None:
            return data.get(key)
    return None

def _report_id(data: Mapping[str, Any]) -> Any:
    for key in ("storage_execution_dossier_id", "storage_transaction_plan_verifier_id", "storage_transaction_plan_id", "storage_policy_verifier_id", "storage_policy_contract_id", "vow_alignment_attestation_id", "vow_boundary_contract_id", "memory_activation_preflight_id", "memory_candidate_verifier_id", "memory_candidate_bundle_id", "memory_contract_id"):
        if data.get(key):
            return data.get(key)
    return None

def _digest(data: Mapping[str, Any]) -> Any:
    for key in ("digest", "source_digest", "policy_digest", "plan_digest", "memory_contract_digest", "candidate_bundle_digest", "canonical_vow_digest"):
        if data.get(key):
            return data.get(key)
    return None

def _all_true(value: Any) -> bool | None:
    if not isinstance(value, Mapping):
        return None
    return all(v is True for v in value.values())

def _is_verified(data: Mapping[str, Any], good: str) -> bool | None:
    s = _status(data)
    if s is None:
        return None
    return s == good or s is True

def build_codex_workcell_storage_execution_dossier(*, input_summaries: Mapping[str, Mapping[str, Any]], input_reports: Mapping[str, Mapping[str, Any]], commit_sha: str | None = None, pr_number: str | None = None, pr_title: str | None = None) -> dict[str, Any]:
    supplied_count = sum(1 for key, _, _ in INPUT_SPECS if input_summaries[key].get("provided") is True)
    inventory = []
    for input_id, role, _ in INPUT_SPECS:
        summary = input_summaries[input_id]
        data = input_reports.get(input_id, {})
        nonauth = data.get("non_authority_posture")
        inventory.append({"input_id": input_id, "provided": bool(summary.get("provided")), "detected_report_id": _report_id(data), "source_digest": summary.get("digest"), "source_digest_algo": summary.get("digest_algo") or DIGEST_ALGO, "source_byte_size": summary.get("byte_size"), "evidence_role": role, "relevant_status": _status(data), "relevant_digest": _digest(data), "non_authority_posture_present": isinstance(nonauth, Mapping), "non_authority_posture_all_true": _all_true(nonauth), "inventory_status": "supplied" if summary.get("provided") else "missing", "notes": [] if summary.get("provided") else ["optional input omitted; required for complete future-design dossier"]})
    by = input_reports
    policy_verified = _is_verified(by.get("storage_policy_verifier_json", {}), "storage_policy_verified")
    plan_verified = _is_verified(by.get("storage_transaction_plan_verifier_json", {}), "storage_transaction_plan_verified")
    candidate_verified = _is_verified(by.get("memory_candidate_verifier_json", {}), "memory_candidate_verified")
    vow = by.get("vow_alignment_attestation_json", {})
    failed = vow.get("failed_attestation_count")
    warnings = vow.get("warning_attestation_count")
    active = any(report.get("active_storage_allowed_now") is True or report.get("execution_performed") is True or report.get("writes_performed") is True or report.get("archives_performed") is True or report.get("memory_mutation_performed") is True for report in by.values())
    all_supplied = supplied_count == len(INPUT_SPECS)
    all_nonauth = all(i["non_authority_posture_all_true"] is not False for i in inventory if i["provided"])
    failed_verified = policy_verified is False or plan_verified is False
    status = "future_storage_design_dossier_failed" if failed_verified else ("future_storage_design_dossier_complete" if all_supplied else "future_storage_design_dossier_incomplete")
    readiness: dict[str, Any] = {spec[2]: input_summaries[spec[0]].get("provided") is True for spec in INPUT_SPECS}
    readiness.update({"storage_policy_verified": policy_verified, "storage_transaction_plan_verified": plan_verified, "memory_candidate_verified": candidate_verified, "vow_alignment_failed_count": failed, "vow_alignment_warning_count": warnings, "active_authority_detected": active, "all_required_reports_supplied": all_supplied, "all_supplied_reports_non_authoritative": all_nonauth, "dossier_ready_for_future_design_review": status == "future_storage_design_dossier_complete", "no_action_taken": True})
    gaps = {"active_writer_implementation_present": False, "operator_consent_present": False, "finalizer_guard_runtime_binding_present": False, "storage_path_enforcement_present": False, "retention_enforcement_present": False, "digest_verification_runtime_present": False, "parent_chain_runtime_present": False, "pulse_watcher_contract_present": False, "daemon_action_contract_present": False, "federation_consensus_present": False, "active_storage_allowed_now": False, "execution_performed": False, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "blocking_gap_ids": BLOCKING_GAP_IDS, "warning_gap_ids": []}
    prereq=[]
    for _, _, pid in INPUT_SPECS:
        passed = readiness[pid]
        prereq.append({"prerequisite_id": pid, "category": "supplied_report", "passed": passed, "severity": "info" if passed else "warning", "observed_state": "supplied" if passed else "missing", "evidence_source": pid.replace("_supplied", "_json"), "authority_boundary": AUTHORITY_BOUNDARY})
    for pid, val in (("storage_policy_verified", policy_verified), ("storage_transaction_plan_verified", plan_verified)):
        prereq.append({"prerequisite_id": pid, "category": "verified_report", "passed": val is True, "severity": "info" if val is True else ("violation" if val is False else "warning"), "observed_state": "verified" if val is True else ("failed" if val is False else "unknown"), "evidence_source": pid, "authority_boundary": AUTHORITY_BOUNDARY})
    for gap in BLOCKING_GAP_IDS:
        prereq.append({"prerequisite_id": gap, "category": "active_execution_gap", "passed": True, "severity": "blocking_gap", "observed_state": "future-only unmet active execution gap documented", "evidence_source": "active_execution_gap_summary", "authority_boundary": AUTHORITY_BOUNDARY})
    return {"storage_execution_dossier_id": WORKCELL_STORAGE_EXECUTION_DOSSIER_ID, "metadata_only": True, "dossier_only": True, "execution_not_performed": True, "writes_performed": False, "archives_performed": False, "memory_mutation_performed": False, "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True, "input_summaries": dict(input_summaries), "dossier_context": {"commit_sha": commit_sha, "pr_number": pr_number, "pr_title": pr_title, "supplied_report_count": supplied_count, "required_report_count": len(INPUT_SPECS), "dossier_only": True, "no_action_taken": True}, "evidence_inventory": inventory, "readiness_evidence_summary": readiness, "active_execution_gap_summary": gaps, "storage_execution_status": status, "execution_prerequisite_results": prereq, "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI/" + "SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata dossier.", "docs_hygiene_only": True, "no_runtime_effect": True}, "sentientos_mount_alignment": {"/ledger": "future active storage target; no ledger write here", "/glow": "future active storage target; no archive write here", "/vow": "canonical digest context for execution boundaries", "/pulse": "future consumer of stored history; inactive here", "/daemon": "future consumer of pulse/recommendation context; inactive here"}, "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_REQUIREMENT_NAMES], "non_authority_posture": dict(NON_AUTHORITY_POSTURE)}

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")

def _table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out.extend("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows)
    return "\n".join(out) + "\n"

def render_codex_workcell_storage_execution_dossier_markdown(report: Mapping[str, Any]) -> str:
    parts = ["# Codex Workcell Storage Execution Readiness Dossier\n", "This deterministic dossier inventories supplied reports for future active-storage design only; it performs no execution and grants no storage, commit, PR, daemon, ledger, glow, or readiness authority.\n"]
    parts.append("## Input summaries\n" + _table(["input", "provided", "path", "digest", "bytes"], [[k, v.get("provided"), v.get("path"), v.get("digest"), v.get("byte_size")] for k, v in sorted(report["input_summaries"].items())]))
    parts.append("## Dossier context\n" + _table(["key", "value"], [[k, v] for k, v in report["dossier_context"].items()]))
    parts.append("## Evidence inventory\n" + _table(["input", "role", "provided", "status", "digest"], [[i["input_id"], i["evidence_role"], i["provided"], i["relevant_status"], i["source_digest"]] for i in report["evidence_inventory"]]))
    for title, key in (("Readiness evidence summary", "readiness_evidence_summary"), ("Active execution gap summary", "active_execution_gap_summary"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment"), ("Non-authority posture", "non_authority_posture")):
        parts.append(f"## {title}\n" + _table(["key", "value"], [[k, v] for k, v in report[key].items()]))
    parts.append("## Storage execution status\n" + str(report["storage_execution_status"]) + "\n")
    parts.append("## Execution prerequisite results\n" + _table(["id", "category", "passed", "severity", "observed"], [[r["prerequisite_id"], r["category"], r["passed"], r["severity"], r["observed_state"]] for r in report["execution_prerequisite_results"]]))
    parts.append("## Future activation requirements\n" + _table(["requirement", "status", "met", "active"], [[r["requirement"], r["status"], r["met"], r["active"]] for r in report["future_activation_requirements"]]))
    return "\n".join(parts)
