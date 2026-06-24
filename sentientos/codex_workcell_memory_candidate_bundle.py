from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

WORKCELL_MEMORY_CANDIDATE_BUNDLE_ID = "codex_workcell_memory_candidate_bundle.v1"
DIGEST_ALGO = "sha256"

INPUT_IDS: tuple[str, ...] = (
    "memory_contract_json", "architecture_json", "health_snapshot_json", "pulse_contract_json",
    "daemon_recommendation_contract_json", "matrix_json", "pre_commit_finalizer_json",
    "pr_metadata_finalizer_json", "pr_metadata_guard_json", "evidence_index_json",
    "appendix_sidecar_json", "doctrine_map_json",
)

LEDGER_BY_INPUT: dict[str, str | None] = {
    "memory_contract_json": "memory_contract_receipt",
    "architecture_json": "codex_landing_receipt",
    "health_snapshot_json": "health_snapshot_receipt",
    "pulse_contract_json": "pulse_contract_receipt",
    "daemon_recommendation_contract_json": "daemon_recommendation_contract_receipt",
    "matrix_json": "matrix_receipt",
    "pre_commit_finalizer_json": "finalizer_receipt",
    "pr_metadata_finalizer_json": "finalizer_receipt",
    "pr_metadata_guard_json": "pr_metadata_guard_receipt",
    "evidence_index_json": "evidence_index_receipt",
    "appendix_sidecar_json": "appendix_provenance_receipt",
    "doctrine_map_json": None,
}

GLOW_BY_INPUT: dict[str, str] = {
    "memory_contract_json": "memory_contract_snapshot",
    "architecture_json": "workcell_architecture_snapshot",
    "health_snapshot_json": "workcell_health_snapshot",
    "pulse_contract_json": "pulse_contract_snapshot",
    "daemon_recommendation_contract_json": "daemon_recommendation_contract_snapshot",
    "matrix_json": "matrix_report_snapshot",
    "pre_commit_finalizer_json": "finalizer_report_snapshot",
    "pr_metadata_finalizer_json": "finalizer_report_snapshot",
    "pr_metadata_guard_json": "pr_metadata_guard_snapshot",
    "evidence_index_json": "evidence_index_snapshot",
    "appendix_sidecar_json": "evidence_appendix_sidecar",
    "doctrine_map_json": "doctrine_map_snapshot",
}

FAMILY_BY_INPUT: dict[str, str] = {key: key.removesuffix("_json").replace("_", " ") for key in INPUT_IDS}
FUTURE_ACTIVATION_REQUIREMENTS: tuple[str, ...] = (
    "explicit ledger writer implementation", "explicit glow archiver implementation", "explicit storage path policy",
    "explicit retention policy", "explicit digest verification policy", "explicit parent-chain validation policy",
    "explicit operator consent", "explicit finalizer/guard non-bypass invariant", "explicit pulse watcher contract",
    "explicit daemon action contract", "explicit federation drift consensus rule", "explicit vow digest constraint check",
    "tests proving no readiness authority", "docs marking active behavior",
)
NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "memory_candidate_bundle_is_read_only": True,
    "memory_candidate_bundle_is_metadata_only": True,
    "memory_candidate_bundle_is_candidate_only": True,
    "memory_candidate_bundle_does_not_write_ledger": True,
    "memory_candidate_bundle_does_not_archive_glow": True,
    "memory_candidate_bundle_does_not_modify_memory": True,
    "memory_candidate_bundle_does_not_watch_files": True,
    "memory_candidate_bundle_does_not_poll_state": True,
    "memory_candidate_bundle_does_not_rerun_commands": True,
    "memory_candidate_bundle_does_not_decide_readiness": True,
    "memory_candidate_bundle_does_not_bypass_finalizer": True,
    "memory_candidate_bundle_does_not_bypass_pr_metadata_guard": True,
    "memory_candidate_bundle_does_not_authorize_commit": True,
    "memory_candidate_bundle_does_not_authorize_pr_creation": True,
    "memory_candidate_bundle_does_not_trigger_daemon": True,
    "memory_candidate_bundle_does_not_create_tasks": True,
    "memory_candidate_bundle_does_not_schedule_tasks": True,
    "memory_candidate_bundle_does_not_send_alerts": True,
    "memory_candidate_bundle_does_not_train_or_modify_models": True,
    "memory_candidate_bundle_does_not_establish_federation_consensus": True,
}
AUTHORITY_BOUNDARY = "Candidate metadata only; does not write memory, decide readiness, authorize landing, trigger daemon action, schedule work, alert, or establish consensus."
FORBIDDEN_INFERENCE = "Do not infer ledger persistence, glow archiving, readiness, commit authority, PR metadata authority, daemon action, task creation, model training, or federation consensus from this candidate record."

