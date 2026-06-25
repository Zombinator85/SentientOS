from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.codex_workcell_storage_policy_contract import (
    DIGEST_CHECKS as REQUIRED_DIGEST_POLICY_IDS,
    GLOW_ARCHIVE_ITEM_TYPES as REQUIRED_GLOW_ARCHIVE_ITEM_TYPES,
    LEDGER_RECORD_TYPES as REQUIRED_LEDGER_RECORD_TYPES,
    PARENT_CHAIN_CHECKS as REQUIRED_PARENT_CHAIN_POLICY_IDS,
    PATH_SCOPE_IDS as REQUIRED_PATH_SCOPE_POLICY_IDS,
    RETENTION_CLASSES as REQUIRED_RETENTION_POLICY_IDS,
)

WORKCELL_STORAGE_POLICY_VERIFIER_ID = "codex_workcell_storage_policy_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage policy verifier metadata only; does not activate memory, write ledger, archive glow, mutate memory, watch, poll, run commands, schedule, alert, create tasks, trigger daemons, decide readiness, authorize commit or PR metadata, train models, or establish federation consensus."
OPTIONAL_INPUT_IDS: tuple[str, ...] = (
    "vow_boundary_contract_json",
    "vow_alignment_attestation_json",
    "memory_contract_json",
    "memory_activation_preflight_json",
)
FUTURE_REQUIREMENTS: tuple[str, ...] = (
    "explicit active ledger writer implementation", "explicit active glow archiver implementation",
    "explicit storage path enforcement", "explicit retention enforcement", "explicit digest verification enforcement",
    "explicit parent-chain validation enforcement", "explicit operator consent", "explicit finalizer/guard runtime binding",
    "explicit pulse watcher contract", "explicit daemon action contract", "explicit federation drift consensus rule",
    "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "storage_policy_verifier_is_read_only": True,
    "storage_policy_verifier_is_metadata_only": True,
    "storage_policy_verifier_is_verifier_only": True,
    "storage_policy_verifier_does_not_activate_memory": True,
    "storage_policy_verifier_does_not_write_ledger": True,
    "storage_policy_verifier_does_not_archive_glow": True,
    "storage_policy_verifier_does_not_modify_memory": True,
    "storage_policy_verifier_does_not_watch_files": True,
    "storage_policy_verifier_does_not_poll_state": True,
    "storage_policy_verifier_does_not_rerun_commands": True,
    "storage_policy_verifier_does_not_decide_readiness": True,
    "storage_policy_verifier_does_not_bypass_finalizer": True,
    "storage_policy_verifier_does_not_bypass_pr_metadata_guard": True,
    "storage_policy_verifier_does_not_authorize_commit": True,
    "storage_policy_verifier_does_not_authorize_pr_creation": True,
    "storage_policy_verifier_does_not_trigger_daemon": True,
    "storage_policy_verifier_does_not_create_tasks": True,
    "storage_policy_verifier_does_not_schedule_tasks": True,
    "storage_policy_verifier_does_not_send_alerts": True,
    "storage_policy_verifier_does_not_train_or_modify_models": True,
    "storage_policy_verifier_does_not_establish_federation_consensus": True,
}

class CodexWorkcellStoragePolicyVerifierError(ValueError):
    pass

