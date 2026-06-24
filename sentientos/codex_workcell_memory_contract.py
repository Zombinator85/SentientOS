from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

WORKCELL_MEMORY_CONTRACT_ID = "codex_workcell_memory_contract.v1"
DIGEST_ALGO = "sha256"

LEDGER_RECORD_TYPES: tuple[str, ...] = (
    "codex_landing_receipt",
    "matrix_receipt",
    "finalizer_receipt",
    "pr_metadata_guard_receipt",
    "evidence_index_receipt",
    "appendix_provenance_receipt",
    "health_snapshot_receipt",
    "pulse_contract_receipt",
    "daemon_recommendation_contract_receipt",
    "memory_contract_receipt",
)

LEDGER_CHAIN_FIELDS: tuple[str, ...] = (
    "ledger_entry_id",
    "record_type",
    "created_at",
    "source_artifact_id",
    "source_artifact_digest",
    "source_artifact_digest_algo",
    "parent_entry_id",
    "parent_entry_digest",
    "commit_sha",
    "pr_number",
    "pr_title",
    "merge_commit_sha",
    "finalizer_status",
    "pr_metadata_guard_status",
    "matrix_status",
    "non_authority_posture",
)

GLOW_ARCHIVE_ITEM_TYPES: tuple[str, ...] = (
    "workcell_architecture_snapshot",
    "workcell_health_snapshot",
    "pulse_contract_snapshot",
    "daemon_recommendation_contract_snapshot",
    "evidence_index_snapshot",
    "evidence_appendix_markdown",
    "evidence_appendix_sidecar",
    "doctrine_map_snapshot",
    "matrix_report_snapshot",
    "finalizer_report_snapshot",
    "pr_metadata_guard_snapshot",
)

GLOW_ARCHIVE_FIELDS: tuple[str, ...] = (
    "glow_item_id",
    "archive_item_type",
    "created_at",
    "source_path",
    "source_artifact_id",
    "source_digest",
    "source_digest_algo",
    "byte_size",
    "related_ledger_entry_id",
    "related_commit_sha",
    "related_pr_number",
    "review_surface",
    "memory_scope",
    "non_authority_posture",
)

SOURCE_ARTIFACT_FAMILIES: tuple[str, ...] = (
    "matrix report",
    "finalizer report",
    "PR metadata guard report",
    "evidence index",
    "evidence appendix markdown",
    "evidence appendix sidecar",
    "doctrine map",
    "workcell architecture",
    "health snapshot",
    "pulse contract",
    "daemon recommendation contract",
    "memory contract",
)

FUTURE_ACTIVATION_REQUIREMENTS: tuple[str, ...] = (
    "explicit ledger writer implementation",
    "explicit glow archiver implementation",
    "explicit storage path policy",
    "explicit retention policy",
    "explicit digest verification policy",
    "explicit parent-chain validation policy",
    "explicit operator consent",
    "explicit finalizer/guard non-bypass invariant",
    "explicit pulse watcher contract",
    "explicit daemon action contract",
    "explicit federation drift consensus rule",
    "explicit vow digest constraint check",
    "tests proving no readiness authority",
    "docs marking active behavior",
)

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "memory_contract_is_read_only": True,
    "memory_contract_is_metadata_only": True,
    "memory_contract_does_not_write_ledger": True,
    "memory_contract_does_not_archive_glow": True,
    "memory_contract_does_not_modify_memory": True,
    "memory_contract_does_not_watch_files": True,
    "memory_contract_does_not_poll_state": True,
    "memory_contract_does_not_rerun_commands": True,
    "memory_contract_does_not_decide_readiness": True,
    "memory_contract_does_not_bypass_finalizer": True,
    "memory_contract_does_not_bypass_pr_metadata_guard": True,
    "memory_contract_does_not_authorize_commit": True,
    "memory_contract_does_not_authorize_pr_creation": True,
    "memory_contract_does_not_trigger_daemon": True,
    "memory_contract_does_not_create_tasks": True,
    "memory_contract_does_not_schedule_tasks": True,
    "memory_contract_does_not_send_alerts": True,
    "memory_contract_does_not_train_or_modify_models": True,
    "memory_contract_does_not_establish_federation_consensus": True,
}

LEDGER_FORBIDDEN_INFERENCE = "Receipt schema metadata does not write ledger entries, verify readiness, authorize commit or PR metadata, establish consensus, or mutate memory."
GLOW_FORBIDDEN_INFERENCE = "Archive schema metadata does not archive files, write glow memory, decide retention, authorize disclosure, trigger watchers, or mutate memory."

_LEDGER_RECORD_SPECS: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], str], ...] = tuple(
    (
        record_type,
        record_type.replace("_", " ").title(),
        ("ledger_entry_id", "record_type", "created_at", "source_artifact_digest", "source_artifact_digest_algo", "non_authority_posture"),
        ("source_artifact_digest", "parent_entry_digest"),
        ("parent_entry_id", "parent_entry_digest"),
        ("created_at",),
        f"Defines future /ledger metadata for {record_type}; inactive and non-writing here.",
    )
    for record_type in LEDGER_RECORD_TYPES
)

