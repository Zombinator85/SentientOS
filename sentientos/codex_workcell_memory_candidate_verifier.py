from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from sentientos.codex_workcell_memory_candidate_bundle import GLOW_BY_INPUT, LEDGER_BY_INPUT
from sentientos.codex_workcell_memory_contract import GLOW_ARCHIVE_ITEM_TYPES, LEDGER_RECORD_TYPES, SOURCE_ARTIFACT_FAMILIES

WORKCELL_MEMORY_CANDIDATE_VERIFIER_ID = "codex_workcell_memory_candidate_verifier.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Verifier metadata only; does not write ledger, archive glow, mutate memory, decide readiness, run commands, trigger daemon action, schedule work, create tasks, alert, train models, or establish consensus."

FUTURE_REQUIREMENTS: tuple[str, ...] = (
    "explicit ledger writer implementation", "explicit glow archiver implementation", "explicit storage path policy",
    "explicit retention policy", "explicit digest verification policy", "explicit parent-chain validation policy",
    "explicit operator consent", "explicit finalizer/guard non-bypass invariant", "explicit pulse watcher contract",
    "explicit daemon action contract", "explicit federation drift consensus rule", "explicit vow digest constraint check",
    "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "memory_candidate_verifier_is_read_only": True,
    "memory_candidate_verifier_is_metadata_only": True,
    "memory_candidate_verifier_is_verifier_only": True,
    "memory_candidate_verifier_does_not_write_ledger": True,
    "memory_candidate_verifier_does_not_archive_glow": True,
    "memory_candidate_verifier_does_not_modify_memory": True,
    "memory_candidate_verifier_does_not_watch_files": True,
    "memory_candidate_verifier_does_not_poll_state": True,
    "memory_candidate_verifier_does_not_rerun_commands": True,
    "memory_candidate_verifier_does_not_decide_readiness": True,
    "memory_candidate_verifier_does_not_bypass_finalizer": True,
    "memory_candidate_verifier_does_not_bypass_pr_metadata_guard": True,
    "memory_candidate_verifier_does_not_authorize_commit": True,
    "memory_candidate_verifier_does_not_authorize_pr_creation": True,
    "memory_candidate_verifier_does_not_trigger_daemon": True,
    "memory_candidate_verifier_does_not_create_tasks": True,
    "memory_candidate_verifier_does_not_schedule_tasks": True,
    "memory_candidate_verifier_does_not_send_alerts": True,
    "memory_candidate_verifier_does_not_train_or_modify_models": True,
    "memory_candidate_verifier_does_not_establish_federation_consensus": True,
}

class CodexWorkcellMemoryCandidateVerifierError(ValueError):
    pass

