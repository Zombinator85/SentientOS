from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_VOW_ALIGNMENT_ATTESTATION_ID = "codex_workcell_vow_alignment_attestation.v1"
DIGEST_ALGO = "sha256"

INPUT_IDS: tuple[str, ...] = (
    "architecture_json", "health_snapshot_json", "pulse_contract_json", "daemon_recommendation_contract_json",
    "memory_contract_json", "memory_candidate_bundle_json", "memory_candidate_verifier_json", "memory_activation_preflight_json",
)

CONSTRAINT_MAP: dict[str, tuple[str, ...]] = {
    "architecture_json": ("reports_do_not_create_runtime_authority", "no_runtime_or_host_action_without_explicit_boundary", "no_backdoor_or_hidden_authority"),
    "health_snapshot_json": ("health_snapshots_are_not_decisions", "reports_do_not_create_runtime_authority"),
    "pulse_contract_json": ("pulse_signals_are_not_actions", "reports_do_not_create_runtime_authority"),
    "daemon_recommendation_contract_json": ("recommendations_are_not_commands", "daemon_must_not_self_authorize", "reports_do_not_create_runtime_authority"),
    "memory_contract_json": ("ledger_schema_is_not_ledger_write", "glow_schema_is_not_glow_archive", "storage_policy_required_for_memory_writes", "reports_do_not_create_runtime_authority"),
    "memory_candidate_bundle_json": ("memory_candidates_are_not_writes", "ledger_schema_is_not_ledger_write", "glow_schema_is_not_glow_archive", "reports_do_not_create_runtime_authority"),
    "memory_candidate_verifier_json": ("memory_verification_is_not_readiness", "reports_do_not_create_runtime_authority"),
    "memory_activation_preflight_json": ("activation_preflight_is_not_activation", "vow_digest_required_for_future_active_writers", "operator_consent_required_for_active_watchers_or_daemons", "reports_do_not_create_runtime_authority"),
}

FORBIDDEN_MAP: dict[str, tuple[str, ...]] = {
    "architecture_json": ("architecture_map_implies_runtime_authority",),
    "health_snapshot_json": ("health_snapshot_implies_readiness",),
    "pulse_contract_json": ("pulse_contract_implies_action",),
    "daemon_recommendation_contract_json": ("daemon_recommendation_implies_command",),
    "memory_contract_json": ("memory_contract_implies_storage_write",),
    "memory_candidate_bundle_json": ("memory_candidate_bundle_implies_ledger_write", "memory_candidate_bundle_implies_glow_archive"),
    "memory_candidate_verifier_json": ("memory_candidate_verifier_implies_readiness",),
    "memory_activation_preflight_json": ("memory_activation_preflight_implies_activation",),
}

FUTURE_REQUIREMENTS: tuple[str, ...] = (
    "explicit vow digest adoption policy", "explicit ledger writer implementation", "explicit glow archiver implementation",
    "explicit storage path policy", "explicit retention policy", "explicit digest verification policy", "explicit parent-chain validation policy",
    "explicit operator consent", "explicit finalizer/guard non-bypass invariant", "explicit pulse watcher contract", "explicit daemon action contract",
    "explicit federation drift consensus rule", "tests proving no readiness authority", "docs marking active behavior",
)

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "vow_alignment_attestation_is_read_only": True,
    "vow_alignment_attestation_is_metadata_only": True,
    "vow_alignment_attestation_is_attestation_only": True,
    "vow_alignment_attestation_does_not_activate_memory": True,
    "vow_alignment_attestation_does_not_write_ledger": True,
    "vow_alignment_attestation_does_not_archive_glow": True,
    "vow_alignment_attestation_does_not_modify_memory": True,
    "vow_alignment_attestation_does_not_watch_files": True,
    "vow_alignment_attestation_does_not_poll_state": True,
    "vow_alignment_attestation_does_not_rerun_commands": True,
    "vow_alignment_attestation_does_not_decide_readiness": True,
    "vow_alignment_attestation_does_not_bypass_finalizer": True,
    "vow_alignment_attestation_does_not_bypass_pr_metadata_guard": True,
    "vow_alignment_attestation_does_not_authorize_commit": True,
    "vow_alignment_attestation_does_not_authorize_pr_creation": True,
    "vow_alignment_attestation_does_not_trigger_daemon": True,
    "vow_alignment_attestation_does_not_create_tasks": True,
    "vow_alignment_attestation_does_not_schedule_tasks": True,
    "vow_alignment_attestation_does_not_send_alerts": True,
    "vow_alignment_attestation_does_not_train_or_modify_models": True,
    "vow_alignment_attestation_does_not_establish_federation_consensus": True,
}