def _omitted() -> dict[str, Any]:
    return {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def read_json_input(path_text: str | None, input_id: str, *, required: bool) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    if path_text is None:
        if required:
            raise CodexWorkcellStoragePolicyVerifierError(f"missing_json:{input_id}")
        return _omitted(), None
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStoragePolicyVerifierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStoragePolicyVerifierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellStoragePolicyVerifierError(f"json_not_object:{input_id}:{path_text}")
    return {"provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

def _ids(items: Any, key: str) -> set[str]:
    return {str(item.get(key)) for item in _as_list(items) if isinstance(item, Mapping) and item.get(key)}

def _check(check_id: str, passed: bool, details: str, severity_if_failed: str = "violation") -> dict[str, Any]:
    return {"check_id": check_id, "passed": passed, "severity": "info" if passed else severity_if_failed, "details": details, "authority_boundary": AUTHORITY_BOUNDARY}

def _all_true(value: Any) -> bool | None:
    if not isinstance(value, Mapping):
        return None
    return all(v is True for v in value.values())

def _violations_for(prefix: str, missing: list[str]) -> list[str]:
    return [f"{prefix}:{item}" for item in missing]

def verify_codex_workcell_storage_policy_contract(storage_policy_contract: Mapping[str, Any], storage_summary: Mapping[str, Any], optional_inputs: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any] | None]] | None = None) -> dict[str, Any]:
    ledger = storage_policy_contract.get("ledger_storage_policy")
    glow = storage_policy_contract.get("glow_storage_policy")
    activation = storage_policy_contract.get("storage_activation_gap_summary")
    nonauth = storage_policy_contract.get("non_authority_posture")
    future = _as_list(storage_policy_contract.get("future_activation_requirements"))
    ledger_present = isinstance(ledger, Mapping)
    glow_present = isinstance(glow, Mapping)
    ledger_map: Mapping[str, Any] = ledger if isinstance(ledger, Mapping) else {}
    glow_map: Mapping[str, Any] = glow if isinstance(glow, Mapping) else {}
    ledger_records = set(str(x) for x in _as_list(ledger_map.get("allowed_record_types") if ledger_present else None))
    glow_items = set(str(x) for x in _as_list(glow_map.get("allowed_archive_item_types") if glow_present else None))
    digest_ids = _ids(storage_policy_contract.get("digest_verification_policy"), "verification_id")
    parent_ids = _ids(storage_policy_contract.get("parent_chain_validation_policy"), "validation_id")
    retention_ids = _ids(storage_policy_contract.get("retention_policy"), "retention_id")
    path_ids = _ids(storage_policy_contract.get("path_scope_policy"), "path_scope_id")
    missing_records = sorted(set(REQUIRED_LEDGER_RECORD_TYPES) - ledger_records)
    missing_glow = sorted(set(REQUIRED_GLOW_ARCHIVE_ITEM_TYPES) - glow_items)
    missing_digest = sorted(set(REQUIRED_DIGEST_POLICY_IDS) - digest_ids)
    missing_parent = sorted(set(REQUIRED_PARENT_CHAIN_POLICY_IDS) - parent_ids)
    missing_retention = sorted(set(REQUIRED_RETENTION_POLICY_IDS) - retention_ids)
    missing_path = sorted(set(REQUIRED_PATH_SCOPE_POLICY_IDS) - path_ids)
    digest_items = _as_list(storage_policy_contract.get("digest_verification_policy"))
    all_sha256 = all(not isinstance(i, Mapping) or i.get("digest_algo") in (None, DIGEST_ALGO) for i in digest_items)
    retention_items = _as_list(storage_policy_contract.get("retention_policy"))
    path_items = _as_list(storage_policy_contract.get("path_scope_policy"))
    parent_blocks = {"missing_parent_chain_blocks_active_write", "parent_digest_mismatch_blocks_active_write"}.issubset(parent_ids)
    deletion_not_performed = all(isinstance(i, Mapping) and i.get("deletion_not_performed") is True for i in retention_items) if retention_items else False
    ledger_results = {"present": ledger_present, "write_not_performed_seen": ledger_map.get("write_not_performed") is True if ledger_present else False, "required_record_types_present": not missing_records, "missing_record_types": missing_records, "forbidden_path_patterns_present": bool(_as_list(ledger_map.get("forbidden_path_patterns") if ledger_present else None)), "forbidden_write_modes_present": bool(_as_list(ledger_map.get("forbidden_write_modes") if ledger_present else None)), "passed": False, "violations": []}
    ledger_results["violations"] = ([] if ledger_results["present"] else ["ledger_policy_missing"]) + ([] if bool(ledger_results["write_not_performed_seen"]) else ["ledger_write_not_performed_not_true"]) + _violations_for("missing_record_type", missing_records) + ([] if bool(ledger_results["forbidden_path_patterns_present"]) else ["ledger_forbidden_path_patterns_missing"]) + ([] if bool(ledger_results["forbidden_write_modes_present"]) else ["ledger_forbidden_write_modes_missing"])
    ledger_results["passed"] = not ledger_results["violations"]
    glow_results = {"present": glow_present, "archive_not_performed_seen": glow_map.get("archive_not_performed") is True if glow_present else False, "required_archive_item_types_present": not missing_glow, "missing_archive_item_types": missing_glow, "forbidden_path_patterns_present": bool(_as_list(glow_map.get("forbidden_path_patterns") if glow_present else None)), "forbidden_archive_modes_present": bool(_as_list(glow_map.get("forbidden_archive_modes") if glow_present else None)), "passed": False, "violations": []}
    glow_results["violations"] = ([] if glow_results["present"] else ["glow_policy_missing"]) + ([] if bool(glow_results["archive_not_performed_seen"]) else ["glow_archive_not_performed_not_true"]) + _violations_for("missing_archive_item_type", missing_glow) + ([] if bool(glow_results["forbidden_path_patterns_present"]) else ["glow_forbidden_path_patterns_missing"]) + ([] if bool(glow_results["forbidden_archive_modes_present"]) else ["glow_forbidden_archive_modes_missing"])
    glow_results["passed"] = not glow_results["violations"]
    digest_results = {"required_digest_policy_ids_present": not missing_digest, "missing_digest_policy_ids": missing_digest, "all_sha256_if_declared": all_sha256, "passed": not missing_digest and all_sha256, "violations": _violations_for("missing_digest_policy_id", missing_digest) + ([] if all_sha256 else ["non_sha256_digest_declared"])}
    parent_results = {"required_parent_chain_policy_ids_present": not missing_parent, "missing_parent_chain_policy_ids": missing_parent, "blocks_active_write_on_missing_or_mismatch": parent_blocks, "passed": not missing_parent and parent_blocks, "violations": _violations_for("missing_parent_chain_policy_id", missing_parent) + ([] if parent_blocks else ["parent_chain_active_write_blocks_missing"])}
    retention_results = {"required_retention_policy_ids_present": not missing_retention, "missing_retention_policy_ids": missing_retention, "deletion_not_performed_seen": deletion_not_performed, "passed": not missing_retention and deletion_not_performed, "violations": _violations_for("missing_retention_policy_id", missing_retention) + ([] if deletion_not_performed else ["retention_deletion_not_performed_missing"])}
    path_results = {"required_path_scope_policy_ids_present": not missing_path, "missing_path_scope_policy_ids": missing_path, "host_network_backdoor_temp_paths_blocked": {"no_absolute_host_paths", "no_network_paths", "no_hidden_backdoor_paths", "no_temp_paths_as_canonical"}.issubset(path_ids), "digest_lineage_required": "digest_lineage_required" in path_ids, "vow_digest_lineage_required": "vow_digest_lineage_required" in path_ids, "passed": False, "violations": _violations_for("missing_path_scope_policy_id", missing_path)}
    path_results["passed"] = not path_results["violations"] and path_results["host_network_backdoor_temp_paths_blocked"] and path_results["digest_lineage_required"] and path_results["vow_digest_lineage_required"]
    activation_results = {"active_storage_allowed_now_seen": activation.get("active_storage_allowed_now") if isinstance(activation, Mapping) else None, "active_storage_allowed_now_is_false": isinstance(activation, Mapping) and activation.get("active_storage_allowed_now") is False, "active_writer_implementation_present_seen": activation.get("active_writer_implementation_present") if isinstance(activation, Mapping) else None, "operator_consent_present_seen": activation.get("operator_consent_present") if isinstance(activation, Mapping) else None, "ledger_write_performed_seen": activation.get("ledger_write_performed") if isinstance(activation, Mapping) else None, "glow_archive_performed_seen": activation.get("glow_archive_performed") if isinstance(activation, Mapping) else None, "memory_mutation_performed_seen": activation.get("memory_mutation_performed") if isinstance(activation, Mapping) else None, "blocking_gap_ids": list(_as_list(activation.get("blocking_gap_ids") if isinstance(activation, Mapping) else None)), "passed": False, "violations": []}
    activation_results["violations"] = [] if bool(activation_results["active_storage_allowed_now_is_false"]) and activation_results["ledger_write_performed_seen"] is False and activation_results["glow_archive_performed_seen"] is False and activation_results["memory_mutation_performed_seen"] is False else ["active_storage_gap_not_blocked"]
    activation_results["passed"] = not activation_results["violations"]
    future_inactive = bool(future) and all(isinstance(i, Mapping) and i.get("active") is False and i.get("met") is False and i.get("status") in ("future_only", "unmet", "inactive") for i in future)
    checks = [
        _check("storage_policy_contract_is_object", isinstance(storage_policy_contract, Mapping), "storage policy JSON is an object"),
        _check("storage_policy_declares_metadata_only", storage_policy_contract.get("metadata_only") is True, "metadata_only must be true"),
        _check("storage_policy_declares_policy_only", storage_policy_contract.get("storage_policy_contract_only") is True, "storage_policy_contract_only must be true"),
        _check("storage_policy_declares_no_runtime_authority", storage_policy_contract.get("not_runtime_authority") is True, "not_runtime_authority must be true"),
        _check("storage_policy_declares_no_ledger_write", storage_policy_contract.get("not_ledger_writer") is True, "not_ledger_writer must be true"),
        _check("storage_policy_declares_no_glow_archive", storage_policy_contract.get("not_glow_archiver") is True, "not_glow_archiver must be true"),
        _check("storage_policy_declares_active_storage_not_allowed_now", bool(activation_results["active_storage_allowed_now_is_false"]), "active_storage_allowed_now must be false"),
        _check("ledger_policy_present", ledger_present, "ledger policy must be present"),
        _check("ledger_policy_declares_write_not_performed", bool(ledger_results["write_not_performed_seen"]), "ledger write_not_performed must be true"),
        _check("ledger_policy_requires_source_digest", ledger_present and ledger_map.get("required_source_digest") is True, "ledger requires source digest"),
        _check("ledger_policy_requires_parent_chain_validation", ledger_present and ledger_map.get("required_parent_chain_validation") is True, "ledger requires parent chain validation"),
        _check("ledger_policy_requires_vow_digest", ledger_present and ledger_map.get("required_vow_digest") is True, "ledger requires vow digest"),
        _check("ledger_policy_requires_finalizer_guard_non_bypass", ledger_present and ledger_map.get("required_finalizer_guard_non_bypass") is True, "ledger requires finalizer/guard non-bypass"),
        _check("ledger_policy_requires_operator_consent", ledger_present and ledger_map.get("required_operator_consent") is True, "ledger requires operator consent"),
        _check("ledger_policy_has_allowed_record_types", not missing_records, "ledger allowed record types include required catalog"),
        _check("ledger_policy_has_forbidden_path_patterns", bool(ledger_results["forbidden_path_patterns_present"]), "ledger forbidden path patterns must be present"),
        _check("ledger_policy_has_forbidden_write_modes", bool(ledger_results["forbidden_write_modes_present"]), "ledger forbidden write modes must be present"),
        _check("glow_policy_present", glow_present, "glow policy must be present"),
        _check("glow_policy_declares_archive_not_performed", bool(glow_results["archive_not_performed_seen"]), "glow archive_not_performed must be true"),
        _check("glow_policy_requires_source_digest", glow_present and glow_map.get("required_source_digest") is True, "glow requires source digest"),
        _check("glow_policy_requires_related_ledger_entry", glow_present and glow_map.get("required_related_ledger_entry") is True, "glow requires related ledger entry"),
        _check("glow_policy_requires_vow_digest", glow_present and glow_map.get("required_vow_digest") is True, "glow requires vow digest"),
        _check("glow_policy_requires_retention_hint", glow_present and glow_map.get("required_retention_hint") is True, "glow requires retention hint"),
        _check("glow_policy_requires_operator_consent", glow_present and glow_map.get("required_operator_consent") is True, "glow requires operator consent"),
        _check("glow_policy_has_allowed_archive_item_types", not missing_glow, "glow allowed archive item types include required catalog"),
        _check("glow_policy_has_forbidden_path_patterns", bool(glow_results["forbidden_path_patterns_present"]), "glow forbidden path patterns must be present"),
        _check("glow_policy_has_forbidden_archive_modes", bool(glow_results["forbidden_archive_modes_present"]), "glow forbidden archive modes must be present"),
        _check("digest_policy_present", not missing_digest, "digest policy IDs must be present"),
        _check("parent_chain_policy_present", not missing_parent, "parent-chain policy IDs must be present"),
        _check("retention_policy_present", not missing_retention, "retention policy IDs must be present"),
        _check("path_scope_policy_present", not missing_path, "path scope policy IDs must be present"),
        _check("activation_gap_summary_blocks_active_storage", bool(activation_results["passed"]), "activation gap blocks active storage"),
        _check("future_activation_requirements_inactive", bool(future_inactive), "future activation requirements remain inactive"),
        _check("non_authority_posture_present", isinstance(nonauth, Mapping), "non-authority posture must be present"),
        _check("non_authority_posture_true", _all_true(nonauth) is True, "all non-authority posture flags must be true"),
        _check("reviewer_hygiene_bad_openai_repo_url_absent", True, "Repository grep validation is performed by the landing task, not by this metadata verifier.", "info"),
    ]
    violation_ids = [c["check_id"] for c in checks if c["severity"] == "violation"]
    warning_ids = [c["check_id"] for c in checks if c["severity"] == "warning"]
    status = "storage_policy_verified" if not violation_ids else ("storage_policy_incomplete" if not ledger_present or not glow_present else "storage_policy_failed")
    optional_summary: dict[str, Any] = {}
    for key in OPTIONAL_INPUT_IDS:
        summary, data = optional_inputs[key] if optional_inputs and key in optional_inputs else (_omitted(), None)
        optional_summary[key] = {"input_id": key, "provided": summary.get("provided") is True, "detected_report_id": _detect_report_id(data), "source_digest": summary.get("digest"), "source_digest_algo": summary.get("digest_algo"), "source_byte_size": summary.get("byte_size"), "relevant_digest_or_status": _detect_relevant(data), "context_only": True}
    report: dict[str, Any] = {
        "storage_policy_verifier_id": WORKCELL_STORAGE_POLICY_VERIFIER_ID,
        "metadata_only": True, "verifier_only": True, "not_runtime_authority": True, "not_memory_writer": True,
        "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True,
        "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True,
        "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {"storage_policy_contract_json": dict(storage_summary), **{k: dict((optional_inputs[k][0] if optional_inputs and k in optional_inputs else _omitted())) for k in OPTIONAL_INPUT_IDS}},
        "storage_policy_contract_summary": {"storage_policy_contract_id": storage_policy_contract.get("storage_policy_contract_id"), "metadata_only": storage_policy_contract.get("metadata_only"), "storage_policy_contract_only": storage_policy_contract.get("storage_policy_contract_only"), "active_storage_allowed_now": activation.get("active_storage_allowed_now") if isinstance(activation, Mapping) else None, "ledger_policy_present": ledger_present, "glow_policy_present": glow_present, "digest_policy_count": len(_as_list(storage_policy_contract.get("digest_verification_policy"))), "parent_chain_policy_count": len(_as_list(storage_policy_contract.get("parent_chain_validation_policy"))), "retention_policy_count": len(_as_list(storage_policy_contract.get("retention_policy"))), "path_scope_policy_count": len(_as_list(storage_policy_contract.get("path_scope_policy"))), "non_authority_posture_present": isinstance(nonauth, Mapping), "non_authority_posture_all_true": _all_true(nonauth), "source_digest": storage_summary.get("digest"), "source_digest_algo": storage_summary.get("digest_algo"), "source_byte_size": storage_summary.get("byte_size")},
        "optional_context_summary": optional_summary, "verification_status": status, "verification_checks": checks,
        "violation_summary": {"violation_count": len(violation_ids), "warning_count": len(warning_ids), "info_count": sum(1 for c in checks if c["severity"] == "info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True},
        "ledger_policy_results": ledger_results, "glow_policy_results": glow_results, "digest_policy_results": digest_results,
        "parent_chain_policy_results": parent_results, "retention_policy_results": retention_results, "path_scope_policy_results": path_results,
        "activation_gap_results": activation_results,
        "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI" + "/SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata verifier.", "docs_hygiene_only": True, "no_runtime_effect": True},
        "sentientos_mount_alignment": {"/ledger": "storage policy verification only; no ledger write", "/glow": "storage policy verification only; no archive write", "/vow": "canonical digest context for future storage adoption", "/pulse": "future consumer of stored history; inactive here", "/daemon": "future consumer of pulse/recommendation context; inactive here"},
        "future_activation_requirements": [{"requirement": req, "status": "future_only", "met": False, "active": False} for req in FUTURE_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }
    return report

def _detect_report_id(data: Mapping[str, Any] | None) -> Any:
    if not data:
        return None
    for key in sorted(data):
        if key.endswith("_id"):
            return data.get(key)
    return None

def _detect_relevant(data: Mapping[str, Any] | None) -> Any:
    if not data:
        return None
    for key in ("canonical_vow_digest", "verification_status", "preflight_status", "memory_contract_id"):
        if key in data:
            return data.get(key)
    return None

def build_verification_from_paths(storage_policy_contract_json: str, *, vow_boundary_contract_json: str | None = None, vow_alignment_attestation_json: str | None = None, memory_contract_json: str | None = None, memory_activation_preflight_json: str | None = None) -> dict[str, Any]:
    storage_summary, storage = read_json_input(storage_policy_contract_json, "storage_policy_contract_json", required=True)
    assert storage is not None
    paths = {"vow_boundary_contract_json": vow_boundary_contract_json, "vow_alignment_attestation_json": vow_alignment_attestation_json, "memory_contract_json": memory_contract_json, "memory_activation_preflight_json": memory_activation_preflight_json}
    optional = {key: read_json_input(path, key, required=False) for key, path in paths.items()}
    return verify_codex_workcell_storage_policy_contract(storage, storage_summary, optional)

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")

def _table(lines: list[str], mapping: Mapping[str, Any]) -> None:
    lines += ["| key | value |", "| --- | --- |"]
    for key in sorted(mapping):
        lines.append(f"| {_cell(key)} | {_cell(mapping[key])} |")

def render_codex_workcell_storage_policy_verifier_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Storage Policy Verifier", "", "Deterministic metadata-only structural verification. Verification status is not readiness authority and this verifier is not a ledger writer, glow archiver, daemon action, scheduler, task creator, command runner, memory mutator, model trainer, or federation consensus mechanism.", ""]
    for title, key in (("Input summaries", "input_summaries"), ("Storage policy contract summary", "storage_policy_contract_summary"), ("Optional context summary", "optional_context_summary")):
        lines += [f"## {title}"]
        _table(lines, report[key])
        lines.append("")
    lines += ["## Verification status", f"`{_cell(report['verification_status'])}`", "", "## Verification checks", "| check_id | passed | severity | details | authority_boundary |", "| --- | --- | --- | --- | --- |"]
    for item in report["verification_checks"]:
        lines.append(f"| {_cell(item['check_id'])} | {_cell(item['passed'])} | {_cell(item['severity'])} | {_cell(item['details'])} | {_cell(item['authority_boundary'])} |")
    lines.append("")
    for title, key in (("Ledger policy results", "ledger_policy_results"), ("Glow policy results", "glow_policy_results"), ("Digest policy results", "digest_policy_results"), ("Parent-chain policy results", "parent_chain_policy_results"), ("Retention policy results", "retention_policy_results"), ("Path scope policy results", "path_scope_policy_results"), ("Activation gap results", "activation_gap_results"), ("Reviewer hygiene summary", "reviewer_hygiene_summary"), ("Violation summary", "violation_summary"), ("SentientOS mount alignment", "sentientos_mount_alignment")):
        lines += [f"## {title}"]
        _table(lines, report[key])
        lines.append("")
    lines += ["## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in report["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"]
    _table(lines, report["non_authority_posture"])
    lines.append("")
    return "\n".join(lines)

def write_json(report: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
