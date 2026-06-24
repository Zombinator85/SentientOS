from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sentientos.codex_workcell_pulse_contract import CATEGORIES as PULSE_CATEGORIES
from sentientos.codex_workcell_pulse_contract import SEVERITY_HINTS as PULSE_SEVERITY_HINTS
from sentientos.codex_workcell_pulse_contract import _signal_catalog

DAEMON_RECOMMENDATION_CONTRACT_ID = "codex_workcell_daemon_recommendation_contract.v1"
DIGEST_ALGO = "sha256"
RECOMMENDATION_TYPES: tuple[str, ...] = (
    "provide_missing_evidence",
    "inspect_proof_pressure",
    "inspect_authority_pressure",
    "inspect_freshness_pressure",
    "inspect_provenance_pressure",
    "inspect_doctrine_pressure",
    "document_future_integration",
    "preserve_boundary",
    "require_future_contract",
)
SEVERITY_FLOORS: tuple[str, ...] = ("info", "watch", "caution", "blocked_observation")

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "daemon_recommendation_contract_is_read_only": True,
    "daemon_recommendation_contract_is_metadata_only": True,
    "daemon_recommendation_contract_does_not_watch_files": True,
    "daemon_recommendation_contract_does_not_poll_state": True,
    "daemon_recommendation_contract_does_not_rerun_commands": True,
    "daemon_recommendation_contract_does_not_decide_readiness": True,
    "daemon_recommendation_contract_does_not_bypass_finalizer": True,
    "daemon_recommendation_contract_does_not_bypass_pr_metadata_guard": True,
    "daemon_recommendation_contract_does_not_authorize_commit": True,
    "daemon_recommendation_contract_does_not_authorize_pr_creation": True,
    "daemon_recommendation_contract_does_not_trigger_daemon": True,
    "daemon_recommendation_contract_does_not_create_tasks": True,
    "daemon_recommendation_contract_does_not_schedule_tasks": True,
    "daemon_recommendation_contract_does_not_send_alerts": True,
    "daemon_recommendation_contract_does_not_train_or_modify_models": True,
    "daemon_recommendation_contract_does_not_establish_federation_consensus": True,
}

FUTURE_ACTIVATION_REQUIREMENTS: tuple[str, ...] = (
    "explicit separate daemon implementation",
    "explicit operator consent",
    "explicit command execution boundary",
    "explicit scheduler boundary",
    "explicit alerting boundary",
    "explicit task creation boundary",
    "explicit finalizer/guard non-bypass invariant",
    "explicit ledger/glow storage policy",
    "explicit pulse watcher contract",
    "explicit federation drift consensus rule",
    "explicit vow digest constraint check",
    "tests proving no readiness authority",
    "docs marking active behavior",
)

