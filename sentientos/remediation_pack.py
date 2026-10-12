from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from sentientos.recovery_allowlist import is_allowlisted
from sentientos.artifact_catalog import append_catalog_entry, latest_for_incident, latest_for_trace, load_catalog_artifact
from sentientos.schema_registry import SchemaCompatibilityError, SchemaName, normalize
from sentientos.recovery_tasks import append_task_record, list_tasks
from sentientos.private_file_custody import (
    PrivateFileCustodyError,
    list_bounded_json_names_at,
    open_private_directory,
    read_private_file_at,
    publish_immutable_bytes,
)
from sentientos.windows_handle_custody import WindowsHandleCustodyError, read_explicit_file, read_regular_files

SCHEMA_VERSION = 1
PACKS_DIR = Path("glow/forge/remediation/packs")
PACKS_PULSE_PATH = Path("pulse/remediation_packs.jsonl")
RUNS_DIR = Path("glow/forge/remediation/runs")
INTENTS_DIR = Path("glow/forge/remediation/intents")
MAX_REMEDIATION_PACK_BYTES = 1_048_576
MAX_REMEDIATION_RUN_BYTES = 1_048_576
MAX_REMEDIATION_RUN_FILES = 512
_PACK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_RUN_FILE_RE = re.compile(r"^run_[0-9]{8}T[0-9]{6}Z_[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json$")
_INTENT_FILE_RE = re.compile(r"^intent_([0-9]{8}T[0-9]{6}Z)_([A-Za-z0-9][A-Za-z0-9_.-]{0,127})\.json$")


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
    append_catalog_entry(
        root,
        kind="remediation_pack",
        artifact_id=pack_id,
        relative_path=str(pack_path.relative_to(root)),
        schema_name="remediation_pack",
        schema_version=SCHEMA_VERSION,
        links={"pack_id": pack_id, "trace_id": trace_id, "incident_id": incident_id},
        summary={"status": str(pack.get("status") or "proposed"), "primary_reason": primary_reason},
        ts=created_at,
    )

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
    root = repo_root.resolve()
    entry: dict[str, object] | None = None
    if incident_id:
        entry = latest_for_incident(root, incident_id, kind="remediation_pack")
    if entry is None and governance_trace_id:
        entry = latest_for_trace(root, governance_trace_id, kind="remediation_pack")
    if entry is not None:
        payload = load_catalog_artifact(root, entry) or {}
        return {
            "pack_id": payload.get("pack_id") or entry.get("id"),
            "created_at": payload.get("created_at") or entry.get("ts"),
            "governance_trace_id": payload.get("governance_trace_id") or (entry.get("links") if isinstance(entry.get("links"), dict) else {}).get("trace_id"),
            "primary_reason": payload.get("primary_reason"),
            "incident_id": payload.get("incident_id") or (entry.get("links") if isinstance(entry.get("links"), dict) else {}).get("incident_id"),
            "status": payload.get("status") or (entry.get("summary") if isinstance(entry.get("summary"), dict) else {}).get("status"),
            "steps_count": len(list(payload.get("steps") or [])) if isinstance(payload, dict) else None,
            "pack_path": entry.get("path"),
        }
    rows = _read_jsonl(root / PACKS_PULSE_PATH)
    for row in reversed(rows):
        row_incident = _optional_str(row.get("incident_id"))
        row_trace = _optional_str(row.get("governance_trace_id"))
        if incident_id and row_incident == incident_id:
            return row
        if governance_trace_id and row_trace == governance_trace_id:
            return row
    return None


