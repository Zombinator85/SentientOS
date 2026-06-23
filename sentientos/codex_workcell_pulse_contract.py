from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

PULSE_CONTRACT_ID = "codex_workcell_pulse_contract.v1"
DIGEST_ALGO = "sha256"
CATEGORIES: tuple[str, ...] = (
    "missing_input",
    "proof_pressure",
    "authority_pressure",
    "freshness_pressure",
    "provenance_pressure",
    "doctrine_pressure",
    "future_integration_pressure",
    "daemon_boundary",
    "federation_boundary",
)
SEVERITY_HINTS: tuple[str, ...] = ("info", "watch", "caution", "blocked_observation")

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "pulse_contract_is_read_only": True,
    "pulse_contract_is_metadata_only": True,
    "pulse_contract_does_not_watch_files": True,
    "pulse_contract_does_not_poll_state": True,
    "pulse_contract_does_not_rerun_commands": True,
    "pulse_contract_does_not_decide_readiness": True,
    "pulse_contract_does_not_bypass_finalizer": True,
    "pulse_contract_does_not_bypass_pr_metadata_guard": True,
    "pulse_contract_does_not_authorize_commit": True,
    "pulse_contract_does_not_authorize_pr_creation": True,
    "pulse_contract_does_not_trigger_daemon": True,
    "pulse_contract_does_not_schedule_tasks": True,
    "pulse_contract_does_not_send_alerts": True,
    "pulse_contract_does_not_train_or_modify_models": True,
    "pulse_contract_does_not_establish_federation_consensus": True,
}

FUTURE_ACTIVATION_REQUIREMENTS: tuple[str, ...] = (
    "explicit separate implementation",
    "explicit scheduler/watch loop",
    "explicit operator consent",
    "explicit daemon boundary",
    "explicit ledger/glow storage policy",
    "explicit federation drift consensus rule",
    "explicit finalizer/guard non-bypass invariant",
    "tests proving no readiness authority",
    "docs marking active behavior",
)

_SIGNAL_SPECS: tuple[tuple[str, str, str, str, tuple[str, ...], str], ...] = (
    ("missing_architecture_map", "Missing architecture map", "missing_input", "watch", ("missing_inputs", "observed_pressure_signals"), "Architecture map metadata was not supplied."),
    ("missing_matrix_evidence", "Missing matrix evidence", "missing_input", "caution", ("missing_inputs",), "Matrix evidence metadata was not supplied."),
    ("missing_finalizer_evidence", "Missing finalizer evidence", "missing_input", "caution", ("missing_inputs", "authority_summary"), "Finalizer evidence metadata was not supplied."),
    ("missing_pr_metadata_guard_evidence", "Missing PR metadata guard evidence", "missing_input", "caution", ("missing_inputs", "authority_summary"), "PR metadata guard evidence metadata was not supplied."),
    ("missing_evidence_index", "Missing evidence index", "missing_input", "watch", ("missing_inputs", "evidence_summary"), "Evidence index metadata was not supplied."),
    ("missing_lifecycle_doctor", "Missing lifecycle doctor", "missing_input", "watch", ("missing_inputs", "evidence_summary"), "Lifecycle doctor metadata was not supplied."),
    ("missing_appendix_sidecar", "Missing appendix sidecar", "provenance_pressure", "watch", ("missing_inputs", "provenance_summary"), "Evidence appendix sidecar provenance was not supplied."),
    ("missing_doctrine_map", "Missing doctrine map", "doctrine_pressure", "watch", ("missing_inputs", "doctrine_summary"), "Doctrine map metadata was not supplied."),
    ("matrix_required_failure_observed", "Matrix required failure observed", "proof_pressure", "blocked_observation", ("proof_summary.required_failure_count", "observed_pressure_signals"), "Required matrix failure was observed in supplied metadata."),
    ("matrix_diagnostic_failure_observed", "Matrix diagnostic failure observed", "proof_pressure", "watch", ("proof_summary.diagnostic_failure_count", "observed_pressure_signals"), "Diagnostic matrix failure was observed as non-authority evidence."),
    ("finalizer_rerun_required_observed", "Finalizer rerun required observed", "authority_pressure", "caution", ("authority_summary", "observed_pressure_signals"), "Finalizer metadata reported rerun pressure."),
    ("stale_evidence_refresh_observed", "Stale evidence refresh observed", "freshness_pressure", "caution", ("authority_summary", "observed_pressure_signals"), "Finalizer metadata reported terminal refresh or stale evidence pressure."),
    ("generated_artifact_cleanup_incomplete_observed", "Generated artifact cleanup incomplete observed", "freshness_pressure", "caution", ("authority_summary", "observed_pressure_signals"), "Generated artifact cleanup pressure was observed in supplied metadata."),
    ("authority_status_absent", "Authority status absent", "authority_pressure", "watch", ("authority_summary",), "Authority status fields were absent from supplied metadata."),
    ("provenance_absent", "Provenance absent", "provenance_pressure", "watch", ("provenance_summary", "missing_inputs"), "Provenance context was absent or incomplete."),
    ("doctrine_context_absent", "Doctrine context absent", "doctrine_pressure", "watch", ("doctrine_summary", "missing_inputs"), "Doctrine context was absent or incomplete."),
    ("future_integration_unwired", "Future integration unwired", "future_integration_pressure", "info", ("future_integration_snapshot",), "Future integration surface remains metadata-only and unwired."),
    ("federation_consensus_absent", "Federation consensus absent", "federation_boundary", "info", ("future_integration_snapshot",), "No federation consensus is established by this contract."),
    ("daemon_repair_not_active", "Daemon repair not active", "daemon_boundary", "info", ("future_integration_snapshot",), "Daemon repair is not active in this contract."),
    ("pulse_watch_not_active", "Pulse watch not active", "future_integration_pressure", "info", ("future_integration_snapshot",), "Pulse watch behavior is not active in this contract."),
)

