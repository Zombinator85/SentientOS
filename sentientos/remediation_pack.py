from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from sentientos.recovery_allowlist import is_allowlisted
from sentientos.schema_registry import SchemaCompatibilityError, SchemaName, normalize
from sentientos.recovery_tasks import append_task_record, list_tasks

SCHEMA_VERSION = 1
PACKS_DIR = Path("glow/forge/remediation/packs")
PACKS_PULSE_PATH = Path("pulse/remediation_packs.jsonl")
RUNS_DIR = Path("glow/forge/remediation/runs")


_REASON_STEP_LIBRARY: dict[str, list[dict[str, object]]] = {
    "audit_chain_broken": [
        {
            "name": "repair_audit_index",
            "command": "python scripts/audit_chain_doctor.py --repair-index-only",
            "kind": "repair",
            "preconditions": ["audit_chain_report_present"],
            "expected_artifacts": ["glow/forge/audit_doctor_*.json"],
            "destructive": False,
        },
        {
            "name": "verify_audits_strict",
            "command": "python scripts/verify_audits.py --strict",
            "kind": "verify",
            "preconditions": ["audit_index_repaired_or_intact"],
            "expected_artifacts": ["glow/contracts/stability_doctrine.json"],
            "destructive": False,
        },
    ],
    "receipt_chain_broken": [
        {
            "name": "verify_receipt_chain",
            "command": "python scripts/verify_receipt_chain.py --last 50",
            "kind": "verify",
            "preconditions": ["receipt_index_present"],
            "expected_artifacts": ["glow/forge/receipts/receipts_index.jsonl"],
            "destructive": False,
        }
    ],
    "receipt_anchor_invalid": [
        {
            "name": "verify_receipt_anchors",
            "command": "python scripts/verify_receipt_anchors.py --last 10",
            "kind": "verify",
            "preconditions": ["anchor_index_present"],
            "expected_artifacts": ["glow/forge/receipts/anchors/anchors_index.jsonl"],
            "destructive": False,
        },
        {
            "name": "anchor_receipt_chain",
            "command": "python scripts/anchor_receipt_chain.py",
            "kind": "repair",
            "preconditions": ["receipt_signing_configured"],
            "expected_artifacts": ["glow/forge/receipts/anchors/anchors_index.jsonl"],
            "destructive": False,
        },
    ],
    "receipt_anchor_missing": [
        {
            "name": "verify_receipt_anchors",
            "command": "python scripts/verify_receipt_anchors.py --last 10",
            "kind": "verify",
            "preconditions": ["anchor_index_present_or_empty"],
            "expected_artifacts": ["glow/forge/receipts/anchors/anchors_index.jsonl"],
            "destructive": False,
        },
        {
            "name": "anchor_receipt_chain",
            "command": "python scripts/anchor_receipt_chain.py",
            "kind": "repair",
            "preconditions": ["receipt_signing_configured"],
            "expected_artifacts": ["glow/forge/receipts/anchors/anchors_index.jsonl"],
            "destructive": False,
        },
    ],
    "federation_integrity_diverged": [
        {
            "name": "emit_integrity_snapshot",
            "command": "python -m sentientos.integrity_snapshot",
            "kind": "observe",
            "preconditions": ["federation_config_present"],
            "expected_artifacts": ["glow/federation/integrity_snapshot.json"],
            "destructive": False,
        },
        {
            "name": "publish_anchor_witness",
            "command": "python scripts/publish_anchor_witness.py",
            "kind": "observe",
            "preconditions": ["witness_publish_enabled"],
            "expected_artifacts": ["glow/federation/anchor_witness_status.json"],
            "destructive": False,
        },
    ],
    "doctrine_identity_mismatch": [
        {
            "name": "verify_doctrine_identity",
            "command": "python scripts/verify_doctrine_identity.py",
            "kind": "verify",
            "preconditions": ["doctrine_bundle_present"],
            "expected_artifacts": ["glow/contracts/doctrine_identity.json"],
            "destructive": False,
        },
        {
            "name": "refresh_doctrine_bundle",
            "command": "python scripts/emit_stability_doctrine.py",
            "kind": "repair",
            "preconditions": ["remote_doctrine_fetch_enabled"],
            "expected_artifacts": ["glow/contracts/stability_doctrine.json"],
            "destructive": False,
        },
    ],
    "risk_budget_throttle": [
        {
            "name": "risk_budget_operator_guidance",
            "command": "python scripts/verify_audits.py --strict",
            "kind": "suggestion",
            "preconditions": ["operator_adjusts_posture_or_waits_for_pressure_drop"],
            "expected_artifacts": ["glow/contracts/stability_doctrine.json"],
            "destructive": False,
        }
    ],
    "mode_throttle_publish": [
        {
            "name": "mode_throttle_operator_guidance",
            "command": "python scripts/verify_audits.py --strict",
            "kind": "suggestion",
            "preconditions": ["operator_adjusts_mode_or_waits_for_pressure_drop"],
            "expected_artifacts": ["glow/contracts/stability_doctrine.json"],
            "destructive": False,
        }
    ],
    "quarantine_active": [
        {
            "name": "audit_chain_repair",
            "command": "python scripts/audit_chain_doctor.py --repair-index-only",
            "kind": "repair",
            "preconditions": ["quarantine_reviewed"],
            "expected_artifacts": ["glow/forge/audit_doctor_*.json"],
            "destructive": False,
        },
        {
            "name": "verify_audits_strict",
            "command": "python scripts/verify_audits.py --strict",
            "kind": "verify",
            "preconditions": ["quarantine_reviewed"],
            "expected_artifacts": ["glow/contracts/stability_doctrine.json"],
            "destructive": False,
        },
    ],
}