# recommendation_id, name, type, source_signal_ids, source_categories, severity_floor, text, boundary note
_RECOMMENDATION_SPECS: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...], str, str, str], ...] = (
    ("provide_architecture_evidence", "Provide architecture evidence", "provide_missing_evidence", ("missing_architecture_map",), ("missing_input",), "watch", "Supply the architecture map evidence to the reviewing surface.", "Architecture evidence does not authorize landing."),
    ("provide_matrix_evidence", "Provide matrix evidence", "provide_missing_evidence", ("missing_matrix_evidence",), ("missing_input",), "caution", "Supply matrix evidence metadata for review.", "Matrix evidence remains proof context only."),
    ("provide_finalizer_evidence", "Provide finalizer evidence", "provide_missing_evidence", ("missing_finalizer_evidence",), ("missing_input",), "caution", "Supply finalizer evidence metadata for the appropriate phase.", "Only the finalizer may decide its phase readiness."),
    ("provide_pr_metadata_guard_evidence", "Provide PR metadata guard evidence", "provide_missing_evidence", ("missing_pr_metadata_guard_evidence",), ("missing_input",), "caution", "Supply PR metadata guard evidence metadata.", "Only the guard may authorize PR metadata."),
    ("provide_evidence_index", "Provide evidence index", "provide_missing_evidence", ("missing_evidence_index",), ("missing_input",), "watch", "Supply the landing evidence index metadata.", "The index catalogs artifacts only."),
    ("provide_lifecycle_doctor", "Provide lifecycle doctor", "provide_missing_evidence", ("missing_lifecycle_doctor",), ("missing_input",), "watch", "Supply lifecycle doctor diagnostic metadata.", "Doctor output is advisory context only."),
    ("provide_appendix_sidecar", "Provide appendix sidecar", "provide_missing_evidence", ("missing_appendix_sidecar",), ("provenance_pressure",), "watch", "Supply appendix provenance sidecar metadata.", "Provenance does not verify readiness."),
    ("provide_doctrine_map", "Provide doctrine map", "provide_missing_evidence", ("missing_doctrine_map",), ("doctrine_pressure",), "watch", "Supply doctrine map metadata for reviewer context.", "Doctrine context does not train or modify models."),
    ("inspect_required_matrix_failures", "Inspect required matrix failures", "inspect_proof_pressure", ("matrix_required_failure_observed",), ("proof_pressure",), "blocked_observation", "Inspect required matrix failures in the source matrix evidence.", "Inspection does not rerun commands."),
    ("inspect_diagnostic_nonproof_lanes", "Inspect diagnostic nonproof lanes", "inspect_proof_pressure", ("matrix_diagnostic_failure_observed",), ("proof_pressure",), "watch", "Inspect diagnostic nonproof lane failures as reviewer context.", "Diagnostics cannot become proof authority."),
    ("inspect_finalizer_rerun_signal", "Inspect finalizer rerun signal", "inspect_authority_pressure", ("finalizer_rerun_required_observed", "authority_status_absent"), ("authority_pressure",), "caution", "Inspect finalizer rerun or absent authority status metadata.", "Recommendation cannot decide readiness or rerun finalizer."),
    ("inspect_stale_evidence_refresh", "Inspect stale evidence refresh", "inspect_freshness_pressure", ("stale_evidence_refresh_observed",), ("freshness_pressure",), "caution", "Inspect stale evidence refresh pressure before relying on evidence context.", "Recommendation cannot make evidence fresh."),
    ("inspect_generated_artifact_cleanup", "Inspect generated artifact cleanup", "inspect_freshness_pressure", ("generated_artifact_cleanup_incomplete_observed",), ("freshness_pressure",), "caution", "Inspect generated artifact cleanup pressure.", "Recommendation cannot clean artifacts."),
    ("preserve_unmatched_pressure_signal", "Preserve unmatched pressure signal", "preserve_boundary", ("provenance_absent",), ("provenance_pressure",), "watch", "Preserve unmatched or provenance pressure for human review.", "Unknown pressure must not be converted into action."),
    ("document_future_integration_gap", "Document future integration gap", "document_future_integration", ("future_integration_unwired",), ("future_integration_pressure",), "info", "Document unwired future integration as inactive metadata.", "Future integration remains inactive."),
    ("preserve_daemon_inactive_boundary", "Preserve daemon inactive boundary", "preserve_boundary", ("daemon_repair_not_active",), ("daemon_boundary",), "info", "Preserve the daemon repair inactive boundary.", "No daemon action is triggered."),
    ("require_explicit_watcher_activation_contract", "Require explicit watcher activation contract", "require_future_contract", ("pulse_watch_not_active",), ("future_integration_pressure",), "info", "Require a separate watcher activation contract before any watching.", "This contract does not watch files."),
    ("require_explicit_scheduler_activation_contract", "Require explicit scheduler activation contract", "require_future_contract", ("pulse_watch_not_active",), ("future_integration_pressure",), "info", "Require a separate scheduler activation contract before scheduling.", "This contract does not schedule tasks."),
    ("require_explicit_daemon_action_contract", "Require explicit daemon action contract", "require_future_contract", ("daemon_repair_not_active",), ("daemon_boundary",), "info", "Require a separate daemon action contract before daemon repair behavior.", "This contract does not trigger daemon action."),
    ("require_federation_consensus_contract", "Require federation consensus contract", "require_future_contract", ("federation_consensus_absent",), ("federation_boundary",), "info", "Require a separate consensus contract before federation drift adoption.", "This contract establishes no federation consensus."),
    ("require_ledger_glow_storage_policy", "Require ledger glow storage policy", "require_future_contract", ("provenance_absent",), ("provenance_pressure",), "info", "Require explicit ledger/glow storage policy before archival writes.", "This contract writes no ledger or glow memory."),
    ("require_vow_digest_boundary_check", "Require vow digest boundary check", "require_future_contract", ("doctrine_context_absent",), ("doctrine_pressure",), "watch", "Require explicit vow digest constraint checks before future active interpretation.", "This contract does not override canonical constraints."),
)

class CodexWorkcellDaemonRecommendationContractError(ValueError):
    pass

@dataclass(frozen=True)
class CodexWorkcellDaemonRecommendationContractRequest:
    pulse_contract_json: str | None = None
    health_snapshot_json: str | None = None


def _known_signal_ids() -> set[str]:
    return {str(item["signal_id"]) for item in _signal_catalog()}