_GLOW_ITEM_SPECS: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str, str], ...] = tuple(
    (
        item_type,
        item_type.replace("_", " ").title(),
        ("glow_item_id", "archive_item_type", "created_at", "source_digest", "source_digest_algo", "byte_size", "non_authority_posture"),
        ("source_digest",),
        ("source_path", "source_artifact_id", "related_ledger_entry_id", "related_commit_sha", "related_pr_number"),
        "future policy required before retention is active",
        f"Defines future /glow metadata for {item_type}; inactive and non-archiving here.",
    )
    for item_type in GLOW_ARCHIVE_ITEM_TYPES
)

class CodexWorkcellMemoryContractError(ValueError):
    pass

@dataclass(frozen=True)
class CodexWorkcellMemoryContractRequest:
    health_snapshot_json: str | None = None
    pulse_contract_json: str | None = None
    daemon_recommendation_contract_json: str | None = None
    evidence_index_json: str | None = None
    appendix_sidecar_json: str | None = None


def _read_json(path_text: str | None, label: str) -> dict[str, Any]:
    if path_text is None:
        return {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}
    path = Path(path_text)
    if not path.exists():
        raise CodexWorkcellMemoryContractError(f"missing_{label}_json:{path_text}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkcellMemoryContractError(f"invalid_{label}_json:{path_text}:{exc}") from exc
    if not isinstance(loaded, Mapping):
        raise CodexWorkcellMemoryContractError(f"{label}_json_not_object:{path_text}")
    summary: dict[str, Any] = {"provided": True, "path": path_text, "digest_algo": DIGEST_ALGO, "digest": digest, "byte_size": len(raw), "readable_json": True, "error": None}
    for key in ("workcell_health_snapshot_id", "pulse_contract_id", "daemon_recommendation_contract_id", "codex_landing_evidence_index_id", "appendix_sidecar_id"):
        if key in loaded:
            summary[key] = loaded[key]
    return summary


def _ledger_catalog() -> list[dict[str, Any]]:
    return [
        {
            "record_type": record_type,
            "record_name": name,
            "required_fields": list(required),
            "digest_fields": list(digests),
            "parent_reference_fields": list(parents),
            "timestamp_fields": list(timestamps),
            "authority_boundary": boundary,
            "forbidden_inference": LEDGER_FORBIDDEN_INFERENCE,
            "reviewer_summary": f"{name} defines future receipt-chain metadata only.",
        }
        for record_type, name, required, digests, parents, timestamps, boundary in _LEDGER_RECORD_SPECS
    ]


def _glow_catalog() -> list[dict[str, Any]]:
    return [
        {
            "archive_item_type": item_type,
            "archive_item_name": name,
            "required_metadata_fields": list(required),
            "digest_fields": list(digests),
            "source_reference_fields": list(source_refs),
            "retention_hint": retention_hint,
            "authority_boundary": boundary,
            "forbidden_inference": GLOW_FORBIDDEN_INFERENCE,
            "reviewer_summary": f"{name} defines future evidence-archive metadata only.",
        }
        for item_type, name, required, digests, source_refs, retention_hint, boundary in _GLOW_ITEM_SPECS
    ]


def _source_artifact_alignment() -> list[dict[str, Any]]:
    return [
        {
            "artifact_family": family,
            "ledger_role": f"future receipt metadata for {family}",
            "glow_role": f"future archive metadata for {family}",
            "source_digest_expected": True,
            "authority_boundary": "Alignment only; does not create, verify, store, archive, or approve the artifact.",
            "forbidden_inference": "Artifact alignment does not imply readiness, storage, retention, memory mutation, daemon action, federation consensus, or model training.",
        }
        for family in SOURCE_ARTIFACT_FAMILIES
    ]


def _index(catalog: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(item[key]): {"position": index, "name": str(item.get(key.replace("type", "name"), item[key]))} for index, item in enumerate(catalog)}


def build_codex_workcell_memory_contract(request: CodexWorkcellMemoryContractRequest | None = None) -> dict[str, Any]:
    request = request or CodexWorkcellMemoryContractRequest()
    ledger_catalog = _ledger_catalog()
    glow_catalog = _glow_catalog()
    return {
        "workcell_memory_contract_id": WORKCELL_MEMORY_CONTRACT_ID,
        "metadata_only": True,
        "memory_contract_only": True,
        "not_runtime_authority": True,
        "not_memory_writer": True,
        "not_ledger_writer": True,
        "not_glow_archiver": True,
        "not_watcher": True,
        "not_scheduler": True,
        "not_executor": True,
        "not_daemon_action": True,
        "not_task_creator": True,
        "not_alerting_system": True,
        "not_model_training": True,
        "not_reinforcement_learning": True,
        "input_summaries": {
            "health_snapshot_json": _read_json(request.health_snapshot_json, "health_snapshot"),
            "pulse_contract_json": _read_json(request.pulse_contract_json, "pulse_contract"),
            "daemon_recommendation_contract_json": _read_json(request.daemon_recommendation_contract_json, "daemon_recommendation_contract"),
            "evidence_index_json": _read_json(request.evidence_index_json, "evidence_index"),
            "appendix_sidecar_json": _read_json(request.appendix_sidecar_json, "appendix_sidecar"),
        },
        "ledger_receipt_chain_contract": {"mount": "/ledger", "active": False, "writes_ledger_entries": False, "canonical_fields": list(LEDGER_CHAIN_FIELDS), "record_catalog": ledger_catalog},
        "glow_evidence_archive_contract": {"mount": "/glow", "active": False, "archives_evidence": False, "canonical_fields": list(GLOW_ARCHIVE_FIELDS), "archive_catalog": glow_catalog},
        "ledger_record_type_index": _index(ledger_catalog, "record_type"),
        "glow_archive_item_type_index": _index(glow_catalog, "archive_item_type"),
        "source_artifact_alignment": _source_artifact_alignment(),
        "sentientos_mount_alignment": {
            "/ledger": "future tamper-evident landing history and receipt chain; inactive here",
            "/glow": "future archived evidence memory and review-surface archive; inactive here",
            "/pulse": "future consumer of ledger/glow history for pressure observation; inactive here",
            "/daemon": "future consumer of pulse/recommendation context; inactive here",
            "/vow": "canonical constraints bounding memory interpretation and forbidden inference",
        },
        "future_activation_requirements": [{"requirement": item, "status": "future_only", "met": False, "active": False} for item in FUTURE_ACTIVATION_REQUIREMENTS],
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }


def _cell(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else ("" if value is None else str(value))
    return text.replace("|", "\\|").replace("\\r\\n", "<br>").replace("\\n", "<br>").replace("\\r", "<br>").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def render_codex_workcell_memory_contract_markdown(contract: Mapping[str, Any]) -> str:
    lines = ["# Codex Workcell Memory Contract", "", "This deterministic metadata-only contract defines future /ledger receipt-chain and /glow evidence-archive schemas. It does not write ledger entries, archive files, mutate memory, watch, poll, schedule, alert, create tasks, trigger daemon action, decide readiness, authorize commit or PR metadata, train models, or establish federation consensus."]
    lines += ["", "## Input summary", "| input | provided | path | digest | byte_size | readable_json | error |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for key, summary in sorted(contract["input_summaries"].items()):
        lines.append(f"| {_cell(key)} | {_cell(summary.get('provided'))} | {_cell(summary.get('path'))} | {_cell(summary.get('digest'))} | {_cell(summary.get('byte_size'))} | {_cell(summary.get('readable_json'))} | {_cell(summary.get('error'))} |")
    lines += ["", "## /ledger receipt-chain contract", "| record_type | record_name | required_fields | digest_fields | parent_reference_fields | timestamp_fields | reviewer_summary |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for item in contract["ledger_receipt_chain_contract"]["record_catalog"]:
        lines.append(f"| {_cell(item['record_type'])} | {_cell(item['record_name'])} | {_cell(item['required_fields'])} | {_cell(item['digest_fields'])} | {_cell(item['parent_reference_fields'])} | {_cell(item['timestamp_fields'])} | {_cell(item['reviewer_summary'])} |")
    lines += ["", "## /glow evidence-archive contract", "| archive_item_type | archive_item_name | required_metadata_fields | digest_fields | source_reference_fields | retention_hint | reviewer_summary |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for item in contract["glow_evidence_archive_contract"]["archive_catalog"]:
        lines.append(f"| {_cell(item['archive_item_type'])} | {_cell(item['archive_item_name'])} | {_cell(item['required_metadata_fields'])} | {_cell(item['digest_fields'])} | {_cell(item['source_reference_fields'])} | {_cell(item['retention_hint'])} | {_cell(item['reviewer_summary'])} |")
    lines += ["", "## Source artifact alignment", "| artifact_family | ledger_role | glow_role | source_digest_expected |", "| --- | --- | --- | --- |"]
    for item in contract["source_artifact_alignment"]:
        lines.append(f"| {_cell(item['artifact_family'])} | {_cell(item['ledger_role'])} | {_cell(item['glow_role'])} | {_cell(item['source_digest_expected'])} |")
    lines += ["", "## SentientOS mount alignment", "| mount | alignment |", "| --- | --- |"]
    for key, value in sorted(contract["sentientos_mount_alignment"].items()):
        lines.append(f"| {_cell(key)} | {_cell(value)} |")
    lines += ["", "## Future activation requirements", "| requirement | status | met | active |", "| --- | --- | --- | --- |"]
    for item in contract["future_activation_requirements"]:
        lines.append(f"| {_cell(item['requirement'])} | {_cell(item['status'])} | {_cell(item['met'])} | {_cell(item['active'])} |")
    lines += ["", "## Non-authority posture"] + [f"- **{key}:** {str(value).lower()}" for key, value in sorted(contract["non_authority_posture"].items())]
    lines.append("")
    return "\n".join(lines)


def write_codex_workcell_memory_contract_json(contract: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_codex_workcell_memory_contract_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
