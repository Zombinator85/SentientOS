from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.ledger_api import append_audit_record
from sentientos.embodiment_proposals import DEFAULT_PROPOSAL_LOG, embodied_proposal_ref, list_recent_embodied_proposals

SCHEMA_VERSION = "embodiment.proposal.review_receipt.v1"
DEFAULT_REVIEW_RECEIPT_LOG = Path("logs/embodiment_proposal_reviews.jsonl")

ALLOWED_REVIEW_OUTCOMES = {
    "pending_review",
    "reviewed_deferred",
    "reviewed_rejected",
    "reviewed_needs_more_context",
    "reviewed_approved_for_next_stage",
}
ALLOWED_REVIEWER_KINDS = {"operator", "system_policy", "diagnostic", "test_fixture"}


def classify_embodied_proposal_review_outcome(review_outcome: str) -> str:
    outcome = str(review_outcome or "").strip().lower()
    if outcome not in ALLOWED_REVIEW_OUTCOMES:
        raise ValueError(f"unsupported review_outcome: {review_outcome}")
    return outcome


def embodied_proposal_review_receipt_ref(record: Mapping[str, Any]) -> str:
    return f"proposal_review:{record['review_receipt_id']}"


def _review_receipt_id(material: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return f"eprr_{digest}"


def build_embodied_proposal_review_receipt(*, proposal_record: Mapping[str, Any], review_outcome: str, reviewer_kind: str,
                                           reviewer_ref: str | None = None, reviewer_label: str | None = None,
                                           review_rationale: str | None = None, source_event_refs: Sequence[str] | None = None,
                                           risk_flags: Mapping[str, Any] | None = None, correlation_id: str | None = None,
                                           created_at: float | None = None) -> dict[str, Any]:
    outcome = classify_embodied_proposal_review_outcome(review_outcome)
    reviewer_kind_normalized = str(reviewer_kind or "").strip().lower()
    if reviewer_kind_normalized not in ALLOWED_REVIEWER_KINDS:
        raise ValueError(f"unsupported reviewer_kind: {reviewer_kind}")

    proposal_ref = embodied_proposal_ref(proposal_record)
    material = {
        "proposal_id": proposal_record.get("proposal_id"),
        "proposal_ref": proposal_ref,
        "review_outcome": outcome,
        "reviewer_kind": reviewer_kind_normalized,
        "reviewer_ref": reviewer_ref,
        "reviewer_label": reviewer_label,
        "review_rationale": review_rationale,
        "correlation_id": correlation_id if correlation_id is not None else proposal_record.get("correlation_id"),
        "source_event_refs": list(source_event_refs if source_event_refs is not None else proposal_record.get("source_event_refs", [])),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "review_receipt_id": _review_receipt_id(material),
        "proposal_id": proposal_record.get("proposal_id"),
        "proposal_ref": proposal_ref,
        "proposal_kind": str(proposal_record.get("proposal_kind") or "unknown"),
        "review_outcome": outcome,
        "reviewer_kind": reviewer_kind_normalized,
        "reviewer_ref": reviewer_ref,
        "reviewer_label": reviewer_label,
        "review_rationale": review_rationale or "review_recorded",
        "source_proposal_ref": proposal_ref,
        "source_ingress_receipt_ref": proposal_record.get("ingress_receipt_ref"),
        "source_event_refs": list(source_event_refs if source_event_refs is not None else proposal_record.get("source_event_refs", [])),
        "correlation_id": correlation_id if correlation_id is not None else proposal_record.get("correlation_id"),
        "risk_flags": dict(risk_flags or proposal_record.get("risk_flags") or {}),
        "privacy_retention_posture": proposal_record.get("privacy_retention_posture", "review"),
        "consent_posture": proposal_record.get("consent_posture", "not_asserted"),
        "created_at": float(created_at if created_at is not None else time.time()),
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "approval_is_not_execution": True,
    }


def append_embodied_proposal_review_receipt(record: Mapping[str, Any], *, path: Path = DEFAULT_REVIEW_RECEIPT_LOG) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    return append_audit_record(path, record)


def list_recent_embodied_proposal_review_receipts(*, path: Path = DEFAULT_REVIEW_RECEIPT_LOG, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[-max(1, limit):]


def resolve_embodied_proposal_review_state(*, proposals: Sequence[Mapping[str, Any]], review_receipts: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    latest: dict[str, tuple[float, str, str]] = {}
    for row in review_receipts:
        pid = str(row.get("proposal_id") or "")
        if not pid:
            continue
        ts = float(row.get("created_at") or 0.0)
        rid = str(row.get("review_receipt_id") or "")
        outcome = classify_embodied_proposal_review_outcome(str(row.get("review_outcome") or "pending_review"))
        current = latest.get(pid)
        if current is None or (ts, rid) >= (current[0], current[1]):
            latest[pid] = (ts, rid, outcome)

    resolved: dict[str, str] = {}
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "")
        if not pid:
            continue
        outcome = latest.get(pid, (0.0, "", "pending_review"))[2]
        mapped = {
            "pending_review": "pending_review",
            "reviewed_deferred": "deferred",
            "reviewed_rejected": "rejected",
            "reviewed_needs_more_context": "needs_more_context",
            "reviewed_approved_for_next_stage": "approved_for_next_stage",
        }[outcome]
        resolved[pid] = mapped
    return resolved


def summarize_embodied_proposal_review_status(*, proposals: Sequence[Mapping[str, Any]], review_receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    states = resolve_embodied_proposal_review_state(proposals=proposals, review_receipts=review_receipts)
    counts = {"pending_review": 0, "approved_for_next_stage": 0, "rejected": 0, "deferred": 0, "needs_more_context": 0}
    for state in states.values():
        counts[state] = counts.get(state, 0) + 1
    high_risk_pending = 0
    by_id = {str(p.get("proposal_id") or ""): p for p in proposals}
    for pid, state in states.items():
        if state != "pending_review":
            continue
        row = by_id.get(pid, {})
        flags = row.get("risk_flags") if isinstance(row.get("risk_flags"), Mapping) else {}
        if flags.get("biometric_sensitive") or flags.get("emotion_sensitive"):
            high_risk_pending += 1

    if not proposals or counts["pending_review"] == 0:
        posture = "no_pending_review_activity"
    elif counts["pending_review"] > 0 and counts["approved_for_next_stage"] == 0 and counts["rejected"] == 0 and counts["deferred"] == 0 and counts["needs_more_context"] == 0:
        posture = "pending_review_items"
    elif counts["pending_review"] == 0 and counts["approved_for_next_stage"] > 0:
        posture = "reviewed_items_waiting_next_stage"
    elif high_risk_pending > 0:
        posture = "high_risk_review_pending"
    else:
        posture = "mixed_review_state"

    return {
        "review_counts_by_outcome": counts,
        "pending_without_review_count": counts["pending_review"],
        "approved_for_next_stage_count": counts["approved_for_next_stage"],
        "rejected_count": counts["rejected"],
        "deferred_count": counts["deferred"],
        "needs_more_context_count": counts["needs_more_context"],
        "review_posture": posture,
    }


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_REVIEW_RECEIPT_LOG",
    "ALLOWED_REVIEW_OUTCOMES",
    "build_embodied_proposal_review_receipt",
    "append_embodied_proposal_review_receipt",
    "list_recent_embodied_proposal_review_receipts",
    "embodied_proposal_review_receipt_ref",
    "classify_embodied_proposal_review_outcome",
    "resolve_embodied_proposal_review_state",
    "summarize_embodied_proposal_review_status",
    "DEFAULT_PROPOSAL_LOG",
    "list_recent_embodied_proposals",
]
