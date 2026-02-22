from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Protocol

from sentientos.audit_chain_gate import maybe_verify_audit_chain
from sentientos.doctrine_identity import verify_doctrine_identity
from sentientos.event_stream import record_forge_event
from sentientos.federation_integrity import federation_integrity_gate
from sentientos.receipt_anchors import maybe_verify_receipt_anchors
from sentientos.receipt_chain import maybe_verify_receipt_chain
from sentientos.remediation_pack import latest_run_for_pack
from sentientos.schema_registry import SchemaCompatibilityError, SchemaName, normalize
from scripts import run_remediation_pack

ATTEMPTS_PATH = Path("pulse/auto_remediation_attempts.jsonl")


@dataclass(frozen=True)
class AutoRemediationDecision:
    status: str
    reason: str


@dataclass(frozen=True)
class AutoRemediationResult:
    status: str
    reason: str
    attempted: bool
    run_id: str | None = None
    pack_id: str | None = None
    gate_results: list[dict[str, object]] | None = None


def maybe_auto_run_pack(
    repo_root: Path,
    *,
    operating_mode: str,
    context: str,
    pack: dict[str, object],
    governance_trace_id: str,
    incident_id: str | None,
) -> AutoRemediationResult:
    root = repo_root.resolve()
    pack_id = _optional_str(pack.get("pack_id"))
    pack_path = _optional_str(pack.get("pack_path"))
    if pack_id is None or pack_path is None:
        return AutoRemediationResult(status="failed", reason="missing_pack_metadata", attempted=False)

    decision = should_auto_run_pack(root, operating_mode=operating_mode, pack=pack, incident_id=incident_id, governance_trace_id=governance_trace_id)
    if decision.status != "run":
        return AutoRemediationResult(status=decision.status, reason=decision.reason, attempted=False, pack_id=pack_id)

    record_forge_event({"event": "auto_remediation_run_started", "pack_id": pack_id, "trace_id": governance_trace_id, "incident_id": incident_id, "context": context, "operating_mode": operating_mode})
    report = run_remediation_pack.execute_pack_file(root / pack_path, root=root)
    run_id = _optional_str(report.get("run_id"))
    status = str(report.get("status") or "failed")
    _append_attempt(
        root,
        {
            "attempted_at": _iso_now(),
            "pack_id": pack_id,
            "pack_path": pack_path,
            "governance_trace_id": governance_trace_id,
            "incident_id": incident_id,
            "run_id": run_id,
            "status": status,
        },
    )
    record_forge_event({"event": "auto_remediation_run_finished", "pack_id": pack_id, "run_id": run_id, "trace_id": governance_trace_id, "incident_id": incident_id, "context": context, "status": status})

    gate_results: list[dict[str, object]] = []
    if status == "completed":
        gate_results = _reevaluate_gates(root, context=context, reasons=[str(item) for item in list(pack.get("reason_stack") or []) if isinstance(item, str)])
        return AutoRemediationResult(status="succeeded", reason="run_completed", attempted=True, run_id=run_id, pack_id=pack_id, gate_results=gate_results)
    return AutoRemediationResult(status="failed", reason="run_failed", attempted=True, run_id=run_id, pack_id=pack_id)


