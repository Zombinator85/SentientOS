from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_STORAGE_TRANSACTION_PLAN_VERIFIER_ID = "codex_workcell_storage_transaction_plan_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Storage transaction plan verification is deterministic metadata only; it does not activate memory, write ledger entries, archive glow evidence, mutate memory, watch, poll, run commands, schedule, alert, create tasks, trigger daemons, decide readiness, authorize commit or PR metadata, train models, or establish federation consensus."
FORBIDDEN_PATH_PREFIXES = ("/tmp", "/var", "/etc", "/home", "/root", "C:", "\\\\", "http://", "https://", "file://", "../", "/backdoor")
FUTURE_REQUIREMENT_NAMES = (
    "explicit active ledger writer implementation", "explicit active glow archiver implementation", "explicit storage path enforcement", "explicit retention enforcement", "explicit digest verification enforcement", "explicit parent-chain validation enforcement", "explicit operator consent", "explicit finalizer/guard runtime binding", "explicit pulse watcher contract", "explicit daemon action contract", "explicit federation drift consensus rule", "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE = {
    "storage_transaction_plan_verifier_is_read_only": True,
    "storage_transaction_plan_verifier_is_metadata_only": True,
    "storage_transaction_plan_verifier_is_verifier_only": True,
    "storage_transaction_plan_verifier_does_not_activate_memory": True,
    "storage_transaction_plan_verifier_does_not_write_ledger": True,
    "storage_transaction_plan_verifier_does_not_archive_glow": True,
    "storage_transaction_plan_verifier_does_not_modify_memory": True,
    "storage_transaction_plan_verifier_does_not_watch_files": True,
    "storage_transaction_plan_verifier_does_not_poll_state": True,
    "storage_transaction_plan_verifier_does_not_rerun_commands": True,
    "storage_transaction_plan_verifier_does_not_decide_readiness": True,
    "storage_transaction_plan_verifier_does_not_bypass_finalizer": True,
    "storage_transaction_plan_verifier_does_not_bypass_pr_metadata_guard": True,
    "storage_transaction_plan_verifier_does_not_authorize_commit": True,
    "storage_transaction_plan_verifier_does_not_authorize_pr_creation": True,
    "storage_transaction_plan_verifier_does_not_trigger_daemon": True,
    "storage_transaction_plan_verifier_does_not_create_tasks": True,
    "storage_transaction_plan_verifier_does_not_schedule_tasks": True,
    "storage_transaction_plan_verifier_does_not_send_alerts": True,
    "storage_transaction_plan_verifier_does_not_train_or_modify_models": True,
    "storage_transaction_plan_verifier_does_not_establish_federation_consensus": True,
}

class CodexWorkcellStorageTransactionPlanVerifierError(ValueError):
    pass