def latest_run_for_pack(repo_root: Path, *, pack_id: str) -> dict[str, object] | None:
    root = repo_root.resolve()
    if not isinstance(pack_id, str) or not _PACK_ID_RE.fullmatch(pack_id):
        return _invalid_run_projection(pack_id, "pack_id_invalid")
    run_dir = root / RUNS_DIR
    intent_dir = root / INTENTS_DIR
    names: tuple[str, ...] = ()
    intent_names: tuple[str, ...] = ()
    for directory, destination in ((run_dir, "runs"), (intent_dir, "intents")):
        try:
            found = _bounded_run_names(directory)
        except (PrivateFileCustodyError, WindowsHandleCustodyError) as exc:
            if _custody_code(exc) not in {"directory_root_missing", "explicit_file_missing"}:
                return _invalid_run_projection(pack_id, _custody_code(exc))
            found = ()
        if destination == "runs":
            names = found
        else:
            intent_names = found
    suffix = f"_{pack_id}.json"
    candidates = sorted(name for name in names if name.startswith("run_") and name.endswith(suffix))
    intent_suffix = f"_{pack_id}.json"
    intent_candidates = sorted(name for name in intent_names
        if name.startswith("intent_") and name.endswith(intent_suffix))
    if not candidates and not intent_candidates:
        return None

    # Intent is published before the first remediation command. The latest
    # intent shadows prior completed reports until its exact final report is
    # durably available and bound back to the intent bytes.
    selected_intent: dict[str, object] | None = None
    selected_intent_name: str | None = None
    selected_intent_digest: str | None = None
    if intent_candidates:
        selected_intent_name = intent_candidates[-1]
        if not _INTENT_FILE_RE.fullmatch(selected_intent_name):
            return _invalid_run_projection(pack_id, "run_intent_filename_invalid",
                report_path=(INTENTS_DIR / selected_intent_name).as_posix())
    try:
        pack_path = root / PACKS_DIR / f"pack_{pack_id}.json"
        pack_bytes = _read_bounded_file(pack_path, max_bytes=MAX_REMEDIATION_PACK_BYTES)
        pack = _strict_json_object(pack_bytes)
        pack, _warnings = normalize(pack, SchemaName.REMEDIATION_PACK)
    except (OSError, ValueError, UnicodeError, SchemaCompatibilityError,
            PrivateFileCustodyError, WindowsHandleCustodyError) as exc:
        report_path = (INTENTS_DIR / selected_intent_name).as_posix() if selected_intent_name else None
        return _invalid_run_projection(pack_id, _custody_code(exc), report_path=report_path)

    expected_pack_path = str((PACKS_DIR / f"pack_{pack_id}.json").as_posix())
    if pack.get("pack_id") != pack_id:
        return _invalid_run_projection(pack_id, "pack_identity_mismatch")
    if selected_intent_name is not None:
        intent_relative = (INTENTS_DIR / selected_intent_name).as_posix()
        try:
            intent_bytes = _read_bounded_file(intent_dir / selected_intent_name,
                max_bytes=MAX_REMEDIATION_RUN_BYTES)
            selected_intent = _strict_json_object(intent_bytes)
            selected_intent_digest = hashlib.sha256(intent_bytes).hexdigest()
        except (OSError, ValueError, UnicodeError, PrivateFileCustodyError,
                WindowsHandleCustodyError) as exc:
            return _invalid_run_projection(pack_id, _custody_code(exc), report_path=intent_relative)
        code = _validate_remediation_intent(selected_intent, name=selected_intent_name,
            pack_id=pack_id, pack_path=expected_pack_path, pack=pack, pack_bytes=pack_bytes)
        if code is not None:
            return _invalid_run_projection(pack_id, code, report_path=intent_relative)
        expected_run_name = str(selected_intent["run_id"]) + ".json"
        if expected_run_name not in candidates:
            return _invalid_run_projection(pack_id, "run_interrupted_without_final_report",
                report_path=intent_relative)
        if candidates[-1] != expected_run_name:
            return _invalid_run_projection(pack_id, "run_report_conflicts_with_latest_intent",
                report_path=(RUNS_DIR / candidates[-1]).as_posix())
        name = expected_run_name
    else:
        # Historical reports remain readable when no intent exists.
        name = candidates[-1]
    relative = (RUNS_DIR / name).as_posix()
    if not _RUN_FILE_RE.fullmatch(name):
        return _invalid_run_projection(pack_id, "run_filename_invalid", report_path=relative)
    try:
        run_bytes = _read_bounded_file(run_dir / name, max_bytes=MAX_REMEDIATION_RUN_BYTES)
        payload = _strict_json_object(run_bytes)
    except (OSError, ValueError, UnicodeError, PrivateFileCustodyError,
            WindowsHandleCustodyError) as exc:
        return _invalid_run_projection(pack_id, _custody_code(exc), report_path=relative)
    code = _validate_remediation_run(payload, name=name, pack_id=pack_id,
        pack_path=expected_pack_path,
        pack=pack, pack_bytes=pack_bytes)
    if code is None and selected_intent is not None:
        if (payload.get("intent_id") != selected_intent.get("intent_id")
                or payload.get("intent_sha256") != selected_intent_digest):
            code = "run_intent_binding_mismatch"
    elif code is None and (payload.get("intent_id") is not None or payload.get("intent_sha256") is not None):
        code = "run_intent_missing"
    if code is not None:
        invalid = dict(payload)
        invalid["status"] = "invalid"
        invalid["custody_status"] = "invalid:" + code
        invalid["report_path"] = relative
        return invalid
    payload["custody_status"] = "locally_reconciled"
    payload["report_path"] = relative
    # This field names the limit: filesystem custody and internal consistency
    # do not authenticate the runner or independently prove external effects.
    payload["execution_authenticity"] = "owner_report_not_independently_authenticated"
    return payload