def should_auto_run_pack(repo_root: Path, *, operating_mode: str, pack: dict[str, object], incident_id: str | None, governance_trace_id: str) -> AutoRemediationDecision:
    _ = governance_trace_id
    allow_cautious = os.getenv("SENTIENTOS_AUTO_REMEDIATION_ALLOW_CAUTIOUS", "0") == "1"
    if operating_mode not in {"recovery"} and not (allow_cautious and operating_mode == "cautious"):
        return AutoRemediationDecision(status="idle", reason="mode_not_allowed")

    pack_id = _optional_str(pack.get("pack_id"))
    pack_path = _optional_str(pack.get("pack_path"))
    if pack_id is None or pack_path is None:
        return AutoRemediationDecision(status="failed", reason="pack_missing")
    pack_payload = _load_json(repo_root / pack_path)
    try:
        pack_payload, _warnings = normalize(pack_payload, SchemaName.REMEDIATION_PACK)
    except SchemaCompatibilityError:
        return AutoRemediationDecision(status="failed", reason="schema_too_old:remediation_pack")
    steps = list(pack_payload.get("steps") or [])
    if not steps:
        return AutoRemediationDecision(status="idle", reason="no_steps")
    for step in steps:
        if not isinstance(step, dict):
            return AutoRemediationDecision(status="failed", reason="invalid_step")
        if bool(step.get("destructive", True)):
            return AutoRemediationDecision(status="idle", reason="contains_destructive_step")
        if not bool(step.get("allowlisted", False)):
            return AutoRemediationDecision(status="idle", reason="contains_non_allowlisted_step")

    latest_run = latest_run_for_pack(repo_root, pack_id=pack_id)
    if latest_run is not None and str(latest_run.get("status")) == "completed":
        return AutoRemediationDecision(status="succeeded", reason="already_succeeded")

    attempts = _read_jsonl(repo_root / ATTEMPTS_PATH)
    related = [row for row in attempts if _optional_str(row.get("pack_id")) == pack_id]
    if incident_id:
        related.extend(row for row in attempts if _optional_str(row.get("incident_id")) == incident_id and row not in related)

    max_attempts = max(1, int(os.getenv("SENTIENTOS_AUTO_REMEDIATION_MAX_ATTEMPTS", "2")))
    if len(related) >= max_attempts:
        return AutoRemediationDecision(status="failed", reason="max_attempts_reached")

    cooldown_minutes = max(1, int(os.getenv("SENTIENTOS_AUTO_REMEDIATION_COOLDOWN_MINUTES", "60")))
    if related:
        latest_at = _parse_iso(max(str(row.get("attempted_at") or "") for row in related))
        if latest_at is not None and datetime.now(timezone.utc) - latest_at < timedelta(minutes=cooldown_minutes):
            return AutoRemediationDecision(status="cooldown", reason="cooldown_active")
    return AutoRemediationDecision(status="run", reason="eligible")


def _reevaluate_gates(root: Path, *, context: str, reasons: list[str]) -> list[dict[str, object]]:
    gate_rows: list[dict[str, object]] = []
    required: set[str] = set()
    if any(reason in {"audit_chain_broken", "quarantine_active"} for reason in reasons):
        required.add("audit")
    if "receipt_chain_broken" in reasons:
        required.add("receipt")
    if any(reason in {"receipt_anchor_invalid", "receipt_anchor_missing"} for reason in reasons):
        required.add("anchor")
    if "federation_integrity_diverged" in reasons:
        required.add("federation")
    if "doctrine_identity_mismatch" in reasons:
        required.add("doctrine")

    for gate in sorted(required):
        runner = _GATE_RUNNERS[gate]
        gate_rows.append(runner(root, context=context))
    return gate_rows


def _run_audit_gate(root: Path, *, context: str) -> dict[str, object]:
    check, _enforced, _warned, report = maybe_verify_audit_chain(root, context=context)
    return {"name": "audit_chain", "result": "pass" if bool(check and check.valid) else "fail", "reason": "auto_remediation_recheck", "evidence_paths": [report] if report else []}


def _run_receipt_gate(root: Path, *, context: str) -> dict[str, object]:
    check, _enforced, _warned = maybe_verify_receipt_chain(root, context=context)
    return {"name": "receipt_chain", "result": "pass" if bool(check and check.valid) else "fail", "reason": "auto_remediation_recheck"}


def _run_anchor_gate(root: Path, *, context: str) -> dict[str, object]:
    check, _enforced, _warned = maybe_verify_receipt_anchors(root, context=context)
    return {"name": "receipt_anchor", "result": "pass" if bool(check and check.valid) else "fail", "reason": "auto_remediation_recheck"}


def _run_federation_gate(root: Path, *, context: str) -> dict[str, object]:
    payload = federation_integrity_gate(root, context=context)
    blocked = bool(payload.get("blocked", False))
    return {"name": "federation_integrity", "result": "fail" if blocked else "pass", "reason": "auto_remediation_recheck"}


def _run_doctrine_gate(root: Path, *, context: str) -> dict[str, object]:
    _ = context
    ok, payload = verify_doctrine_identity(root)
    return {"name": "doctrine_identity", "result": "pass" if ok else "fail", "reason": "auto_remediation_recheck", "detail": payload}


class _GateRunner(Protocol):
    def __call__(self, root: Path, *, context: str) -> dict[str, object]: ...


_GATE_RUNNERS: dict[str, _GateRunner] = {
    "audit": _run_audit_gate,
    "receipt": _run_receipt_gate,
    "anchor": _run_anchor_gate,
    "federation": _run_federation_gate,
    "doctrine": _run_doctrine_gate,
}


def _append_attempt(repo_root: Path, row: dict[str, object]) -> None:
    path = repo_root / ATTEMPTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


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


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
