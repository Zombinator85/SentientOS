from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_MEMORY_ACTIVATION_PREFLIGHT_ID = "codex_workcell_memory_activation_preflight.v1"
DIGEST_ALGO = "sha256"
AUTHORITY_BOUNDARY = "Activation preflight metadata only; does not activate memory, write ledger, archive glow, mutate memory, decide readiness, run commands, trigger daemon action, schedule work, create tasks, alert, train models, or establish consensus."
FORBIDDEN_INFERENCE = "Do not infer active writer permission, commit readiness, PR readiness, matrix authority, finalizer authority, PR metadata authority, ledger authority, glow authority, daemon authority, or federation consensus from this preflight."

PREREQUISITE_IDS: tuple[tuple[str, str, str, str], ...] = (
    ("memory_contract_supplied", "Memory contract supplied", "supplied_artifact", "memory contract JSON object is supplied"),
    ("candidate_bundle_supplied", "Candidate bundle supplied", "supplied_artifact", "candidate bundle JSON object is supplied"),
    ("candidate_verifier_supplied", "Candidate verifier supplied", "supplied_artifact", "candidate verifier JSON object is supplied"),
    ("memory_contract_declares_no_writer_authority", "Contract declares no writer authority", "contract_boundary", "contract non-authority posture declares no ledger/glow/memory writes"),
    ("candidate_bundle_declares_candidate_only", "Bundle declares candidate only", "candidate_boundary", "candidate bundle is candidate-only"),
    ("candidate_bundle_declares_no_ledger_write", "Bundle declares no ledger write", "candidate_boundary", "candidate bundle did not write ledger"),
    ("candidate_bundle_declares_no_glow_archive", "Bundle declares no glow archive", "candidate_boundary", "candidate bundle did not archive glow"),
    ("candidate_verifier_declares_verifier_only", "Verifier declares verifier only", "verifier_boundary", "candidate verifier is verifier-only"),
    ("candidate_verifier_declares_no_ledger_write", "Verifier declares no ledger write", "verifier_boundary", "candidate verifier did not write ledger"),
    ("candidate_verifier_declares_no_glow_archive", "Verifier declares no glow archive", "verifier_boundary", "candidate verifier did not archive glow"),
    ("candidate_verifier_status_verified", "Verifier status verified", "verifier_boundary", "verification_status is memory_candidate_bundle_verified"),
    ("candidate_verifier_no_violations", "Verifier has no violations", "verifier_boundary", "violation_count is zero"),
    ("ledger_schema_catalog_present", "Ledger schema catalog present", "schema_presence", "ledger record catalog is present"),
    ("glow_schema_catalog_present", "Glow schema catalog present", "schema_presence", "glow archive catalog is present"),
    ("source_artifact_alignment_present", "Source artifact alignment present", "traceability", "source artifact alignment is present"),
    ("candidate_ledger_entries_trace_to_inputs", "Candidate ledger entries trace to inputs", "traceability", "candidate ledger entries retain source input digests"),
    ("candidate_glow_items_trace_to_inputs", "Candidate glow items trace to inputs", "traceability", "candidate glow items retain source input digests"),
    ("future_activation_requirements_inactive", "Future activation requirements inactive", "future_activation_gap", "future requirements are future-only, unmet, and inactive"),
    ("finalizer_guard_non_bypass_declared", "Finalizer/guard non-bypass declared", "authority_boundary", "non-bypass invariant remains declared"),
    ("operator_consent_not_present", "Operator consent not present", "future_activation_gap", "explicit operator consent is absent for actual activation"),
    ("writer_implementation_not_present", "Writer implementation not present", "future_activation_gap", "active writer implementation is absent"),
    ("storage_policy_not_present", "Storage policy not present", "future_activation_gap", "storage path and retention policy are absent"),
    ("federation_consensus_not_present", "Federation consensus not present", "future_activation_gap", "federation drift consensus is absent"),
    ("vow_digest_boundary_not_present", "Vow digest boundary not present", "future_activation_gap", "vow digest constraint check is absent"),
)