def emit_pack_from_trace(repo_root: Path, *, trace_payload: dict[str, object], trace_path: str) -> dict[str, object] | None:
    final_decision = str(trace_payload.get("final_decision", ""))
    if final_decision not in {"hold", "block", "diagnostics_only", "quarantine_active"}:
        return None
    context = str(trace_payload.get("context", ""))
    if context not in {"merge_train", "canary_publish", "forge_run"}:
        return None
    reason_stack = [str(item) for item in list(trace_payload.get("reason_stack") or []) if isinstance(item, str)]
    primary_reason = str(trace_payload.get("final_reason") or "")
    reasons = [primary_reason] + [item for item in reason_stack if item != primary_reason]

    steps: list[dict[str, object]] = []
    seen_commands: set[str] = set()
    for reason in reasons:
        for template in _REASON_STEP_LIBRARY.get(reason, []):
            command = str(template["command"])
            if command in seen_commands:
                continue
            seen_commands.add(command)
            step = dict(template)
            step["allowlisted"] = is_allowlisted(command)
            steps.append(step)

    if not steps:
        return None

    created_at = _iso_now()
    trace_id = str(trace_payload.get("trace_id") or "trace")
    short_trace = trace_id[-8:].replace("/", "_")
    stamp = created_at.replace("-", "").replace(":", "").replace("Z", "")
    pack_id = f"{stamp}_{short_trace}"

    evidence_paths = [trace_path]
    for gate in list(trace_payload.get("gates_evaluated") or []):
        if not isinstance(gate, dict):
            continue
        items = gate.get("evidence_paths")
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str):
                evidence_paths.append(item)

    pack = {
        "schema_version": SCHEMA_VERSION,
        "pack_id": pack_id,
        "created_at": created_at,
        "governance_trace_id": trace_id,
        "primary_reason": primary_reason,
        "reason_stack": reason_stack,
        "mode_summary": str(trace_payload.get("operating_mode") or "unknown"),
        "posture_summary": str(trace_payload.get("strategic_posture") or "unknown"),
        "pressure_summary": {
            "level": trace_payload.get("integrity_pressure_level"),
            "metrics": trace_payload.get("integrity_metrics_summary") if isinstance(trace_payload.get("integrity_metrics_summary"), dict) else {},
        },
        "steps": steps,
        "status": "proposed",
        "evidence_paths": sorted(set(evidence_paths)),
        "trace_path": trace_path,
    }
    incident_id = _optional_str(trace_payload.get("incident_id"))
    if incident_id is None:
        quarantine_summary = trace_payload.get("quarantine_state_summary")
        if isinstance(quarantine_summary, dict):
            incident_id = _optional_str(quarantine_summary.get("last_incident_id"))
    if incident_id is not None:
        pack["incident_id"] = incident_id

    root = repo_root.resolve()
    pack_path = root / PACKS_DIR / f"pack_{pack_id}.json"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _append_pack_pulse(root, pack, pack_path)

    should_auto_queue = str(trace_payload.get("operating_mode") or "") in {"recovery", "lockdown"}
    quarantine_summary = trace_payload.get("quarantine_state_summary")
    if isinstance(quarantine_summary, dict) and bool(quarantine_summary.get("active")):
        should_auto_queue = True
    if should_auto_queue:
        queued = enqueue_pack_steps(root, pack)
        pack["status"] = "queued" if queued else "proposed"
        pack["queued_steps"] = queued
        pack_path.write_text(json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"pack_id": pack_id, "pack_path": str(pack_path.relative_to(root)), "status": pack["status"], "queued_steps": pack.get("queued_steps", 0)}