def _validate_remediation_intent(payload: dict[str, object], *, name: str,
        pack_id: str, pack_path: str, pack: dict[str, object], pack_bytes: bytes) -> str | None:
    match = _INTENT_FILE_RE.fullmatch(name)
    if match is None:
        return "run_intent_filename_invalid"
    stamp = match.group(1)
    intent_id = name[:-5]
    expected_run_id = f"run_{stamp}_{pack_id}"
    if (type(payload.get("schema_version")) is not int or payload.get("schema_version") != 1
            or payload.get("intent_id") != intent_id or payload.get("run_id") != expected_run_id
            or payload.get("pack_id") != pack_id or pack.get("pack_id") != pack_id
            or payload.get("pack_path") != pack_path
            or payload.get("pack_sha256") != hashlib.sha256(pack_bytes).hexdigest()
            or payload.get("incident_id") != pack.get("incident_id")
            or payload.get("governance_trace_id") != pack.get("governance_trace_id")
            or payload.get("status") != "started"):
        return "run_intent_identity_mismatch"
    started_at = payload.get("started_at")
    if not isinstance(started_at, str):
        return "run_intent_time_missing"
    try:
        parsed = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return "run_intent_time_invalid"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "run_intent_time_invalid"
    steps = pack.get("steps")
    if not isinstance(steps, list) or payload.get("step_count") != len(steps) or type(payload.get("step_count")) is not int:
        return "run_intent_step_count_mismatch"
    step_bytes = json.dumps(steps, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if payload.get("steps_sha256") != hashlib.sha256(step_bytes).hexdigest():
        return "run_intent_steps_digest_mismatch"
    return None


def remediation_status_for_pack(repo_root: Path, *, pack_id: str) -> tuple[str, dict[str, object] | None]:
    run_payload = latest_run_for_pack(repo_root, pack_id=pack_id)
    if run_payload is None:
        return ("missing", None)
    if str(run_payload.get("custody_status", "")).startswith("invalid:"):
        return ("invalid", run_payload)
    return ("completed" if str(run_payload.get("status")) == "completed" else "failed", run_payload)


def _bounded_run_names(path: Path) -> tuple[str, ...]:
    if os.name == "nt":
        rows = read_regular_files(path, max_entries=MAX_REMEDIATION_RUN_FILES,
            max_file_bytes=MAX_REMEDIATION_RUN_BYTES, max_total_bytes=MAX_REMEDIATION_RUN_BYTES,
            suffix=".json")
        return tuple(name for name, _data in rows)
    directory_fd = open_private_directory(path, create=False)
    try:
        return list_bounded_json_names_at(directory_fd, max_entries=MAX_REMEDIATION_RUN_FILES,
            max_directory_entries=MAX_REMEDIATION_RUN_FILES * 4)
    finally:
        os.close(directory_fd)


def _read_bounded_file(path: Path, *, max_bytes: int) -> bytes:
    if os.name == "nt":
        return read_explicit_file(path, max_bytes=max_bytes)
    directory_fd = open_private_directory(path.parent, create=False)
    try:
        return read_private_file_at(directory_fd, path.name, max_bytes=max_bytes,
            require_private_mode=False)
    finally:
        os.close(directory_fd)


def _strict_json_object(data: bytes) -> dict[str, object]:
    if type(data) is not bytes or len(data) > max(MAX_REMEDIATION_RUN_BYTES, MAX_REMEDIATION_PACK_BYTES):
        raise ValueError("artifact_size_invalid")

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        output: dict[str, object] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("duplicate_json_key")
            output[key] = value
        return output

    value = json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=unique_pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("invalid_json_constant")))
    if not isinstance(value, dict):
        raise ValueError("json_object_required")
    return value