MISSING_INPUT_MAP = {
    "architecture_json": "missing_architecture_map",
    "matrix_json": "missing_matrix_evidence",
    "pre_commit_finalizer_json": "missing_finalizer_evidence",
    "pr_metadata_finalizer_json": "missing_finalizer_evidence",
    "pr_metadata_guard_json": "missing_pr_metadata_guard_evidence",
    "evidence_index_json": "missing_evidence_index",
    "lifecycle_doctor_json": "missing_lifecycle_doctor",
    "evidence_appendix_sidecar_json": "missing_appendix_sidecar",
    "beneficial_trait_doctrine_json": "missing_doctrine_map",
}
PRESSURE_SIGNAL_MAP = {
    "absent_architecture_map": "missing_architecture_map",
    "matrix_required_failures": "matrix_required_failure_observed",
    "diagnostic_failures_nonproof": "matrix_diagnostic_failure_observed",
    "finalizer_rerun_required": "finalizer_rerun_required_observed",
    "stale_evidence_refresh_status": "stale_evidence_refresh_observed",
    "absent_provenance_sidecar": "provenance_absent",
    "absent_doctrine_map": "doctrine_context_absent",
}

class CodexWorkcellPulseContractError(ValueError):
    pass

@dataclass(frozen=True)
class CodexWorkcellPulseContractRequest:
    health_snapshot_json: str | None = None


def _signal_catalog() -> list[dict[str, Any]]:
    catalog = []
    for signal_id, signal_name, category, severity, fields, interpretation in _SIGNAL_SPECS:
        catalog.append({
            "signal_id": signal_id,
            "signal_name": signal_name,
            "category": category,
            "severity_hint": severity,
            "source_health_snapshot_fields": list(fields),
            "interpretation": interpretation,
            "forbidden_inference": "Does not decide readiness, authorize commit or PR metadata, trigger daemon action, schedule tasks, send alerts, or establish federation consensus.",
            "next_observation_recommendation": "Review supplied metadata evidence only; any active behavior requires a separate future implementation and operator authority.",
            "non_authority_boundary": "Observation-only catalog entry; no runtime authority is granted.",
            "reviewer_summary": f"{signal_name} is classified as {category} with {severity} severity hint.",
        })
    return catalog


