from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from sentientos.audit_chain_gate import verify_audit_chain


@dataclass(frozen=True)
class AuditTrustState:
    schema_version: int
    evaluated_at: str
    context: str
    status: str
    history_state: str
    degraded_audit_trust: bool
    checkpoint_id: str | None
    continuation_descends_from_anchor: bool | None
    trust_boundary_explicit: bool
    trusted_history_head_hash: str | None
    report_break_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "evaluated_at": self.evaluated_at,
            "context": self.context,
            "status": self.status,
            "history_state": self.history_state,
            "degraded_audit_trust": self.degraded_audit_trust,
            "checkpoint_id": self.checkpoint_id,
            "continuation_descends_from_anchor": self.continuation_descends_from_anchor,
            "trust_boundary_explicit": self.trust_boundary_explicit,
            "trusted_history_head_hash": self.trusted_history_head_hash,
            "report_break_count": self.report_break_count,
        }


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _runtime_dir(repo_root: Path) -> Path:
    return repo_root / "glow" / "runtime"


def evaluate_audit_trust(repo_root: Path, *, context: str) -> AuditTrustState:
    report = verify_audit_chain(repo_root)
    recovery = report.recovery_state or {}
    history_state = str(recovery.get("history_state") or "unknown")
    degraded = bool(recovery.get("degraded_audit_trust", True))
    checkpoint_id = recovery.get("checkpoint_id")
    continuation_descends = recovery.get("continuation_descends_from_anchor")
    trust_boundary_explicit = bool(recovery.get("trust_boundary_explicit", False))
    return AuditTrustState(
        schema_version=1,
        evaluated_at=_iso_now(),
        context=context,
        status=report.status,
        history_state=history_state,
        degraded_audit_trust=degraded,
        checkpoint_id=str(checkpoint_id) if checkpoint_id else None,
        continuation_descends_from_anchor=bool(continuation_descends) if continuation_descends is not None else None,
        trust_boundary_explicit=trust_boundary_explicit,
        trusted_history_head_hash=report.trusted_history_head_hash,
        report_break_count=report.break_count,
    )


def _state_signature(payload: dict[str, Any]) -> str:
    canonical = {
        "status": payload.get("status"),
        "history_state": payload.get("history_state"),
        "degraded_audit_trust": payload.get("degraded_audit_trust"),
        "checkpoint_id": payload.get("checkpoint_id"),
        "continuation_descends_from_anchor": payload.get("continuation_descends_from_anchor"),
        "trust_boundary_explicit": payload.get("trust_boundary_explicit"),
        "trusted_history_head_hash": payload.get("trusted_history_head_hash"),
        "report_break_count": payload.get("report_break_count"),
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def write_audit_trust_artifacts(repo_root: Path, state: AuditTrustState, *, actor: str) -> dict[str, str]:
    runtime_dir = _runtime_dir(repo_root)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = runtime_dir / "audit_trust_state.json"
    transitions_path = runtime_dir / "audit_trust_transitions.jsonl"
    decisions_path = runtime_dir / "audit_trust_decisions.jsonl"

    payload = state.to_dict()
    signature = _state_signature(payload)
    payload["state_signature"] = signature
    payload["actor"] = actor

    snapshot_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    previous_signature: str | None = None
    if transitions_path.exists():
        for line in transitions_path.read_text(encoding="utf-8", errors="replace").splitlines()[::-1]:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and isinstance(row.get("state_signature"), str):
                previous_signature = row["state_signature"]
                break

    transition_kind = "unchanged" if previous_signature == signature else "changed"
    transition_row = {
        "timestamp": _iso_now(),
        "event": "audit_trust_transition",
        "transition": transition_kind,
        "previous_state_signature": previous_signature,
        "state_signature": signature,
        "actor": actor,
        "context": state.context,
        "degraded_audit_trust": state.degraded_audit_trust,
        "history_state": state.history_state,
        "checkpoint_id": state.checkpoint_id,
    }
    with transitions_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(transition_row, sort_keys=True) + "\n")

    decision_row = {
        "timestamp": _iso_now(),
        "event": "audit_trust_observation",
        "actor": actor,
        "context": state.context,
        "state_signature": signature,
        "degraded_audit_trust": state.degraded_audit_trust,
        "history_state": state.history_state,
        "status": state.status,
    }
    with decisions_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision_row, sort_keys=True) + "\n")

    return {
        "snapshot": str(snapshot_path.relative_to(repo_root)),
        "transitions": str(transitions_path.relative_to(repo_root)),
        "decisions": str(decisions_path.relative_to(repo_root)),
    }


__all__ = [
    "AuditTrustState",
    "evaluate_audit_trust",
    "write_audit_trust_artifacts",
]