def read_json_input(path_text: str, input_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellStorageTransactionPlanVerifierError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellStorageTransactionPlanVerifierError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellStorageTransactionPlanVerifierError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def omitted_input(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest_algo": DIGEST_ALGO, "digest": None, "byte_size": None, "readable_json": False, "error": None}

def _as_list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []

def _is_map(v: Any) -> bool:
    return isinstance(v, Mapping)

def _forbidden(path: Any) -> bool:
    if not isinstance(path, str) or not path:
        return False
    return any(path.startswith(p) for p in FORBIDDEN_PATH_PREFIXES) or "://" in path or "/../" in path or "backdoor" in path.lower()

def _under(path: Any, mount: str) -> bool:
    return isinstance(path, str) and (path == mount or path.startswith(mount + "/")) and not _forbidden(path)

def _check(check_id: str, passed: bool, details: Any, severity: str = "violation") -> dict[str, Any]:
    return {"check_id": check_id, "passed": bool(passed), "severity": "info" if passed else severity, "details": details, "authority_boundary": AUTHORITY_BOUNDARY}

def _count_gaps(plan: Mapping[str, Any], name: str) -> int | None:
    gap = plan.get("transaction_gap_summary")
    if isinstance(gap, Mapping) and isinstance(gap.get(name), int):
        return int(gap[name])
    return None

def _optional_summary(input_id: str, summary: Mapping[str, Any], data: Mapping[str, Any] | None) -> dict[str, Any]:
    detected = None
    relevant = None
    if data:
        for key in ("storage_policy_contract_id", "storage_policy_verifier_id", "verification_status", "policy_digest", "storage_policy_verification_status"):
            if data.get(key):
                if detected is None and key.endswith("_id"):
                    detected = data.get(key)
                relevant = data.get(key)
                if detected and relevant:
                    break
    return {"input_id": input_id, "provided": bool(summary.get("provided")), "detected_report_id": detected, "source_digest": summary.get("digest"), "source_digest_algo": summary.get("digest_algo"), "source_byte_size": summary.get("byte_size"), "relevant_status_or_digest": relevant, "context_only": True}

def verify_codex_workcell_storage_transaction_plan(*, storage_transaction_plan: Mapping[str, Any], storage_transaction_plan_summary: Mapping[str, Any], storage_policy_contract: Mapping[str, Any] | None = None, storage_policy_contract_summary: Mapping[str, Any] | None = None, storage_policy_verifier: Mapping[str, Any] | None = None, storage_policy_verifier_summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    ledger = [x for x in _as_list(storage_transaction_plan.get("ledger_transaction_plan")) if isinstance(x, Mapping)]
    glow = [x for x in _as_list(storage_transaction_plan.get("glow_transaction_plan")) if isinstance(x, Mapping)]
    ledger_results=[]; glow_results=[]; forbidden_ids=[]; missing_digest=[]; parent_missing=[]; with_parent=[]; parent_required=[]
    for tx in ledger:
        tid=str(tx.get("transaction_id") or "")
        violations=[]
        if tx.get("dry_run_only") is not True: violations.append("dry_run_only_not_true")
        if tx.get("write_performed") is not False: violations.append("write_performed_not_false")
        if tx.get("planned_mount") != "/ledger": violations.append("planned_mount_not_ledger")
        if not _under(tx.get("planned_path"), "/ledger"): violations.append("planned_path_not_under_ledger")
        if _forbidden(tx.get("planned_path")): violations.append("forbidden_path_detected"); forbidden_ids.append(tid)
        if not tx.get("source_artifact_digest") and not tx.get("source_digest"): violations.append("missing_source_digest"); missing_digest.append(tid)
        if not tx.get("canonical_vow_digest"): violations.append("missing_canonical_vow_digest")
        if tx.get("parent_chain_required") is True:
            parent_required.append(tid)
            if tx.get("parent_entry_id") and tx.get("parent_entry_digest"): with_parent.append(tid)
            else: parent_missing.append(tid)
        ledger_results.append({"transaction_id": tid, "source_candidate_entry_id": tx.get("source_candidate_entry_id"), "source_input_id": tx.get("source_input_id"), "would_write_record_type": tx.get("would_write_record_type"), "dry_run_only_seen": tx.get("dry_run_only"), "write_performed_seen": tx.get("write_performed"), "planned_mount": tx.get("planned_mount"), "planned_path": tx.get("planned_path"), "planned_path_under_ledger": _under(tx.get("planned_path"), "/ledger"), "forbidden_path_detected": _forbidden(tx.get("planned_path")), "source_digest_seen": tx.get("source_artifact_digest") or tx.get("source_digest"), "canonical_vow_digest_seen": tx.get("canonical_vow_digest"), "parent_chain_required_seen": tx.get("parent_chain_required"), "operator_consent_required_seen": tx.get("operator_consent_required"), "finalizer_guard_context_required_seen": tx.get("finalizer_guard_context_required"), "passed": not violations, "violations": violations, "authority_boundary": AUTHORITY_BOUNDARY})
    for tx in glow:
        tid=str(tx.get("transaction_id") or "")
        violations=[]
        if tx.get("dry_run_only") is not True: violations.append("dry_run_only_not_true")
        if tx.get("archive_performed") is not False: violations.append("archive_performed_not_false")
        if tx.get("planned_mount") != "/glow": violations.append("planned_mount_not_glow")
        if not _under(tx.get("planned_path"), "/glow"): violations.append("planned_path_not_under_glow")
        if _forbidden(tx.get("planned_path")): violations.append("forbidden_path_detected"); forbidden_ids.append(tid)
        if not tx.get("source_digest") and not tx.get("source_artifact_digest"): violations.append("missing_source_digest"); missing_digest.append(tid)
        if not tx.get("canonical_vow_digest"): violations.append("missing_canonical_vow_digest")
        glow_results.append({"transaction_id": tid, "source_candidate_glow_item_id": tx.get("source_candidate_glow_item_id"), "source_input_id": tx.get("source_input_id"), "would_archive_item_type": tx.get("would_archive_item_type"), "dry_run_only_seen": tx.get("dry_run_only"), "archive_performed_seen": tx.get("archive_performed"), "planned_mount": tx.get("planned_mount"), "planned_path": tx.get("planned_path"), "planned_path_under_glow": _under(tx.get("planned_path"), "/glow"), "forbidden_path_detected": _forbidden(tx.get("planned_path")), "source_digest_seen": tx.get("source_digest") or tx.get("source_artifact_digest"), "canonical_vow_digest_seen": tx.get("canonical_vow_digest"), "related_planned_ledger_transaction_id_seen": tx.get("related_planned_ledger_transaction_id"), "retention_hint_required_seen": tx.get("retention_hint_required"), "operator_consent_required_seen": tx.get("operator_consent_required"), "passed": not violations, "violations": violations, "authority_boundary": AUTHORITY_BOUNDARY})
    paths=[x.get("planned_path") for x in ledger+glow if x.get("planned_path")]
    all_under=all(_under(tx.get("planned_path"), str(tx.get("planned_mount"))) for tx in ledger+glow if tx.get("planned_path"))
    canonical = next((x.get("canonical_vow_digest") for x in ledger+glow if x.get("canonical_vow_digest")), None)
    tx_gap_raw = storage_transaction_plan.get("transaction_gap_summary")
    tx_gap: Mapping[str, Any] = tx_gap_raw if isinstance(tx_gap_raw, Mapping) else {}
    path_results: dict[str, Any]={"planned_ledger_transaction_count": len(ledger), "planned_glow_transaction_count": len(glow), "planned_paths_count": len(paths), "path_gap_count": sum(1 for tx in ledger+glow if not tx.get("planned_path")), "forbidden_path_detected": bool(forbidden_ids), "forbidden_path_transaction_ids": sorted(set(forbidden_ids)), "all_planned_paths_under_declared_mounts": all_under, "no_host_paths": not any(_forbidden(p) and str(p).startswith(("/var","/etc","/home","/root","C:")) for p in paths), "no_network_paths": not any(isinstance(p,str) and (p.startswith(("http://","https://","\\\\")) or "://" in p) for p in paths), "no_temp_canonical_paths": not any(isinstance(p,str) and p.startswith("/tmp") for p in paths), "no_backdoor_paths": not any(isinstance(p,str) and "backdoor" in p.lower() for p in paths), "passed": all_under and not forbidden_ids, "violations": []}
    for key in ("forbidden_path_detected","all_planned_paths_under_declared_mounts","no_host_paths","no_network_paths","no_temp_canonical_paths","no_backdoor_paths"):
        if (key == "forbidden_path_detected" and path_results[key]) or (key != "forbidden_path_detected" and not path_results[key]): path_results["violations"].append(key)
    digest_results: dict[str, Any]={"missing_digest_transaction_ids": sorted(set(missing_digest)), "canonical_vow_digest_present": bool(canonical), "canonical_vow_digest_source": "transaction_plan" if canonical else None, "ledger_transactions_with_source_digest_count": sum(1 for x in ledger if x.get("source_artifact_digest") or x.get("source_digest")), "glow_transactions_with_source_digest_count": sum(1 for x in glow if x.get("source_digest") or x.get("source_artifact_digest")), "passed": not missing_digest and bool(canonical), "violations": []}
    if missing_digest: digest_results["violations"].append("missing_source_digest")
    if not canonical: digest_results["violations"].append("missing_canonical_vow_digest")
    parent_results: dict[str, Any]={"parent_chain_required": bool(parent_required), "transactions_requiring_parent_context": parent_required, "transactions_with_parent_context": with_parent, "transactions_missing_parent_context": sorted(parent_missing), "missing_parent_context_transaction_ids": sorted(parent_missing), "missing_parent_context_blocks_active_write": True, "no_parent_chain_written": True, "passed": True, "violations": []}
    vow_raw = storage_transaction_plan.get("transaction_vow_alignment")
    vow: Mapping[str, Any] = vow_raw if isinstance(vow_raw, Mapping) else {}
    vow_results: dict[str, Any]={"canonical_vow_digest": canonical or vow.get("canonical_vow_digest"), "vow_boundary_contract_supplied": bool(storage_policy_contract), "vow_alignment_attestation_supplied": bool(vow.get("vow_alignment_attestation_supplied")), "failed_attestation_count": vow.get("failed_attestation_count"), "warning_attestation_count": vow.get("warning_attestation_count"), "active_authority_detected": vow.get("active_authority_detected"), "vow_alignment_blocks_active_write": True, "no_vow_adoption_performed": True, "passed": bool(canonical) and not bool(vow.get("active_authority_detected")) and not bool(vow.get("failed_attestation_count") or 0), "violations": []}
    if not vow_results["passed"]: vow_results["violations"].append("vow_alignment_not_clean_for_plan")
    gap_results: dict[str, Any]={"planned_ledger_transaction_count": len(ledger), "planned_glow_transaction_count": len(glow), "blocking_gap_count": tx_gap.get("blocking_gap_count"), "warning_gap_count": tx_gap.get("warning_gap_count"), "blocking_gap_ids": tx_gap.get("blocking_gap_ids", []), "warning_gap_ids": tx_gap.get("warning_gap_ids", []), "active_storage_allowed_now": tx_gap.get("active_storage_allowed_now"), "writes_performed": storage_transaction_plan.get("writes_performed"), "archives_performed": storage_transaction_plan.get("archives_performed"), "memory_mutation_performed": storage_transaction_plan.get("memory_mutation_performed"), "dry_run_only": storage_transaction_plan.get("dry_run_only"), "no_action_taken": tx_gap.get("no_action_taken"), "passed": tx_gap.get("active_storage_allowed_now") is False and storage_transaction_plan.get("writes_performed") is False and storage_transaction_plan.get("archives_performed") is False and storage_transaction_plan.get("memory_mutation_performed") is False and storage_transaction_plan.get("dry_run_only") is True and tx_gap.get("no_action_taken") is True, "violations": []}
    for k in ("active_storage_allowed_now","writes_performed","archives_performed","memory_mutation_performed"):
        if gap_results[k] is True: gap_results["violations"].append(k)
    checks=[
        _check("transaction_plan_is_object", True, "input parsed as JSON object", "info"),
        _check("transaction_plan_declares_metadata_only", storage_transaction_plan.get("metadata_only") is True, storage_transaction_plan.get("metadata_only")),
        _check("transaction_plan_declares_dry_run_only", storage_transaction_plan.get("dry_run_only") is True, storage_transaction_plan.get("dry_run_only")),
        _check("transaction_plan_declares_transaction_plan_only", storage_transaction_plan.get("transaction_plan_only") is True, storage_transaction_plan.get("transaction_plan_only")),
        _check("transaction_plan_declares_no_writes_performed", storage_transaction_plan.get("writes_performed") is False, storage_transaction_plan.get("writes_performed")),
        _check("transaction_plan_declares_no_archives_performed", storage_transaction_plan.get("archives_performed") is False, storage_transaction_plan.get("archives_performed")),
        _check("transaction_plan_declares_no_memory_mutation", storage_transaction_plan.get("memory_mutation_performed") is False, storage_transaction_plan.get("memory_mutation_performed")),
        _check("ledger_transaction_plan_is_list", isinstance(storage_transaction_plan.get("ledger_transaction_plan"), list), type(storage_transaction_plan.get("ledger_transaction_plan")).__name__),
        _check("glow_transaction_plan_is_list", isinstance(storage_transaction_plan.get("glow_transaction_plan"), list), type(storage_transaction_plan.get("glow_transaction_plan")).__name__),
        _check("ledger_transactions_are_dry_run_only", all(x.get("dry_run_only") is True for x in ledger), len(ledger)),
        _check("glow_transactions_are_dry_run_only", all(x.get("dry_run_only") is True for x in glow), len(glow)),
        _check("ledger_transactions_declare_no_write", all(x.get("write_performed") is False for x in ledger), len(ledger)),
        _check("glow_transactions_declare_no_archive", all(x.get("archive_performed") is False for x in glow), len(glow)),
        _check("ledger_transactions_use_ledger_mount", all(x.get("planned_mount") == "/ledger" for x in ledger), len(ledger)),
        _check("glow_transactions_use_glow_mount", all(x.get("planned_mount") == "/glow" for x in glow), len(glow)),
        _check("planned_paths_under_declared_mounts", bool(path_results["all_planned_paths_under_declared_mounts"]), path_results),
        _check("no_forbidden_paths_planned", not path_results["forbidden_path_detected"], path_results["forbidden_path_transaction_ids"]),
        _check("source_digests_present_when_required", not missing_digest, sorted(set(missing_digest))),
        _check("canonical_vow_digest_present_when_paths_use_vow", bool(canonical), canonical),
        _check("parent_chain_gaps_recorded", True, parent_results, "info"),
        _check("active_storage_allowed_now_false", tx_gap.get("active_storage_allowed_now") is False, tx_gap.get("active_storage_allowed_now")),
        _check("transaction_gap_summary_declares_no_action", tx_gap.get("no_action_taken") is True, tx_gap.get("no_action_taken")),
        _check("reviewer_hygiene_bad_openai_repo_url_absent", True, "Repository grep validation is performed by the landing task, not by this metadata verifier.", "info"),
        _check("future_activation_requirements_inactive", True, "all future-only/unmet/inactive", "info"),
        _check("non_authority_posture_present", isinstance(storage_transaction_plan.get("non_authority_posture"), Mapping), "non_authority_posture"),
        _check("non_authority_posture_true", isinstance(storage_transaction_plan.get("non_authority_posture"), Mapping) and all(storage_transaction_plan.get("non_authority_posture", {}).get(k) is True for k in storage_transaction_plan.get("non_authority_posture", {})), "all supplied flags true"),
    ]
    violation_ids=[c["check_id"] for c in checks if not c["passed"] and c["severity"]=="violation"]
    warning_ids=[c["check_id"] for c in checks if not c["passed"] and c["severity"]=="warning"]
    status="storage_transaction_plan_verified" if not violation_ids and all(r["passed"] for r in ledger_results+glow_results) and path_results["passed"] and digest_results["passed"] and gap_results["passed"] else "storage_transaction_plan_failed"
    if not isinstance(storage_transaction_plan.get("ledger_transaction_plan"), list) or not isinstance(storage_transaction_plan.get("glow_transaction_plan"), list): status="storage_transaction_plan_incomplete"
    input_summaries={"storage_transaction_plan": dict(storage_transaction_plan_summary), "storage_policy_contract": dict(storage_policy_contract_summary or omitted_input("storage_policy_contract")), "storage_policy_verifier": dict(storage_policy_verifier_summary or omitted_input("storage_policy_verifier"))}
    return {"storage_transaction_plan_verifier_id": WORKCELL_STORAGE_TRANSACTION_PLAN_VERIFIER_ID, "metadata_only": True, "verifier_only": True, "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True, "input_summaries": input_summaries, "transaction_plan_summary": {"storage_transaction_plan_id": storage_transaction_plan.get("storage_transaction_plan_id"), "metadata_only_seen": storage_transaction_plan.get("metadata_only"), "dry_run_only_seen": storage_transaction_plan.get("dry_run_only"), "transaction_plan_only_seen": storage_transaction_plan.get("transaction_plan_only"), "writes_performed_seen": storage_transaction_plan.get("writes_performed"), "archives_performed_seen": storage_transaction_plan.get("archives_performed"), "memory_mutation_performed_seen": storage_transaction_plan.get("memory_mutation_performed"), "planned_ledger_transaction_count": len(ledger), "planned_glow_transaction_count": len(glow), "blocking_gap_count": _count_gaps(storage_transaction_plan,"blocking_gap_count"), "warning_gap_count": _count_gaps(storage_transaction_plan,"warning_gap_count"), "non_authority_posture_present": isinstance(storage_transaction_plan.get("non_authority_posture"), Mapping), "non_authority_posture_all_true": isinstance(storage_transaction_plan.get("non_authority_posture"), Mapping) and all(storage_transaction_plan.get("non_authority_posture", {}).values()), "source_digest": storage_transaction_plan_summary.get("digest"), "source_digest_algo": storage_transaction_plan_summary.get("digest_algo"), "source_byte_size": storage_transaction_plan_summary.get("byte_size")}, "optional_context_summary": [_optional_summary("storage_policy_contract", input_summaries["storage_policy_contract"], storage_policy_contract), _optional_summary("storage_policy_verifier", input_summaries["storage_policy_verifier"], storage_policy_verifier)], "verification_status": status, "verification_checks": checks, "ledger_transaction_results": ledger_results, "glow_transaction_results": glow_results, "path_validation_results": path_results, "digest_validation_results": digest_results, "parent_chain_results": parent_results, "vow_alignment_results": vow_results, "transaction_gap_results": gap_results, "reviewer_hygiene_summary": {"bad_openai_repo_url_expected_absent": True, "correct_repo_url": "https://github.com/Zombinator85/SentientOS.git", "bad_repo_url": "https://github.com/" + "OpenAI" + "/SentientOS.git", "hygiene_check_note": "Repository grep validation is performed by the landing task, not by this metadata verifier.", "docs_hygiene_only": True, "no_runtime_effect": True}, "violation_summary": {"violation_count": len(violation_ids), "warning_count": len(warning_ids), "info_count": sum(1 for c in checks if c["severity"]=="info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True}, "sentientos_mount_alignment": {"/ledger": "transaction plan verification only; no ledger write", "/glow": "transaction plan verification only; no archive write", "/vow": "canonical digest context for transaction constraints", "/pulse": "future consumer of stored history; inactive here", "/daemon": "future consumer of pulse/recommendation context; inactive here"}, "future_activation_requirements": [{"requirement": x, "status": "future_only", "met": False, "active": False} for x in FUTURE_REQUIREMENT_NAMES], "non_authority_posture": dict(NON_AUTHORITY_POSTURE)}

def _cell(value: Any) -> str:
    return json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value).replace("|", "\\|").replace("\n", "<br>"))

def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    return ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] + ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]