def _index(catalog: list[dict[str, Any]], key: str, values: tuple[str, ...]) -> dict[str, list[str]]:
    return {value: sorted(str(item["signal_id"]) for item in catalog if item[key] == value) for value in values}


def _load_health_snapshot(path_text: str | None) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    if path_text is None:
        return {"provided": False, "path": None, "digest": None, "byte_size": None}, None
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellPulseContractError(f"missing_health_snapshot_json:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellPulseContractError(f"invalid_health_snapshot_json:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellPulseContractError(f"health_snapshot_json_not_object:{path_text}")
    summary: dict[str, Any] = {"provided": True, "path": path_text, "readable_json": True, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw)}
    if "workcell_health_snapshot_id" in loaded:
        summary["workcell_health_snapshot_id"] = loaded["workcell_health_snapshot_id"]
    pressure = loaded.get("observed_pressure_signals")
    if isinstance(pressure, list):
        summary["observed_pressure_signal_count"] = len(pressure)
    missing = loaded.get("missing_inputs")
    if isinstance(missing, list):
        summary["missing_inputs_count"] = len(missing)
    return summary, loaded


def _observed_summary(snapshot: Mapping[str, Any] | None, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    if snapshot is None:
        return {"provided": False, "observation_only": True}
    known_ids = {str(item["signal_id"]) for item in catalog}
    observed: set[str] = set()
    unmatched: list[Any] = []
    missing = snapshot.get("missing_inputs")
    if isinstance(missing, list):
        for item in missing:
            mapped = MISSING_INPUT_MAP.get(str(item))
            if mapped:
                observed.add(mapped)
    pressure = snapshot.get("observed_pressure_signals")
    if isinstance(pressure, list):
        for item in pressure:
            signal = item.get("signal") if isinstance(item, Mapping) else item
            mapped = PRESSURE_SIGNAL_MAP.get(str(signal))
            if mapped:
                observed.add(mapped)
            else:
                unmatched.append(item)
    proof = snapshot.get("proof_summary")
    if isinstance(proof, Mapping):
        if proof.get("required_failure_count"):
            observed.add("matrix_required_failure_observed")
        if proof.get("diagnostic_failure_count"):
            observed.add("matrix_diagnostic_failure_observed")
    authority = snapshot.get("authority_summary")
    if isinstance(authority, Mapping):
        statuses = [authority.get("pre_commit_finalizer_status"), authority.get("pr_metadata_finalizer_status"), authority.get("pr_metadata_guard_status")]
        if not any(isinstance(status, str) and status for status in statuses):
            observed.add("authority_status_absent")
        if authority.get("pre_commit_rerun_required") or authority.get("pr_metadata_rerun_required"):
            observed.add("finalizer_rerun_required_observed")
        if authority.get("pre_commit_terminal_refresh_status") or authority.get("pr_metadata_terminal_refresh_status"):
            observed.add("stale_evidence_refresh_observed")
    doctrine = snapshot.get("doctrine_summary")
    if isinstance(doctrine, Mapping) and doctrine.get("provided") is False:
        observed.add("doctrine_context_absent")
    provenance = snapshot.get("provenance_summary")
    if isinstance(provenance, Mapping) and not provenance.get("appendix_provenance_digest_version"):
        observed.add("provenance_absent")
    for item in snapshot.get("future_integration_snapshot", []) if isinstance(snapshot.get("future_integration_snapshot"), list) else []:
        if isinstance(item, Mapping) and item.get("active_authority") is False:
            observed.add("future_integration_unwired")
            if "daemon" in str(item.get("integration", "")):
                observed.add("daemon_repair_not_active")
            if "federation" in str(item.get("integration", "")):
                observed.add("federation_consensus_absent")
            if "pulse" in str(item.get("integration", "")):
                observed.add("pulse_watch_not_active")
    catalog_by_id = {str(item["signal_id"]): item for item in catalog}
    observed_ids = sorted(observed & known_ids)
    return {
        "observed_signal_ids": observed_ids,
        "unmatched_health_snapshot_pressure_signals": unmatched,
        "missing_contract_signal_ids": sorted(observed - known_ids),
        "observed_categories": sorted({str(catalog_by_id[s]["category"]) for s in observed_ids}),
        "observed_severity_hints": sorted({str(catalog_by_id[s]["severity_hint"]) for s in observed_ids}),
        "observation_only": True,
    }


def build_codex_workcell_pulse_contract(request: CodexWorkcellPulseContractRequest | None = None) -> dict[str, Any]:
    request = request or CodexWorkcellPulseContractRequest()
    catalog = _signal_catalog()
    health_summary, snapshot = _load_health_snapshot(request.health_snapshot_json)
    return {
        "pulse_contract_id": PULSE_CONTRACT_ID,
        "metadata_only": True,
        "pulse_contract_only": True,
        "not_runtime_authority": True,
        "not_watcher": True,
        "not_scheduler": True,
        "not_executor": True,
        "not_daemon_action": True,
        "not_alerting_system": True,
        "not_model_training": True,
        "not_reinforcement_learning": True,
        "signal_catalog": catalog,
        "category_index": _index(catalog, "category", CATEGORIES),
        "severity_index": _index(catalog, "severity_hint", SEVERITY_HINTS),
        "health_snapshot_input_summary": health_summary,
        "observed_signal_summary": _observed_summary(snapshot, catalog),
        "sentientos_mount_alignment": {
            "/pulse": "Pressure signal naming and freshness/drift/timeout/rerun observation only.",
            "/glow": "Archived evidence and review surfaces may provide observation context only.",
            "/ledger": "Landed receipts may provide history context only.",
            "/daemon": "Future repair recommendation consumer; not active here.",
            "/vow": "Canonical constraints bound interpretation and forbidden inference.",
        },
        "future_activation_requirements": [{"requirement": item, "status": "future_only", "met": False, "active": False} for item in FUTURE_ACTIVATION_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }


def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\\r\\n", "<br>").replace("\\n", "<br>").replace("\\r", "<br>").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def render_codex_workcell_pulse_contract_markdown(contract: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Pulse Contract", "", "This is a read-only pulse signal catalog. It names and bounds observed pressure signals from supplied metadata only; it does not watch files, schedule tasks, trigger daemons, send alerts, decide readiness, authorize commits, authorize PR metadata, or establish federation consensus.", "", "## Health snapshot input summary", "| key | value |", "| --- | --- |"]
    for key, value in sorted(contract["health_snapshot_input_summary"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value)} |")
    lines += ["", "## Signal catalog", "| signal_id | signal_name | category | severity_hint | source_health_snapshot_fields | reviewer_summary |", "| --- | --- | --- | --- | --- | --- |"]
    for signal in contract["signal_catalog"]:
        lines.append(f"| {_cell(signal['signal_id'])} | {_cell(signal['signal_name'])} | {_cell(signal['category'])} | {_cell(signal['severity_hint'])} | {_cell(signal['source_health_snapshot_fields'])} | {_cell(signal['reviewer_summary'])} |")
    if contract["health_snapshot_input_summary"].get("provided"):
        lines += ["", "## Observed signal summary", "| key | value |", "| --- | --- |"]
        for key, value in sorted(contract["observed_signal_summary"].items()):
            lines.append(f"| {_cell(key)} | {_cell(value)} |")
    for title, key in (("Category index", "category_index"), ("Severity index", "severity_index"), ("SentientOS mount alignment", "sentientos_mount_alignment")):
        lines += ["", f"## {title}", "| key | value |", "| --- | --- |"]
        for item_key, value in sorted(contract[key].items()):
            lines.append(f"| {_cell(item_key)} | {_cell(value)} |")
    lines += ["", "## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in contract["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"] + [f"- **{key}:** {str(value).lower()}" for key, value in sorted(contract["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)


def write_codex_workcell_pulse_contract_json(contract: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_codex_workcell_pulse_contract_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