class CodexWorkcellMemoryCandidateBundleError(ValueError):
    pass

@dataclass(frozen=True)
class CodexWorkcellMemoryCandidateBundleRequest:
    memory_contract_json: str | None = None
    architecture_json: str | None = None
    health_snapshot_json: str | None = None
    pulse_contract_json: str | None = None
    daemon_recommendation_contract_json: str | None = None
    matrix_json: str | None = None
    pre_commit_finalizer_json: str | None = None
    pr_metadata_finalizer_json: str | None = None
    pr_metadata_guard_json: str | None = None
    evidence_index_json: str | None = None
    appendix_sidecar_json: str | None = None
    doctrine_map_json: str | None = None

def _stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"

def _read_json(path_text: str | None, input_id: str) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    if path_text is None:
        return ({"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}, None)
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellMemoryCandidateBundleError(f"missing_{input_id}:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellMemoryCandidateBundleError(f"invalid_{input_id}:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellMemoryCandidateBundleError(f"{input_id}_not_object:{path_text}")
    return {"provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}, loaded

def _discover(data: Mapping[str, Any] | None, *keys: str) -> Any:
    if data is None:
        return None
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    for value in data.values():
        if isinstance(value, Mapping):
            found = _discover(value, *keys)
            if found is not None:
                return found
    return None

def _artifact_id(data: Mapping[str, Any] | None) -> Any:
    if data is None:
        return None
    for key, value in data.items():
        if key.endswith("_id") and isinstance(value, (str, int, float)):
            return value
    return _discover(data, "artifact_id", "id")

def _contract_summary(summary: Mapping[str, Any], data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not summary.get("provided"):
        return {"provided": False, "fallback_mapping": "Candidate records are built from static fallback mappings in this module."}
    ledger = data.get("ledger_receipt_chain_contract", {}) if data else {}
    glow = data.get("glow_evidence_archive_contract", {}) if data else {}
    alignment = data.get("source_artifact_alignment", []) if data else []
    return {
        "provided": True,
        "workcell_memory_contract_id": data.get("workcell_memory_contract_id") if data else None,
        "ledger_record_type_count": len(ledger.get("record_catalog", [])) if isinstance(ledger, Mapping) else None,
        "glow_archive_item_type_count": len(glow.get("archive_catalog", [])) if isinstance(glow, Mapping) else None,
        "source_artifact_alignment_count": len(alignment) if isinstance(alignment, list) else None,
    }

def build_codex_workcell_memory_candidate_bundle(request: CodexWorkcellMemoryCandidateBundleRequest | None = None) -> dict[str, Any]:
    request = request or CodexWorkcellMemoryCandidateBundleRequest()
    input_summaries: dict[str, dict[str, Any]] = {}
    data_by_input: dict[str, Mapping[str, Any] | None] = {}
    for input_id in INPUT_IDS:
        summary, data = _read_json(getattr(request, input_id), input_id)
        input_summaries[input_id] = summary
        data_by_input[input_id] = data
    ledger_entries: list[dict[str, Any]] = []
    glow_items: list[dict[str, Any]] = []
    entry_id_by_input: dict[str, str] = {}
    for input_id in INPUT_IDS:
        summary = input_summaries[input_id]
        if not summary["provided"] or LEDGER_BY_INPUT[input_id] is None:
            continue
        data = data_by_input[input_id]
        entry_id = _stable_id("candidate-ledger", input_id, summary["digest"], LEDGER_BY_INPUT[input_id])
        entry_id_by_input[input_id] = entry_id
        ledger_entries.append({
            "candidate_entry_id": entry_id, "candidate_only": True, "would_be_record_type": LEDGER_BY_INPUT[input_id],
            "source_input_id": input_id, "source_artifact_digest": summary["digest"], "source_artifact_digest_algo": DIGEST_ALGO,
            "source_artifact_byte_size": summary["byte_size"], "source_artifact_id": _artifact_id(data),
            "parent_entry_id": _discover(data, "parent_entry_id"), "parent_entry_digest": _discover(data, "parent_entry_digest"),
            "commit_sha": _discover(data, "commit_sha", "head_sha"), "pr_number": _discover(data, "pr_number", "pull_request_number"),
            "pr_title": _discover(data, "pr_title", "title"), "merge_commit_sha": _discover(data, "merge_commit_sha"),
            "observed_status": _discover(data, "status", "decision", "proof_status", "matrix_status", "finalizer_status", "pr_metadata_guard_status"),
            "authority_boundary": AUTHORITY_BOUNDARY, "forbidden_inference": FORBIDDEN_INFERENCE, "no_write_performed": True,
        })
    for input_id in INPUT_IDS:
        summary = input_summaries[input_id]
        if not summary["provided"]:
            continue
        data = data_by_input[input_id]
        glow_items.append({
            "candidate_glow_item_id": _stable_id("candidate-glow", input_id, summary["digest"], GLOW_BY_INPUT[input_id]),
            "candidate_only": True, "would_be_archive_item_type": GLOW_BY_INPUT[input_id], "source_input_id": input_id,
            "source_path": summary["path"], "source_digest": summary["digest"], "source_digest_algo": DIGEST_ALGO,
            "byte_size": summary["byte_size"], "source_artifact_id": _artifact_id(data),
            "related_candidate_ledger_entry_id": entry_id_by_input.get(input_id), "related_commit_sha": _discover(data, "commit_sha", "head_sha"),
            "related_pr_number": _discover(data, "pr_number", "pull_request_number"), "review_surface": "candidate memory review",
            "memory_scope": "metadata-only candidate /glow archive record", "authority_boundary": AUTHORITY_BOUNDARY,
            "forbidden_inference": FORBIDDEN_INFERENCE, "no_archive_performed": True,
        })
    source_map = []
    for input_id in INPUT_IDS:
        summary = input_summaries[input_id]
        if summary["provided"]:
            source_map.append({"input_id": input_id, "provided": True, "digest": summary["digest"], "byte_size": summary["byte_size"],
                "candidate_ledger_entry_ids": [e["candidate_entry_id"] for e in ledger_entries if e["source_input_id"] == input_id],
                "candidate_glow_item_ids": [g["candidate_glow_item_id"] for g in glow_items if g["source_input_id"] == input_id],
                "source_family": FAMILY_BY_INPUT[input_id], "authority_boundary": AUTHORITY_BOUNDARY})
    parent_observed = sum(1 for e in ledger_entries if e["parent_entry_id"] or e["parent_entry_digest"])
    related_observed = sum(1 for g in glow_items if g["related_candidate_ledger_entry_id"])
    return {
        "memory_candidate_bundle_id": WORKCELL_MEMORY_CANDIDATE_BUNDLE_ID, "metadata_only": True, "candidate_bundle_only": True,
        "not_runtime_authority": True, "not_memory_writer": True, "not_ledger_writer": True, "not_glow_archiver": True,
        "not_watcher": True, "not_scheduler": True, "not_executor": True, "not_daemon_action": True, "not_task_creator": True,
        "not_alerting_system": True, "not_model_training": True, "not_reinforcement_learning": True,
        "input_summaries": input_summaries, "contract_summary": _contract_summary(input_summaries["memory_contract_json"], data_by_input["memory_contract_json"]),
        "candidate_ledger_entries": ledger_entries, "candidate_glow_items": glow_items, "source_artifact_map": source_map,
        "candidate_chain_summary": {"candidate_ledger_entry_count": len(ledger_entries), "candidate_record_types": sorted({str(e["would_be_record_type"]) for e in ledger_entries}), "parent_links_observed_count": parent_observed, "parent_links_missing_count": len(ledger_entries) - parent_observed, "candidate_only": True, "no_ledger_write_performed": True},
        "candidate_archive_summary": {"candidate_glow_item_count": len(glow_items), "candidate_archive_item_types": sorted({str(g["would_be_archive_item_type"]) for g in glow_items}), "related_ledger_links_observed_count": related_observed, "related_ledger_links_missing_count": len(glow_items) - related_observed, "candidate_only": True, "no_glow_archive_performed": True},
        "sentientos_mount_alignment": {"/ledger": "candidate receipt entries only; no ledger write", "/glow": "candidate archive records only; no archive write", "/pulse": "future consumer of stored history; inactive here", "/daemon": "future consumer of pulse/recommendation context; inactive here", "/vow": "canonical constraints bounding candidate interpretation and forbidden inference"},
        "future_activation_requirements": [{"requirement": r, "status": "future_only", "met": False, "active": False} for r in FUTURE_ACTIVATION_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }

def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")

def render_codex_workcell_memory_candidate_bundle_markdown(bundle: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Memory Candidate Bundle", "", "Deterministic metadata-only candidate records for review. This bundle does not write /ledger, archive /glow, mutate memory, decide readiness, authorize landing, trigger daemon action, schedule work, create tasks, alert, or train models."]
    lines += ["", "## Input summary", "| input | provided | path | digest | byte_size | readable_json | error |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for key, summary in sorted(bundle["input_summaries"].items()):
        lines.append(f"| {_cell(key)} | {_cell(summary.get('provided'))} | {_cell(summary.get('path'))} | {_cell(summary.get('digest'))} | {_cell(summary.get('byte_size'))} | {_cell(summary.get('readable_json'))} | {_cell(summary.get('error'))} |")
    lines += ["", "## Contract summary", f"`{_cell(bundle['contract_summary'])}`", "", "## Candidate ledger entries", "| candidate_entry_id | type | input | artifact_id | digest | byte_size | status | no_write |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for e in bundle["candidate_ledger_entries"]:
        lines.append(f"| {_cell(e['candidate_entry_id'])} | {_cell(e['would_be_record_type'])} | {_cell(e['source_input_id'])} | {_cell(e.get('source_artifact_id'))} | {_cell(e['source_artifact_digest'])} | {_cell(e['source_artifact_byte_size'])} | {_cell(e.get('observed_status'))} | {_cell(e['no_write_performed'])} |")
    lines += ["", "## Candidate glow items", "| candidate_glow_item_id | type | input | path | artifact_id | digest | related_ledger | no_archive |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for g in bundle["candidate_glow_items"]:
        lines.append(f"| {_cell(g['candidate_glow_item_id'])} | {_cell(g['would_be_archive_item_type'])} | {_cell(g['source_input_id'])} | {_cell(g['source_path'])} | {_cell(g.get('source_artifact_id'))} | {_cell(g['source_digest'])} | {_cell(g.get('related_candidate_ledger_entry_id'))} | {_cell(g['no_archive_performed'])} |")
    lines += ["", "## Source artifact map", "| input | family | ledger_ids | glow_ids |", "| --- | --- | --- | --- |"]
    for item in bundle["source_artifact_map"]:
        lines.append(f"| {_cell(item['input_id'])} | {_cell(item['source_family'])} | {_cell(item['candidate_ledger_entry_ids'])} | {_cell(item['candidate_glow_item_ids'])} |")
    for title, key in (("Candidate chain summary", "candidate_chain_summary"), ("Candidate archive summary", "candidate_archive_summary")):
        lines += ["", f"## {title}", f"`{_cell(bundle[key])}`"]
    lines += ["", "## SentientOS mount alignment", "| mount | alignment |", "| --- | --- |"]
    for key, value in sorted(bundle["sentientos_mount_alignment"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value)} |")
    lines += ["", "## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in bundle["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"] + [f"- **{key}:** {str(value).lower()}" for key, value in sorted(bundle["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)

def write_codex_workcell_memory_candidate_bundle_json(bundle: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_codex_workcell_memory_candidate_bundle_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