def _validate_remediation_run(payload: dict[str, object], *, name: str, pack_id: str,
        pack_path: str, pack: dict[str, object], pack_bytes: bytes) -> str | None:
    run_id = payload.get("run_id")
    expected_id = name[:-5]
    if (type(payload.get("schema_version")) is not int or payload.get("schema_version") != 1
            or run_id != expected_id or payload.get("pack_id") != pack_id
            or payload.get("pack_path") != pack_path):
        return "run_identity_mismatch"
    if pack.get("pack_id") != pack_id:
        return "pack_identity_mismatch"
    if payload.get("incident_id") != pack.get("incident_id"):
        return "run_incident_mismatch"
    if payload.get("pack_sha256") is not None and payload.get("pack_sha256") != hashlib.sha256(pack_bytes).hexdigest():
        return "run_pack_digest_mismatch"
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        return "run_time_missing"
    try:
        parsed_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return "run_time_invalid"
    if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
        return "run_time_invalid"
    expected_steps = pack.get("steps")
    actual_steps = payload.get("steps")
    if not isinstance(expected_steps, list) or not isinstance(actual_steps, list):
        return "run_steps_missing"
    if len(actual_steps) > len(expected_steps):
        return "run_steps_exceed_pack"
    completed = payload.get("status") == "completed"
    if completed and (len(expected_steps) == 0 or len(actual_steps) != len(expected_steps)):
        return "completed_run_steps_incomplete"
    failed_seen = False
    for index, (expected, actual) in enumerate(zip(expected_steps, actual_steps)):
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            return "run_step_invalid"
        expected_name = expected.get("name") if isinstance(expected.get("name"), str) else f"step_{index}"
        command = expected.get("command")
        if (actual.get("index") != index or type(actual.get("index")) is not int
                or actual.get("name") != expected_name or actual.get("command") != command
                or not isinstance(command, str) or len(command) > 4096):
            return "run_step_identity_mismatch"
        allowed, exit_code, step_status = actual.get("allowed"), actual.get("exit_code"), actual.get("status")
        if type(allowed) is not bool or type(exit_code) is not int:
            return "run_step_result_invalid"
        success = allowed and exit_code == 0 and step_status == "ok"
        failure = (not allowed or exit_code != 0) and step_status == "failed"
        if not success and not failure:
            return "run_step_result_inconsistent"
        if failed_seen:
            return "run_steps_after_failure"
        if failure:
            failed_seen = True
        stderr = actual.get("stderr")
        if stderr is not None and (not isinstance(stderr, str) or len(stderr.encode("utf-8")) > 16_384):
            return "run_step_stderr_invalid"
    if completed and failed_seen:
        return "completed_run_contains_failure"
    if payload.get("status") not in {"completed", "failed"}:
        return "run_status_invalid"
    return None


def _invalid_run_projection(pack_id: object, code: str, *, report_path: str | None = None) -> dict[str, object]:
    return {"run_id": None, "pack_id": pack_id, "status": "invalid",
        "report_path": report_path, "custody_status": "invalid:" + code,
        "execution_authenticity": "owner_report_not_independently_authenticated"}


def _custody_code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    return str(code or str(exc) or type(exc).__name__)


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