def read_json_input(path_text: str | None, input_id: str, *, required: bool) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    if path_text is None:
        if required:
            raise CodexWorkcellMemoryCandidateVerifierError(f"missing_{input_id}")
        return ({"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}, None)
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellMemoryCandidateVerifierError(f"missing_{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellMemoryCandidateVerifierError(f"invalid_{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellMemoryCandidateVerifierError(f"{input_id}_not_object:{path_text}")
    return ({"provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded)

def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

def _provided_inputs(bundle: Mapping[str, Any]) -> set[str]:
    summaries = bundle.get("input_summaries", {})
    if not isinstance(summaries, Mapping):
        return set()
    return {str(k) for k, v in summaries.items() if isinstance(v, Mapping) and v.get("provided") is True}

def _known_from_contract(contract: Mapping[str, Any] | None) -> tuple[set[str], set[str], list[str]]:
    if contract is None:
        return set(LEDGER_RECORD_TYPES) | {v for v in LEDGER_BY_INPUT.values() if v}, set(GLOW_ARCHIVE_ITEM_TYPES) | set(GLOW_BY_INPUT.values()), list(SOURCE_ARTIFACT_FAMILIES)
    ledger = contract.get("ledger_receipt_chain_contract", {})
    glow = contract.get("glow_evidence_archive_contract", {})
    alignment = contract.get("source_artifact_alignment", [])
    record_types = {str(item.get("record_type")) for item in _as_list(ledger.get("record_catalog") if isinstance(ledger, Mapping) else None) if isinstance(item, Mapping) and item.get("record_type")}
    item_types = {str(item.get("archive_item_type")) for item in _as_list(glow.get("archive_catalog") if isinstance(glow, Mapping) else None) if isinstance(item, Mapping) and item.get("archive_item_type")}
    families = [str(item.get("artifact_family")) for item in _as_list(alignment) if isinstance(item, Mapping) and item.get("artifact_family")]
    return record_types, item_types, families

def _check(check_id: str, passed: bool, details: str, severity_if_failed: str = "violation") -> dict[str, Any]:
    return {"check_id": check_id, "passed": passed, "severity": "info" if passed else severity_if_failed, "details": details, "authority_boundary": AUTHORITY_BOUNDARY}

def verify_codex_workcell_memory_candidate_bundle(candidate_bundle: Mapping[str, Any], candidate_summary: Mapping[str, Any], memory_contract: Mapping[str, Any] | None = None, memory_contract_summary_input: Mapping[str, Any] | None = None) -> dict[str, Any]:
    contract_provided = memory_contract is not None
    known_records, known_glow, families = _known_from_contract(memory_contract)
    ledger_entries = _as_list(candidate_bundle.get("candidate_ledger_entries"))
    glow_items = _as_list(candidate_bundle.get("candidate_glow_items"))
    source_map = _as_list(candidate_bundle.get("source_artifact_map"))
    provided_inputs = _provided_inputs(candidate_bundle)
    ledger_ids = [str(e.get("candidate_entry_id")) for e in ledger_entries if isinstance(e, Mapping) and e.get("candidate_entry_id") is not None]
    glow_ids = [str(g.get("candidate_glow_item_id")) for g in glow_items if isinstance(g, Mapping) and g.get("candidate_glow_item_id") is not None]
    ledger_id_set, glow_id_set = set(ledger_ids), set(glow_ids)

    ledger_results = []
    for e in ledger_entries:
        if not isinstance(e, Mapping):
            continue
        sid = e.get("source_input_id")
        typ = e.get("would_be_record_type")
        violations = []
        if sid not in provided_inputs: violations.append("source_input_missing")
        if typ not in known_records: violations.append("unknown_record_type")
        if e.get("candidate_only") is not True: violations.append("candidate_only_not_true")
        if e.get("no_write_performed") is not True: violations.append("no_write_performed_not_true")
        if not e.get("source_artifact_digest"): violations.append("source_digest_missing")
        ledger_results.append({"candidate_entry_id": e.get("candidate_entry_id"), "source_input_id": sid, "source_input_provided": sid in provided_inputs, "would_be_record_type": typ, "record_type_known": typ in known_records, "candidate_only_seen": e.get("candidate_only") is True, "no_write_performed_seen": e.get("no_write_performed") is True, "source_digest_seen": bool(e.get("source_artifact_digest")), "passed": not violations, "violations": violations, "authority_boundary": AUTHORITY_BOUNDARY})

    glow_results = []
    for g in glow_items:
        if not isinstance(g, Mapping):
            continue
        sid = g.get("source_input_id")
        typ = g.get("would_be_archive_item_type")
        related = g.get("related_candidate_ledger_entry_id")
        violations = []
        if sid not in provided_inputs: violations.append("source_input_missing")
        if typ not in known_glow: violations.append("unknown_archive_item_type")
        if g.get("candidate_only") is not True: violations.append("candidate_only_not_true")
        if g.get("no_archive_performed") is not True: violations.append("no_archive_performed_not_true")
        if not g.get("source_digest"): violations.append("source_digest_missing")
        if related is not None and related not in ledger_id_set: violations.append("related_candidate_ledger_entry_id_missing")
        glow_results.append({"candidate_glow_item_id": g.get("candidate_glow_item_id"), "source_input_id": sid, "source_input_provided": sid in provided_inputs, "would_be_archive_item_type": typ, "archive_item_type_known": typ in known_glow, "candidate_only_seen": g.get("candidate_only") is True, "no_archive_performed_seen": g.get("no_archive_performed") is True, "source_digest_seen": bool(g.get("source_digest")), "related_candidate_ledger_entry_id_seen": related, "related_candidate_ledger_entry_id_exists": related in ledger_id_set if related is not None else None, "passed": not violations, "violations": violations, "authority_boundary": AUTHORITY_BOUNDARY})

    source_results = []
    for item in source_map:
        if not isinstance(item, Mapping):
            continue
        linked_l = [str(x) for x in _as_list(item.get("candidate_ledger_entry_ids"))]
        linked_g = [str(x) for x in _as_list(item.get("candidate_glow_item_ids"))]
        l_ok = all(x in ledger_id_set for x in linked_l)
        g_ok = all(x in glow_id_set for x in linked_g)
        violations = ([] if item.get("input_id") in provided_inputs else ["source_input_missing"]) + ([] if l_ok else ["linked_ledger_id_missing"]) + ([] if g_ok else ["linked_glow_id_missing"])
        source_results.append({"input_id": item.get("input_id"), "provided": item.get("input_id") in provided_inputs, "linked_candidate_ledger_entry_ids": linked_l, "linked_candidate_glow_item_ids": linked_g, "all_linked_ledger_ids_exist": l_ok, "all_linked_glow_ids_exist": g_ok, "passed": not violations, "violations": violations, "authority_boundary": AUTHORITY_BOUNDARY})

    chain = candidate_bundle.get("candidate_chain_summary", {}) if isinstance(candidate_bundle.get("candidate_chain_summary"), Mapping) else {}
    archive = candidate_bundle.get("candidate_archive_summary", {}) if isinstance(candidate_bundle.get("candidate_archive_summary"), Mapping) else {}
    chain_results = {"reported_candidate_ledger_entry_count": chain.get("candidate_ledger_entry_count"), "actual_candidate_ledger_entry_count": len(ledger_entries), "reported_candidate_glow_item_count": None, "actual_candidate_glow_item_count": len(glow_items), "count_match": chain.get("candidate_ledger_entry_count") == len(ledger_entries), "no_ledger_write_performed_seen": chain.get("no_ledger_write_performed") is True, "no_glow_archive_performed_seen": None}
    archive_results = {"reported_candidate_ledger_entry_count": None, "actual_candidate_ledger_entry_count": len(ledger_entries), "reported_candidate_glow_item_count": archive.get("candidate_glow_item_count"), "actual_candidate_glow_item_count": len(glow_items), "count_match": archive.get("candidate_glow_item_count") == len(glow_items), "no_ledger_write_performed_seen": None, "no_glow_archive_performed_seen": archive.get("no_glow_archive_performed") is True}
    future = candidate_bundle.get("future_activation_requirements", [])
    posture = candidate_bundle.get("non_authority_posture", {})
    required_posture = {k.replace("memory_candidate_verifier", "memory_candidate_bundle"): True for k in NON_AUTHORITY_POSTURE}

    checks = [
        _check("candidate_bundle_is_object", isinstance(candidate_bundle, Mapping), "candidate bundle parsed as JSON object"),
        _check("candidate_bundle_declares_metadata_only", candidate_bundle.get("metadata_only") is True, "metadata_only must be true"),
        _check("candidate_bundle_declares_candidate_only", candidate_bundle.get("candidate_bundle_only") is True or candidate_bundle.get("candidate_only") is True, "candidate-only declaration must be true"),
        _check("candidate_bundle_declares_no_ledger_write", candidate_bundle.get("not_ledger_writer") is True and chain.get("no_ledger_write_performed") is True, "no ledger write declarations must be true"),
        _check("candidate_bundle_declares_no_glow_archive", candidate_bundle.get("not_glow_archiver") is True and archive.get("no_glow_archive_performed") is True, "no glow archive declarations must be true"),
        _check("input_summaries_exist", isinstance(candidate_bundle.get("input_summaries"), Mapping), "input_summaries must exist"),
        _check("candidate_ledger_entries_are_list", isinstance(candidate_bundle.get("candidate_ledger_entries"), list), "candidate_ledger_entries must be a list"),
        _check("candidate_glow_items_are_list", isinstance(candidate_bundle.get("candidate_glow_items"), list), "candidate_glow_items must be a list"),
        _check("source_artifact_map_exists", isinstance(candidate_bundle.get("source_artifact_map"), list), "source_artifact_map must be a list"),
        _check("candidate_ledger_entry_ids_unique", len(ledger_ids) == len(ledger_id_set), "candidate ledger entry ids must be unique"),
        _check("candidate_glow_item_ids_unique", len(glow_ids) == len(glow_id_set), "candidate glow item ids must be unique"),
        _check("ledger_entries_reference_provided_inputs", all(r["source_input_provided"] for r in ledger_results), "ledger entries must reference provided inputs"),
        _check("glow_items_reference_provided_inputs", all(r["source_input_provided"] for r in glow_results), "glow items must reference provided inputs"),
        _check("source_artifact_map_links_existing_ledger_ids", all(r["all_linked_ledger_ids_exist"] for r in source_results), "source map ledger ids must exist"),
        _check("source_artifact_map_links_existing_glow_ids", all(r["all_linked_glow_ids_exist"] for r in source_results), "source map glow ids must exist"),
        _check("candidate_chain_summary_counts_match", bool(chain_results["count_match"]), "chain summary count must match actual ledger entries"),
        _check("candidate_archive_summary_counts_match", bool(archive_results["count_match"]), "archive summary count must match actual glow items"),
        _check("ledger_entries_have_candidate_only_true", all(r["candidate_only_seen"] for r in ledger_results), "ledger entries must have candidate_only true"),
        _check("glow_items_have_candidate_only_true", all(r["candidate_only_seen"] for r in glow_results), "glow items must have candidate_only true"),
        _check("ledger_entries_have_no_write_true", all(r["no_write_performed_seen"] for r in ledger_results), "ledger entries must have no_write_performed true"),
        _check("glow_items_have_no_archive_true", all(r["no_archive_performed_seen"] for r in glow_results), "glow items must have no_archive_performed true"),
        _check("future_activation_requirements_inactive", isinstance(future, list) and all(isinstance(i, Mapping) and i.get("active") is False and i.get("met") is False for i in future), "future activation requirements must be inactive and unmet"),
        _check("non_authority_posture_present", isinstance(posture, Mapping), "non_authority_posture must be present"),
        _check("non_authority_posture_true", isinstance(posture, Mapping) and all(posture.get(k) is True for k in required_posture), "bundle non-authority posture flags must be true"),
        _check("contract_record_types_known_when_contract_supplied", (not contract_provided) or all(r["record_type_known"] for r in ledger_results), "record types must be known when contract supplied"),
        _check("contract_glow_item_types_known_when_contract_supplied", (not contract_provided) or all(r["archive_item_type_known"] for r in glow_results), "archive item types must be known when contract supplied"),
    ]
    violation_ids = [c["check_id"] for c in checks if not c["passed"] and c["severity"] == "violation"]
    warning_ids = [c["check_id"] for c in checks if not c["passed"] and c["severity"] == "warning"]
    status = "memory_candidate_bundle_verified" if not violation_ids else ("memory_candidate_bundle_incomplete" if not isinstance(candidate_bundle.get("input_summaries"), Mapping) else "memory_candidate_bundle_failed")
    msum = dict(memory_contract_summary_input or {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None})
    memory_contract_summary = {"provided": contract_provided, "workcell_memory_contract_id": memory_contract.get("workcell_memory_contract_id") if memory_contract else None, "known_ledger_record_types": sorted(known_records), "known_glow_archive_item_types": sorted(known_glow), "known_source_artifact_families": sorted(families), "digest": msum.get("digest"), "byte_size": msum.get("byte_size")}
    return {
        "memory_candidate_verifier_id": WORKCELL_MEMORY_CANDIDATE_VERIFIER_ID, "metadata_only": True, "verifier_only": True,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {"candidate_bundle_json": dict(candidate_summary), "memory_contract_json": msum},
        "candidate_bundle_summary": {"candidate_bundle_id": candidate_bundle.get("memory_candidate_bundle_id"), "candidate_ledger_entry_count": len(ledger_entries), "candidate_glow_item_count": len(glow_items), "source_artifact_count": len(source_map), "candidate_only": candidate_bundle.get("candidate_bundle_only", candidate_bundle.get("candidate_only")), "no_ledger_write_performed": chain.get("no_ledger_write_performed"), "no_glow_archive_performed": archive.get("no_glow_archive_performed"), "digest": candidate_summary.get("digest"), "byte_size": candidate_summary.get("byte_size")},
        "memory_contract_summary": memory_contract_summary, "verification_status": status, "verification_checks": checks,
        "violation_summary": {"violation_count": len(violation_ids), "warning_count": len(warning_ids), "info_count": sum(1 for c in checks if c["severity"] == "info"), "violation_check_ids": violation_ids, "warning_check_ids": warning_ids, "verifier_only": True, "no_action_taken": True},
        "candidate_ledger_entry_results": ledger_results, "candidate_glow_item_results": glow_results, "source_artifact_map_results": source_results,
        "chain_summary_results": chain_results, "archive_summary_results": archive_results,
        "sentientos_mount_alignment": {"/ledger": "candidate verification only; no ledger write", "/glow": "candidate verification only; no archive write", "/pulse": "future consumer of stored history; inactive here", "/daemon": "future consumer of pulse/recommendation context; inactive here", "/vow": "canonical constraints bounding verification interpretation and forbidden inference"},
        "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\\r\\n", "<br>").replace("\\n", "<br>").replace("\\r", "<br>").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")

def render_codex_workcell_memory_candidate_verifier_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Memory Candidate Verifier", "", "Deterministic metadata-only structural verification. This report is verifier-only and does not grant readiness, write /ledger, archive /glow, mutate memory, trigger daemons, schedule work, create tasks, alert, train models, or establish consensus."]
    lines += ["", "## Input summary", "| input | provided | path | digest | byte_size | readable_json | error |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for key, summary in sorted(report["input_summaries"].items()):
        lines.append(f"| {_cell(key)} | {_cell(summary.get('provided'))} | {_cell(summary.get('path'))} | {_cell(summary.get('digest'))} | {_cell(summary.get('byte_size'))} | {_cell(summary.get('readable_json'))} | {_cell(summary.get('error'))} |")
    for title, key in (("Candidate bundle summary", "candidate_bundle_summary"), ("Memory contract summary", "memory_contract_summary")):
        lines += ["", f"## {title}", f"`{_cell(report[key])}`"]
    lines += ["", "## Verification status", _cell(report["verification_status"]), "", "## Verification checks", "| check_id | passed | severity | details |", "| --- | --- | --- | --- |"]
    for check in report["verification_checks"]:
        lines.append(f"| {_cell(check['check_id'])} | {_cell(check['passed'])} | {_cell(check['severity'])} | {_cell(check['details'])} |")
    lines += ["", "## Violation summary", f"`{_cell(report['violation_summary'])}`", "", "## Candidate ledger entry results", "| candidate_entry_id | input | type | passed | violations |", "| --- | --- | --- | --- | --- |"]
    for item in report["candidate_ledger_entry_results"]:
        lines.append(f"| {_cell(item.get('candidate_entry_id'))} | {_cell(item.get('source_input_id'))} | {_cell(item.get('would_be_record_type'))} | {_cell(item.get('passed'))} | {_cell(item.get('violations'))} |")
    lines += ["", "## Candidate glow item results", "| candidate_glow_item_id | input | type | related_ledger | passed | violations |", "| --- | --- | --- | --- | --- | --- |"]
    for item in report["candidate_glow_item_results"]:
        lines.append(f"| {_cell(item.get('candidate_glow_item_id'))} | {_cell(item.get('source_input_id'))} | {_cell(item.get('would_be_archive_item_type'))} | {_cell(item.get('related_candidate_ledger_entry_id_seen'))} | {_cell(item.get('passed'))} | {_cell(item.get('violations'))} |")
    lines += ["", "## Source artifact map results", "| input | provided | ledger_ids | glow_ids | passed | violations |", "| --- | --- | --- | --- | --- | --- |"]
    for item in report["source_artifact_map_results"]:
        lines.append(f"| {_cell(item.get('input_id'))} | {_cell(item.get('provided'))} | {_cell(item.get('linked_candidate_ledger_entry_ids'))} | {_cell(item.get('linked_candidate_glow_item_ids'))} | {_cell(item.get('passed'))} | {_cell(item.get('violations'))} |")
    lines += ["", "## Chain/archive summary results", f"`{_cell({'chain': report['chain_summary_results'], 'archive': report['archive_summary_results']})}`"]
    lines += ["", "## SentientOS mount alignment", "| mount | alignment |", "| --- | --- |"]
    for key, value in sorted(report["sentientos_mount_alignment"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value)} |")
    lines += ["", "## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in report["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"] + [f"- **{key}:** {str(value).lower()}" for key, value in sorted(report["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)

def write_codex_workcell_memory_candidate_verifier_json(report: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_codex_workcell_memory_candidate_verifier_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