def _catalog() -> list[dict[str, Any]]:
    known = _known_signal_ids()
    catalog = []
    for rec_id, name, rec_type, signal_ids, categories, floor, text, boundary in _RECOMMENDATION_SPECS:
        if rec_type not in RECOMMENDATION_TYPES or floor not in SEVERITY_FLOORS or not set(signal_ids) <= known:
            raise CodexWorkcellDaemonRecommendationContractError(f"invalid_recommendation_spec:{rec_id}")
        catalog.append({
            "recommendation_id": rec_id,
            "recommendation_name": name,
            "recommendation_type": rec_type,
            "source_signal_ids": list(signal_ids),
            "source_categories": list(categories),
            "severity_floor": floor,
            "recommendation_text": text,
            "forbidden_action": "Must not trigger daemon action, create tasks, schedule work, send alerts, watch files, poll state, run commands, decide readiness, authorize commit, authorize PR metadata, write ledger entries, modify memory, establish federation consensus, or train/modify models.",
            "required_operator_boundary": "Any active repair, scheduling, command execution, alerting, task creation, storage, federation, or landing authority requires a separate explicit operator-authorized contract.",
            "daemon_non_action_boundary": boundary,
            "reviewer_summary": f"{name} maps {', '.join(signal_ids)} to {rec_type} with {floor} severity floor.",
        })
    return catalog


def _index(catalog: list[dict[str, Any]], key: str, values: tuple[str, ...]) -> dict[str, list[str]]:
    return {value: sorted(str(item["recommendation_id"]) for item in catalog if item[key] == value) for value in values}