def enqueue_pack_steps(repo_root: Path, pack: dict[str, object]) -> int:
    rows = list_tasks(repo_root)
    open_kinds = {str(item.get("kind")) for item in rows if str(item.get("status", "open")) != "done"}
    pack_id = str(pack.get("pack_id") or "unknown")
    queued = 0
    for index, step in enumerate(list(pack.get("steps") or [])):
        if not isinstance(step, dict):
            continue
        destructive = bool(step.get("destructive", True))
        if destructive:
            continue
        if not bool(step.get("allowlisted", False)):
            continue
        if str(step.get("kind", "")) == "suggestion":
            continue
        kind = f"remediation_pack:{pack_id}:{index:02d}"
        if kind in open_kinds:
            continue
        append_task_record(
            repo_root,
            {
                "kind": kind,
                "created_at": _iso_now(),
                "reason": str(pack.get("primary_reason") or "remediation_pack"),
                "status": "open",
                "suggested_command": str(step.get("command") or ""),
                "related_pack_id": pack_id,
                "step_name": str(step.get("name") or "step"),
            },
        )
        queued += 1
    return queued


def _append_pack_pulse(repo_root: Path, pack: dict[str, object], pack_path: Path) -> None:
    row = {
        "pack_id": pack.get("pack_id"),
        "created_at": pack.get("created_at"),
        "governance_trace_id": pack.get("governance_trace_id"),
        "primary_reason": pack.get("primary_reason"),
        "incident_id": pack.get("incident_id"),
        "status": pack.get("status"),
        "steps_count": len(list(pack.get("steps") or [])),
        "pack_path": str(pack_path.relative_to(repo_root)),
    }
    path = repo_root / PACKS_PULSE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_pack_for_incident_or_trace(
    repo_root: Path,
    *,
    incident_id: str | None,
    governance_trace_id: str | None,
) -> dict[str, object] | None:
    rows = _read_jsonl(repo_root.resolve() / PACKS_PULSE_PATH)
    for row in reversed(rows):
        row_incident = _optional_str(row.get("incident_id"))
        row_trace = _optional_str(row.get("governance_trace_id"))
        if incident_id and row_incident == incident_id:
            return row
        if governance_trace_id and row_trace == governance_trace_id:
            return row
    return None


def latest_run_for_pack(repo_root: Path, *, pack_id: str) -> dict[str, object] | None:
    candidates = sorted((repo_root.resolve() / RUNS_DIR).glob(f"run_*_{pack_id}.json"), key=lambda item: item.name)
    if not candidates:
        return None
    payload = _load_json(candidates[-1])
    if not payload:
        return None
    try:
        payload, _warnings = normalize(payload, SchemaName.REMEDIATION_RUN)
    except SchemaCompatibilityError:
        return None
    payload["report_path"] = str(candidates[-1].relative_to(repo_root.resolve()))
    return payload


def remediation_status_for_pack(repo_root: Path, *, pack_id: str) -> tuple[str, dict[str, object] | None]:
    run_payload = latest_run_for_pack(repo_root, pack_id=pack_id)
    if run_payload is None:
        return ("missing", None)
    return ("completed" if str(run_payload.get("status")) == "completed" else "failed", run_payload)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