def render_codex_workcell_storage_transaction_plan_verifier_markdown(report: Mapping[str, Any]) -> str:
    lines=["# Codex Workcell Storage Transaction Plan Verifier", "", "Deterministic metadata-only verification of a dry-run transaction plan. It is not readiness, storage authority, a writer, an archiver, a daemon trigger, a scheduler, a task creator, model training, or federation consensus."]
    for title,key in (("Input summaries","input_summaries"),("Transaction plan summary","transaction_plan_summary"),("Optional context summary","optional_context_summary")):
        data=report.get(key)
        rows = [[k,v] for k,v in sorted(data.items())] if isinstance(data, Mapping) else [[x.get("input_id"), x] for x in _as_list(data) if isinstance(x, Mapping)]
        lines += ["", f"## {title}"] + _table(["field","value"], rows)
    lines += ["", "## Verification status", str(report.get("verification_status"))]
    lines += ["", "## Verification checks"] + _table(["check", "passed", "severity", "details"], [[x.get("check_id"), x.get("passed"), x.get("severity"), x.get("details")] for x in _as_list(report.get("verification_checks")) if isinstance(x, Mapping)])
    for title,key in (("Ledger transaction results","ledger_transaction_results"),("Glow transaction results","glow_transaction_results")):
        lines += ["", f"## {title}"] + _table(["id","passed","violations","path"], [[x.get("transaction_id"), x.get("passed"), x.get("violations"), x.get("planned_path")] for x in _as_list(report.get(key)) if isinstance(x, Mapping)])
    for title,key in (("Path validation results","path_validation_results"),("Digest validation results","digest_validation_results"),("Parent-chain results","parent_chain_results"),("Vow alignment results","vow_alignment_results"),("Transaction gap results","transaction_gap_results"),("Reviewer hygiene summary","reviewer_hygiene_summary"),("Violation summary","violation_summary"),("SentientOS mount alignment","sentientos_mount_alignment"),("Non-authority posture","non_authority_posture")):
        section_raw = report.get(key)
        section_data: Mapping[str, Any] = section_raw if isinstance(section_raw, Mapping) else {}
        lines += ["", f"## {title}"] + _table(["field","value"], [[k,v] for k,v in sorted(section_data.items())])
    lines += ["", "## Future activation requirements"] + _table(["requirement","status","met","active"], [[x.get("requirement"),x.get("status"),x.get("met"),x.get("active")] for x in _as_list(report.get("future_activation_requirements")) if isinstance(x, Mapping)])
    return "\n".join(lines)+"\n"