def _source_signal_index(catalog: list[dict[str, Any]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {signal_id: [] for signal_id in sorted(_known_signal_ids())}
    for item in catalog:
        for signal_id in item["source_signal_ids"]:
            index[str(signal_id)].append(str(item["recommendation_id"]))
    return {key: sorted(value) for key, value in index.items() if value}


def _read_json(path_text: str | None, label: str) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    if path_text is None:
        return {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}, None
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellDaemonRecommendationContractError(f"missing_{label}_json:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellDaemonRecommendationContractError(f"invalid_{label}_json:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellDaemonRecommendationContractError(f"{label}_json_not_object:{path_text}")
    return {"provided": True, "path": path_text, "readable_json": True, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "error": None}, loaded


def _pulse_summary(summary: dict[str, Any], pulse: Mapping[str, Any] | None) -> dict[str, Any]:
    if pulse is None:
        return summary
    out = dict(summary)
    for src, dst in (("pulse_contract_id", "pulse_contract_id"),):
        if src in pulse:
            out[dst] = pulse[src]
    obs = pulse.get("observed_signal_summary")
    if isinstance(obs, Mapping):
        if isinstance(obs.get("observed_signal_ids"), list):
            out["observed_signal_count"] = len(obs["observed_signal_ids"])
        if isinstance(obs.get("unmatched_health_snapshot_pressure_signals"), list):
            out["unmatched_health_snapshot_pressure_signal_count"] = len(obs["unmatched_health_snapshot_pressure_signals"])
    if isinstance(pulse.get("category_index"), Mapping):
        out["category_count"] = len(pulse["category_index"])
    if isinstance(pulse.get("severity_index"), Mapping):
        out["severity_count"] = len(pulse["severity_index"])
    return out


def _health_summary(summary: dict[str, Any], health: Mapping[str, Any] | None) -> dict[str, Any]:
    if health is None:
        return summary
    out = dict(summary)
    if "workcell_health_snapshot_id" in health:
        out["workcell_health_snapshot_id"] = health["workcell_health_snapshot_id"]
    if isinstance(health.get("observed_pressure_signals"), list):
        out["observed_pressure_signal_count"] = len(health["observed_pressure_signals"])
    if isinstance(health.get("missing_inputs"), list):
        out["missing_input_count"] = len(health["missing_inputs"])
    return out


def _observed_recommendations(pulse: Mapping[str, Any] | None, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    base = {"recommendation_only": True, "no_action_taken": True}
    if pulse is None:
        return {"provided": False, "observed_signal_ids": [], "applicable_recommendation_ids": [], "unmatched_observed_signal_ids": [], "recommendation_types_observed": [], "severity_hints_observed": [], **base}
    raw = pulse.get("observed_signal_summary")
    observed_raw = raw.get("observed_signal_ids") if isinstance(raw, Mapping) else []
    observed = sorted(str(item) for item in observed_raw) if isinstance(observed_raw, list) else []
    index = _source_signal_index(catalog)
    applicable = sorted({rec for signal_id in observed for rec in index.get(signal_id, [])})
    by_id = {str(item["recommendation_id"]): item for item in catalog}
    return {"provided": True, "observed_signal_ids": observed, "applicable_recommendation_ids": applicable, "unmatched_observed_signal_ids": sorted(signal_id for signal_id in observed if signal_id not in index), "recommendation_types_observed": sorted({str(by_id[r]["recommendation_type"]) for r in applicable}), "severity_hints_observed": sorted({str(by_id[r]["severity_floor"]) for r in applicable}), **base}


def build_codex_workcell_daemon_recommendation_contract(request: CodexWorkcellDaemonRecommendationContractRequest | None = None) -> dict[str, Any]:
    request = request or CodexWorkcellDaemonRecommendationContractRequest()
    catalog = _catalog()
    pulse_summary_raw, pulse = _read_json(request.pulse_contract_json, "pulse_contract")
    health_summary_raw, health = _read_json(request.health_snapshot_json, "health_snapshot")
    return {
        "daemon_recommendation_contract_id": DAEMON_RECOMMENDATION_CONTRACT_ID,
        "metadata_only": True,
        "daemon_recommendation_contract_only": True,
        "not_runtime_authority": True,
        "not_watcher": True,
        "not_scheduler": True,
        "not_executor": True,
        "not_daemon_action": True,
        "not_task_creator": True,
        "not_alerting_system": True,
        "not_model_training": True,
        "not_reinforcement_learning": True,
        "recommendation_catalog": catalog,
        "recommendation_type_index": _index(catalog, "recommendation_type", RECOMMENDATION_TYPES),
        "source_signal_index": _source_signal_index(catalog),
        "pulse_contract_input_summary": _pulse_summary(pulse_summary_raw, pulse),
        "health_snapshot_input_summary": _health_summary(health_summary_raw, health),
        "observed_recommendation_summary": _observed_recommendations(pulse, catalog),
        "sentientos_mount_alignment": {"/daemon": "future repair recommendation consumer; inactive here", "/pulse": "source pressure signal categories and severity hints", "/glow": "future archive for observation surfaces and evidence context", "/ledger": "future receipt history context", "/vow": "canonical constraints bounding forbidden action and non-authority interpretation"},
        "future_activation_requirements": [{"requirement": item, "status": "future_only", "met": False, "active": False} for item in FUTURE_ACTIVATION_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }


def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\\r\\n", "<br>").replace("\\n", "<br>").replace("\\r", "<br>").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def render_codex_workcell_daemon_recommendation_contract_markdown(contract: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Daemon Recommendation Contract", "", "This is a deterministic metadata-only recommendation grammar. It maps supplied pulse signal IDs to bounded review recommendations only; it does not watch, poll, schedule, alert, create tasks, execute commands, trigger daemon action, decide readiness, authorize commit, authorize PR metadata, write ledger/glow memory, train models, or establish federation consensus."]
    for title, key in (("Pulse contract input summary", "pulse_contract_input_summary"), ("Health snapshot input summary", "health_snapshot_input_summary")):
        lines += ["", f"## {title}", "| key | value |", "| --- | --- |"]
        for item_key, value in sorted(contract[key].items()):
            lines.append(f"| {_cell(item_key)} | {_cell(value)} |")
    lines += ["", "## Recommendation catalog", "| recommendation_id | recommendation_name | recommendation_type | source_signal_ids | source_categories | severity_floor | reviewer_summary |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for item in contract["recommendation_catalog"]:
        lines.append(f"| {_cell(item['recommendation_id'])} | {_cell(item['recommendation_name'])} | {_cell(item['recommendation_type'])} | {_cell(item['source_signal_ids'])} | {_cell(item['source_categories'])} | {_cell(item['severity_floor'])} | {_cell(item['reviewer_summary'])} |")
    if contract["pulse_contract_input_summary"].get("provided"):
        lines += ["", "## Applicable recommendation summary", "| key | value |", "| --- | --- |"]
        for item_key, value in sorted(contract["observed_recommendation_summary"].items()):
            lines.append(f"| {_cell(item_key)} | {_cell(value)} |")
    for title, key in (("Recommendation type index", "recommendation_type_index"), ("Source signal index", "source_signal_index"), ("SentientOS mount alignment", "sentientos_mount_alignment")):
        lines += ["", f"## {title}", "| key | value |", "| --- | --- |"]
        for item_key, value in sorted(contract[key].items()):
            lines.append(f"| {_cell(item_key)} | {_cell(value)} |")
    lines += ["", "## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in contract["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"] + [f"- **{key}:** {str(value).lower()}" for key, value in sorted(contract["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)


def write_codex_workcell_daemon_recommendation_contract_json(contract: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_codex_workcell_daemon_recommendation_contract_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