FUTURE_REQUIREMENTS: tuple[str, ...] = (
    "explicit ledger writer implementation", "explicit glow archiver implementation", "explicit storage path policy", "explicit retention policy",
    "explicit digest verification policy", "explicit parent-chain validation policy", "explicit operator consent", "explicit finalizer/guard non-bypass invariant",
    "explicit pulse watcher contract", "explicit daemon action contract", "explicit federation drift consensus rule", "explicit vow digest constraint check",
    "tests proving no readiness authority", "docs marking active behavior",
)

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "memory_activation_preflight_is_read_only": True, "memory_activation_preflight_is_metadata_only": True, "memory_activation_preflight_is_preflight_only": True,
    "memory_activation_preflight_does_not_activate_memory": True, "memory_activation_preflight_does_not_write_ledger": True, "memory_activation_preflight_does_not_archive_glow": True,
    "memory_activation_preflight_does_not_modify_memory": True, "memory_activation_preflight_does_not_watch_files": True, "memory_activation_preflight_does_not_poll_state": True,
    "memory_activation_preflight_does_not_rerun_commands": True, "memory_activation_preflight_does_not_decide_readiness": True, "memory_activation_preflight_does_not_bypass_finalizer": True,
    "memory_activation_preflight_does_not_bypass_pr_metadata_guard": True, "memory_activation_preflight_does_not_authorize_commit": True, "memory_activation_preflight_does_not_authorize_pr_creation": True,
    "memory_activation_preflight_does_not_trigger_daemon": True, "memory_activation_preflight_does_not_create_tasks": True, "memory_activation_preflight_does_not_schedule_tasks": True,
    "memory_activation_preflight_does_not_send_alerts": True, "memory_activation_preflight_does_not_train_or_modify_models": True, "memory_activation_preflight_does_not_establish_federation_consensus": True,
}

class CodexWorkcellMemoryActivationPreflightError(ValueError):
    pass