ACTIVE_AUTHORITY_KEYS = {
    "active_writer", "active_daemon", "active_scheduler", "active_task_creator", "active_alerting",
    "active_federation_consensus", "commit_authority", "pr_authority", "PR_authority", "finalizer_bypass", "pr_metadata_guard_bypass",
    "memory_writer", "ledger_writer", "glow_archiver", "watcher", "scheduler", "executor", "daemon_action", "task_creator", "alerting_system",
    "model_training", "reinforcement_learning", "runtime_authority", "federation_consensus",
}

class CodexWorkcellVowAlignmentAttestationError(ValueError):
    pass


def _omitted(input_id: str) -> dict[str, Any]:
    return {"input_id": input_id, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}


def read_json_input(path_text: str | None, input_id: str, *, required: bool = False) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not path_text:
        if required:
            raise CodexWorkcellVowAlignmentAttestationError(f"missing_required_{input_id}")
        return _omitted(input_id), None
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellVowAlignmentAttestationError(f"missing_json:{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellVowAlignmentAttestationError(f"invalid_json:{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise CodexWorkcellVowAlignmentAttestationError(f"json_not_object:{input_id}:{path_text}")
    return {"input_id": input_id, "provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded


def _detected_report_id(data: Mapping[str, Any]) -> Any:
    for key in sorted(data):
        if key.endswith("_id") or key in {"doctor_report_id", "workcell_memory_contract_id"}:
            return data.get(key)
    return None


def _posture(data: Mapping[str, Any]) -> tuple[bool, bool | None]:
    posture = data.get("non_authority_posture")
    if not isinstance(posture, Mapping):
        return False, None
    return True, all(value is True for value in posture.values())


def _active_authority(data: Mapping[str, Any]) -> bool:
    for key, value in data.items():
        key_lower = key.lower()
        if value is True and (key in ACTIVE_AUTHORITY_KEYS or key_lower in ACTIVE_AUTHORITY_KEYS or key_lower.startswith("active_") or key_lower.endswith("_authority")):
            return True
        if key_lower.startswith("not_") and value is False:
            return True
    present, all_true = _posture(data)
    return bool(present and all_true is False)


def _contract_summary(summary: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    posture_present, posture_all_true = _posture(contract)
    constraints = contract.get("canonical_vow_constraints")
    inferences = contract.get("forbidden_inference_catalog")
    return {
        "provided": True,
        "vow_boundary_contract_id": contract.get("vow_boundary_contract_id"),
        "canonical_vow_digest": contract.get("canonical_vow_digest"),
        "canonical_vow_digest_algo": contract.get("canonical_vow_digest_algo"),
        "canonical_constraint_count": len(constraints) if isinstance(constraints, list) else None,
        "forbidden_inference_count": len(inferences) if isinstance(inferences, list) else None,
        "non_authority_posture_present": posture_present,
        "non_authority_posture_all_true": posture_all_true,
        "source_digest": summary.get("digest"),
        "source_digest_algo": summary.get("digest_algo"),
        "source_byte_size": summary.get("byte_size"),
    }


def _record(input_id: str, summary: Mapping[str, Any], data: Mapping[str, Any], digest: Any, algo: Any) -> dict[str, Any]:
    warnings: list[str] = []
    violations: list[str] = []
    metadata_seen = data.get("metadata_only")
    posture_present, posture_all_true = _posture(data)
    if metadata_seen is False:
        violations.append("metadata_only_false")
    elif metadata_seen is not True:
        warnings.append("metadata_only_missing")
    if not posture_present:
        warnings.append("non_authority_posture_missing")
    elif posture_all_true is False:
        violations.append("non_authority_posture_false")
    active = _active_authority(data)
    if active:
        violations.append("active_authority_detected")
    if not digest:
        violations.append("canonical_vow_digest_missing")
    status = "failed" if violations else ("warning" if warnings else "attested")
    return {
        "attestation_id": f"{WORKCELL_VOW_ALIGNMENT_ATTESTATION_ID}:{input_id}",
        "input_id": input_id,
        "supplied": True,
        "source_digest": summary.get("digest"),
        "source_digest_algo": summary.get("digest_algo"),
        "source_byte_size": summary.get("byte_size"),
        "detected_report_id": _detected_report_id(data),
        "canonical_vow_digest": digest,
        "canonical_vow_digest_algo": algo,
        "applicable_constraint_ids": list(CONSTRAINT_MAP[input_id]),
        "applicable_forbidden_inference_ids": list(FORBIDDEN_MAP[input_id]),
        "metadata_only_seen": metadata_seen,
        "non_authority_posture_present": posture_present,
        "non_authority_posture_all_true": posture_all_true,
        "active_authority_detected": active,
        "alignment_status": status,
        "warnings": warnings,
        "violations": violations,
        "forbidden_inference_boundary": "Forbidden inference IDs remain false review boundaries; they are not readiness or activation authority.",
        "authority_boundary": "Attestation does not activate memory, write ledger/glow, trigger daemons, schedule tasks, authorize commit, or authorize PR metadata.",
        "no_action_taken": True,
    }


def build_codex_workcell_vow_alignment_attestation(vow_boundary_contract: tuple[Mapping[str, Any], Mapping[str, Any]], inputs: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any] | None]] | None = None) -> dict[str, Any]:
    vow_summary, vow_data = vow_boundary_contract
    contract_summary = _contract_summary(vow_summary, vow_data)
    canonical_digest = vow_data.get("canonical_vow_digest")
    canonical_algo = vow_data.get("canonical_vow_digest_algo", DIGEST_ALGO)
    normalized = {input_id: (dict(inputs[input_id][0]), inputs[input_id][1]) if inputs and input_id in inputs else (_omitted(input_id), None) for input_id in INPUT_IDS}
    records = [_record(input_id, summary, data, canonical_digest, canonical_algo) for input_id, (summary, data) in sorted(normalized.items()) if summary.get("provided") and data is not None]
    applicable_constraints = sorted({cid for rec in records for cid in rec["applicable_constraint_ids"]})
    applicable_inferences = sorted({iid for rec in records for iid in rec["applicable_forbidden_inference_ids"]})
    canonical_constraints_raw = vow_data.get("canonical_vow_constraints")
    canonical_constraints: list[Any] = canonical_constraints_raw if isinstance(canonical_constraints_raw, list) else []
    canonical_constraint_ids = {str(item.get("constraint_id")) for item in canonical_constraints if isinstance(item, Mapping) and item.get("constraint_id")}
    catalog_raw = vow_data.get("forbidden_inference_catalog")
    catalog: list[Any] = catalog_raw if isinstance(catalog_raw, list) else []
    catalog_ids = {str(item.get("inference_id")) for item in catalog if isinstance(item, Mapping) and item.get("inference_id")}
    return {
        "vow_alignment_attestation_id": WORKCELL_VOW_ALIGNMENT_ATTESTATION_ID,
        "metadata_only": True, "attestation_bundle_only": True,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True, "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True, "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": {key: dict(value[0]) for key, value in sorted(normalized.items())},
        "vow_boundary_contract_summary": contract_summary,
        "canonical_vow_digest": canonical_digest,
        "canonical_vow_digest_algo": canonical_algo,
        "attestation_records": records,
        "constraint_coverage_summary": {"supplied_report_count": len(records), "attested_report_count": sum(r["alignment_status"] == "attested" for r in records), "warning_report_count": sum(r["alignment_status"] == "warning" for r in records), "failed_report_count": sum(r["alignment_status"] == "failed" for r in records), "canonical_constraint_count": len(canonical_constraints) if canonical_constraints else None, "applicable_constraint_count": len(applicable_constraints), "applicable_constraint_ids": applicable_constraints, "missing_expected_constraint_ids": sorted(set(applicable_constraints) - canonical_constraint_ids) if canonical_constraint_ids else [], "canonical_vow_digest": canonical_digest, "no_action_taken": True},
        "forbidden_inference_coverage_summary": {"forbidden_inference_count": len(catalog) if catalog else None, "applicable_forbidden_inference_count": len(applicable_inferences), "applicable_forbidden_inference_ids": applicable_inferences, "missing_expected_forbidden_inference_ids": sorted(set(applicable_inferences) - catalog_ids) if catalog_ids else [], "no_action_taken": True},
        "attestation_gap_summary": {"failed_attestation_count": sum(r["alignment_status"] == "failed" for r in records), "warning_attestation_count": sum(r["alignment_status"] == "warning" for r in records), "failed_input_ids": [r["input_id"] for r in records if r["alignment_status"] == "failed"], "warning_input_ids": [r["input_id"] for r in records if r["alignment_status"] == "warning"], "active_authority_detected": any(r["active_authority_detected"] for r in records), "vow_alignment_attestation_only": True, "no_action_taken": True, "not_readiness_authority": True},
        "sentientos_mount_alignment": {"/vow": "canonical digest binding and forbidden inference attestation", "/ledger": "future consumer of vow-bounded write policy; inactive here", "/glow": "future consumer of vow-bounded archive policy; inactive here", "/pulse": "future consumer of vow-bounded observation history; inactive here", "/daemon": "future consumer of vow-bounded recommendation context; inactive here"},
        "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }


def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def render_codex_workcell_vow_alignment_attestation_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Vow Alignment Attestation Bundle", "", "Deterministic metadata-only attestation. It binds supplied report bytes to a supplied canonical vow digest but does not decide readiness, activate memory, write /ledger, archive /glow, run commands, trigger daemons, create tasks, schedule work, or authorize commits/PR metadata.", "", f"Canonical vow digest: `{_cell(report.get('canonical_vow_digest'))}`", "", "## Vow boundary contract summary", f"`{_cell(report['vow_boundary_contract_summary'])}`", "", "## Input summaries", "| input | provided | path | digest | byte_size |", "| --- | --- | --- | --- | --- |"]
    for key, value in sorted(report["input_summaries"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value.get('provided'))} | {_cell(value.get('path'))} | {_cell(value.get('digest'))} | {_cell(value.get('byte_size'))} |")
    lines += ["", "## Attestation records", "| input | status | report_id | constraints | forbidden inferences | warnings | violations |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for item in report["attestation_records"]:
        lines.append(f"| {_cell(item['input_id'])} | {_cell(item['alignment_status'])} | {_cell(item['detected_report_id'])} | {_cell(item['applicable_constraint_ids'])} | {_cell(item['applicable_forbidden_inference_ids'])} | {_cell(item['warnings'])} | {_cell(item['violations'])} |")
    for title, key in (("Constraint coverage summary", "constraint_coverage_summary"), ("Forbidden inference coverage summary", "forbidden_inference_coverage_summary"), ("Attestation gap summary", "attestation_gap_summary")):
        lines += ["", f"## {title}", f"`{_cell(report[key])}`"]
    lines += ["", "## SentientOS mount alignment", "| mount | alignment |", "| --- | --- |"]
    for key, value in sorted(report["sentientos_mount_alignment"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value)} |")
    lines += ["", "## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in report["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"] + [f"- **{key}:** {str(value).lower()}" for key, value in sorted(report["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)


def write_codex_workcell_vow_alignment_attestation_json(report: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_codex_workcell_vow_alignment_attestation_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