def read_json_input(path_text: str | None, input_id: str) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    if path_text is None:
        return {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}, None
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellMemoryActivationPreflightError(f"missing_{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellMemoryActivationPreflightError(f"invalid_{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellMemoryActivationPreflightError(f"{input_id}_not_object:{path_text}")
    return {"provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

def _posture_true(data: Mapping[str, Any] | None, prefix: str, *names: str) -> bool:
    posture = data.get("non_authority_posture", {}) if data else {}
    return isinstance(posture, Mapping) and all(posture.get(f"{prefix}_{name}") is True for name in names)

def _future_inactive(data: Mapping[str, Any] | None) -> bool:
    future = data.get("future_activation_requirements", []) if data else []
    return isinstance(future, list) and all(isinstance(i, Mapping) and i.get("active") is False and i.get("met") is False for i in future)

def _catalog() -> list[dict[str, Any]]:
    return [{"prerequisite_id": pid, "prerequisite_name": name, "category": cat, "required_for_future_activation": True, "expected_state": exp, "forbidden_inference": FORBIDDEN_INFERENCE, "reviewer_summary": exp} for pid, name, cat, exp in PREREQUISITE_IDS]

def build_codex_workcell_memory_activation_preflight(memory_contract: Mapping[str, Any] | None, memory_contract_input_summary: Mapping[str, Any], candidate_bundle: Mapping[str, Any] | None, candidate_bundle_input_summary: Mapping[str, Any], candidate_verifier: Mapping[str, Any] | None, candidate_verifier_input_summary: Mapping[str, Any]) -> dict[str, Any]:
    ledger = memory_contract.get("ledger_receipt_chain_contract", {}) if memory_contract else {}
    glow = memory_contract.get("glow_evidence_archive_contract", {}) if memory_contract else {}
    alignment = memory_contract.get("source_artifact_alignment", []) if memory_contract else []
    entries = _as_list(candidate_bundle.get("candidate_ledger_entries") if candidate_bundle else None)
    glow_items = _as_list(candidate_bundle.get("candidate_glow_items") if candidate_bundle else None)
    vsummary = candidate_verifier.get("violation_summary", {}) if candidate_verifier else {}
    checks: dict[str, tuple[bool, str, str, str]] = {
        "memory_contract_supplied": (memory_contract is not None, str(memory_contract_input_summary.get("provided")), "memory_contract_json", "warning"),
        "candidate_bundle_supplied": (candidate_bundle is not None, str(candidate_bundle_input_summary.get("provided")), "candidate_bundle_json", "warning"),
        "candidate_verifier_supplied": (candidate_verifier is not None, str(candidate_verifier_input_summary.get("provided")), "candidate_verifier_json", "warning"),
        "memory_contract_declares_no_writer_authority": (_posture_true(memory_contract, "memory_contract", "does_not_write_ledger", "does_not_archive_glow", "does_not_modify_memory"), "contract non-authority posture inspected", "memory_contract_json", "warning"),
        "candidate_bundle_declares_candidate_only": (bool(candidate_bundle and (candidate_bundle.get("candidate_bundle_only") is True or candidate_bundle.get("candidate_only") is True)), "candidate-only flags inspected", "candidate_bundle_json", "warning"),
        "candidate_bundle_declares_no_ledger_write": (bool(candidate_bundle and candidate_bundle.get("not_ledger_writer") is True and (candidate_bundle.get("candidate_chain_summary", {}) or {}).get("no_ledger_write_performed") is True), "bundle no ledger write flags inspected", "candidate_bundle_json", "warning"),
        "candidate_bundle_declares_no_glow_archive": (bool(candidate_bundle and candidate_bundle.get("not_glow_archiver") is True and (candidate_bundle.get("candidate_archive_summary", {}) or {}).get("no_glow_archive_performed") is True), "bundle no glow archive flags inspected", "candidate_bundle_json", "warning"),
        "candidate_verifier_declares_verifier_only": (bool(candidate_verifier and candidate_verifier.get("verifier_only") is True), "verifier-only flag inspected", "candidate_verifier_json", "warning"),
        "candidate_verifier_declares_no_ledger_write": (bool(candidate_verifier and candidate_verifier.get("not_ledger_writer") is True), "verifier no ledger write flag inspected", "candidate_verifier_json", "warning"),
        "candidate_verifier_declares_no_glow_archive": (bool(candidate_verifier and candidate_verifier.get("not_glow_archiver") is True), "verifier no glow archive flag inspected", "candidate_verifier_json", "warning"),
        "candidate_verifier_status_verified": (bool(candidate_verifier and candidate_verifier.get("verification_status") == "memory_candidate_bundle_verified"), str(candidate_verifier.get("verification_status") if candidate_verifier else None), "candidate_verifier_json", "blocking_gap"),
        "candidate_verifier_no_violations": (bool(candidate_verifier and vsummary.get("violation_count") == 0), str(vsummary.get("violation_count") if candidate_verifier else None), "candidate_verifier_json", "blocking_gap"),
        "ledger_schema_catalog_present": (isinstance(ledger, Mapping) and isinstance(ledger.get("record_catalog"), list) and bool(ledger.get("record_catalog")), "ledger catalog inspected", "memory_contract_json", "warning"),
        "glow_schema_catalog_present": (isinstance(glow, Mapping) and isinstance(glow.get("archive_catalog"), list) and bool(glow.get("archive_catalog")), "glow catalog inspected", "memory_contract_json", "warning"),
        "source_artifact_alignment_present": (isinstance(alignment, list) and bool(alignment), "source alignment inspected", "memory_contract_json", "warning"),
        "candidate_ledger_entries_trace_to_inputs": (all(isinstance(e, Mapping) and e.get("source_input_id") and e.get("source_artifact_digest") for e in entries), "candidate ledger trace inspected", "candidate_bundle_json", "warning"),
        "candidate_glow_items_trace_to_inputs": (all(isinstance(g, Mapping) and g.get("source_input_id") and g.get("source_digest") for g in glow_items), "candidate glow trace inspected", "candidate_bundle_json", "warning"),
        "future_activation_requirements_inactive": (_future_inactive(candidate_bundle) and _future_inactive(candidate_verifier), "future requirements inspected as inactive", "candidate_bundle_json,candidate_verifier_json", "warning"),
        "finalizer_guard_non_bypass_declared": (NON_AUTHORITY_POSTURE["memory_activation_preflight_does_not_bypass_finalizer"] and NON_AUTHORITY_POSTURE["memory_activation_preflight_does_not_bypass_pr_metadata_guard"], "preflight non-bypass posture declared", "activation_preflight", "info"),
        "operator_consent_not_present": (False, "expected future-only gap: no operator consent", "activation_preflight", "blocking_gap"),
        "writer_implementation_not_present": (False, "expected future-only gap: no writer implementation", "activation_preflight", "blocking_gap"),
        "storage_policy_not_present": (False, "expected future-only gap: no storage policy", "activation_preflight", "blocking_gap"),
        "federation_consensus_not_present": (False, "expected future-only gap: no federation consensus", "activation_preflight", "blocking_gap"),
        "vow_digest_boundary_not_present": (False, "expected future-only gap: no vow digest boundary", "activation_preflight", "blocking_gap"),
    }
    future_gap_ids = {"operator_consent_not_present", "writer_implementation_not_present", "storage_policy_not_present", "federation_consensus_not_present", "vow_digest_boundary_not_present"}
    results = []
    for pid, _, _, _ in PREREQUISITE_IDS:
        passed, observed, source, severity_if_failed = checks[pid]
        severity = "info" if passed else severity_if_failed
        results.append({"prerequisite_id": pid, "passed": passed, "observed_state": observed, "evidence_source": source, "severity": severity, "details": "Expected blocking gap for actual activation; not a preflight failure." if pid in future_gap_ids else observed, "authority_boundary": AUTHORITY_BOUNDARY})
    omitted = memory_contract is None or candidate_bundle is None or candidate_verifier is None
    violations = candidate_verifier is not None and (vsummary.get("violation_count") not in (0, None) or candidate_verifier.get("verification_status") == "memory_candidate_bundle_failed")
    status = "activation_prerequisites_failed" if violations else ("activation_prerequisites_incomplete" if omitted else "activation_prerequisites_satisfied_for_future_design")
    blocking = [r["prerequisite_id"] for r in results if r["severity"] == "blocking_gap"]
    return {
        "memory_activation_preflight_id": WORKCELL_MEMORY_ACTIVATION_PREFLIGHT_ID, "metadata_only": True, "preflight_only": True, "activation_not_performed": True,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {"memory_contract_json": dict(memory_contract_input_summary), "candidate_bundle_json": dict(candidate_bundle_input_summary), "candidate_verifier_json": dict(candidate_verifier_input_summary)},
        "memory_contract_summary": {"provided": memory_contract is not None, "workcell_memory_contract_id": memory_contract.get("workcell_memory_contract_id") if memory_contract else None, "ledger_record_catalog_count": len(ledger.get("record_catalog", [])) if isinstance(ledger, Mapping) else None, "glow_archive_catalog_count": len(glow.get("archive_catalog", [])) if isinstance(glow, Mapping) else None, "non_authority_posture_present": isinstance(memory_contract.get("non_authority_posture") if memory_contract else None, Mapping), "non_authority_posture_true": _posture_true(memory_contract, "memory_contract", "does_not_write_ledger", "does_not_archive_glow", "does_not_modify_memory")},
        "candidate_bundle_summary": {"provided": candidate_bundle is not None, "memory_candidate_bundle_id": candidate_bundle.get("memory_candidate_bundle_id") if candidate_bundle else None, "candidate_ledger_entry_count": len(entries), "candidate_glow_item_count": len(glow_items), "candidate_only_seen": bool(candidate_bundle and (candidate_bundle.get("candidate_bundle_only") is True or candidate_bundle.get("candidate_only") is True)), "no_ledger_write_seen": checks["candidate_bundle_declares_no_ledger_write"][0], "no_glow_archive_seen": checks["candidate_bundle_declares_no_glow_archive"][0]},
        "candidate_verifier_summary": {"provided": candidate_verifier is not None, "memory_candidate_verifier_id": candidate_verifier.get("memory_candidate_verifier_id") if candidate_verifier else None, "verification_status": candidate_verifier.get("verification_status") if candidate_verifier else None, "violation_count": vsummary.get("violation_count") if candidate_verifier else None, "warning_count": vsummary.get("warning_count") if candidate_verifier else None, "verifier_only_seen": bool(candidate_verifier and candidate_verifier.get("verifier_only") is True), "no_ledger_write_seen": bool(candidate_verifier and candidate_verifier.get("not_ledger_writer") is True), "no_glow_archive_seen": bool(candidate_verifier and candidate_verifier.get("not_glow_archiver") is True)},
        "activation_prerequisite_catalog": _catalog(), "activation_prerequisite_results": results,
        "activation_gap_summary": {"blocking_gap_count": len(blocking), "warning_count": sum(1 for r in results if r["severity"] == "warning"), "info_count": sum(1 for r in results if r["severity"] == "info"), "blocking_gap_ids": blocking, "activation_not_performed": True, "future_writer_requirements_unmet": True},
        "activation_preflight_status": status,
        "sentientos_mount_alignment": {"/ledger": "preflight only; no ledger write", "/glow": "preflight only; no archive write", "/pulse": "future consumer of stored history; inactive here", "/daemon": "future consumer of pulse/recommendation context; inactive here", "/vow": "canonical constraints bounding activation interpretation and forbidden inference"},
        "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")

def render_codex_workcell_memory_activation_preflight_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Memory Activation Preflight", "", "Deterministic metadata-only activation preflight. It does not activate memory, write /ledger, archive /glow, decide readiness, or authorize daemon/PR/commit action.", "", "## Input summaries", "| input | provided | digest | byte_size |", "| --- | --- | --- | --- |"]
    for key, value in sorted(report["input_summaries"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value.get('provided'))} | {_cell(value.get('digest'))} | {_cell(value.get('byte_size'))} |")
    for title, key in (("Memory contract summary", "memory_contract_summary"), ("Candidate bundle summary", "candidate_bundle_summary"), ("Candidate verifier summary", "candidate_verifier_summary")):
        lines += ["", f"## {title}", f"`{_cell(report[key])}`"]
    lines += ["", "## Activation prerequisite results", "| prerequisite_id | passed | severity | observed_state |", "| --- | --- | --- | --- |"]
    for item in report["activation_prerequisite_results"]:
        lines.append(f"| {_cell(item['prerequisite_id'])} | {_cell(item['passed'])} | {_cell(item['severity'])} | {_cell(item['observed_state'])} |")
    lines += ["", "## Activation gap summary", f"`{_cell(report['activation_gap_summary'])}`", "", "## Activation preflight status", f"`{_cell(report['activation_preflight_status'])}`", "", "## SentientOS mount alignment", "| mount | alignment |", "| --- | --- |"]
    for key, value in sorted(report["sentientos_mount_alignment"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value)} |")
    lines += ["", "## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in report["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"] + [f"- **{key}:** {str(value).lower()}" for key, value in sorted(report["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)

def write_codex_workcell_memory_activation_preflight_json(report: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_codex_workcell_memory_activation_preflight_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
