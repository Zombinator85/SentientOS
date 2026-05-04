from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping, Sequence

from sentientos.embodiment_proposals import embodied_proposal_ref
from sentientos.embodiment_proposal_review import classify_embodied_proposal_review_outcome, embodied_proposal_review_receipt_ref

SCHEMA_VERSION = "embodiment.proposal.handoff_candidate.v1"

_HANDOFF_KIND_BY_PROPOSAL_KIND = {
    "memory_ingress_candidate": "memory_ingress_handoff_candidate",
    "feedback_action_candidate": "feedback_action_handoff_candidate",
    "screen_retention_candidate": "screen_retention_handoff_candidate",
    "vision_retention_candidate": "vision_retention_handoff_candidate",
    "multimodal_retention_candidate": "multimodal_retention_handoff_candidate",
    "operator_attention_candidate": "operator_attention_handoff_candidate",
}


def embodied_handoff_candidate_ref(record: Mapping[str, Any]) -> str:
    return f"handoff_candidate:{record['handoff_candidate_id']}"


def classify_embodied_handoff_candidate_kind(proposal_kind: str) -> str:
    return _HANDOFF_KIND_BY_PROPOSAL_KIND.get(str(proposal_kind or ""), "unsupported_handoff_candidate")


def _latest_review_receipts(review_receipts: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, tuple[float, str, Mapping[str, Any]]] = {}
    for row in review_receipts:
        pid = str(row.get("proposal_id") or "")
        if not pid:
            continue
        created_at = float(row.get("created_at") or 0.0)
        receipt_id = str(row.get("review_receipt_id") or "")
        cur = latest.get(pid)
        if cur is None or (created_at, receipt_id) >= (cur[0], cur[1]):
            latest[pid] = (created_at, receipt_id, row)
    return {k: v[2] for k, v in latest.items()}


def filter_review_approved_embodied_proposals(*, proposals: Sequence[Mapping[str, Any]], review_receipts: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    latest = _latest_review_receipts(review_receipts)
    approved: list[Mapping[str, Any]] = []
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "")
        review = latest.get(pid)
        if not review:
            continue
        if classify_embodied_proposal_review_outcome(str(review.get("review_outcome") or "pending_review")) == "reviewed_approved_for_next_stage":
            approved.append(proposal)
    return approved


def build_embodied_handoff_candidate(*, proposal_record: Mapping[str, Any], review_receipt: Mapping[str, Any], created_at: float | None = None) -> dict[str, Any]:
    proposal_kind = str(proposal_record.get("proposal_kind") or "unknown")
    handoff_kind = classify_embodied_handoff_candidate_kind(proposal_kind)
    review_outcome = classify_embodied_proposal_review_outcome(str(review_receipt.get("review_outcome") or "pending_review"))

    posture = {
        "pending_review": "blocked_missing_review",
        "reviewed_rejected": "blocked_rejected",
        "reviewed_deferred": "blocked_deferred",
        "reviewed_needs_more_context": "blocked_needs_more_context",
        "reviewed_approved_for_next_stage": "eligible_for_next_stage_review",
    }[review_outcome]
    if handoff_kind == "unsupported_handoff_candidate":
        posture = "blocked_unsupported_kind"

    material = {
        "proposal_id": proposal_record.get("proposal_id"),
        "review_receipt_id": review_receipt.get("review_receipt_id"),
        "handoff_kind": handoff_kind,
        "posture": posture,
    }
    candidate_id = "ehc_" + hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]

    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_candidate_id": candidate_id,
        "handoff_candidate_kind": handoff_kind,
        "source_proposal_id": proposal_record.get("proposal_id"),
        "source_proposal_ref": embodied_proposal_ref(proposal_record),
        "source_review_receipt_id": review_receipt.get("review_receipt_id"),
        "source_review_receipt_ref": embodied_proposal_review_receipt_ref(review_receipt),
        "source_ingress_receipt_ref": proposal_record.get("ingress_receipt_ref"),
        "source_event_refs": list(proposal_record.get("source_event_refs") or []),
        "source_snapshot_ref": proposal_record.get("source_snapshot_ref"),
        "correlation_id": proposal_record.get("correlation_id") or review_receipt.get("correlation_id"),
        "source_module": proposal_record.get("source_module"),
        "proposal_kind": proposal_kind,
        "review_outcome": "reviewed_approved_for_next_stage" if posture == "eligible_for_next_stage_review" else review_outcome,
        "handoff_posture": posture,
        "risk_flags": dict(proposal_record.get("risk_flags") or {}),
        "privacy_retention_posture": proposal_record.get("privacy_retention_posture", "review"),
        "consent_posture": proposal_record.get("consent_posture", "not_asserted"),
        "candidate_payload_summary": dict(proposal_record.get("candidate_payload_summary") or {}),
        "rationale": list(proposal_record.get("rationale") or []),
        "created_at": float(created_at if created_at is not None else time.time()),
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "approval_is_not_execution": True,
        "handoff_is_not_fulfillment": True,
    }


def resolve_embodied_handoff_candidates(*, proposals: Sequence[Mapping[str, Any]], review_receipts: Sequence[Mapping[str, Any]], created_at: float | None = None) -> dict[str, Any]:
    latest = _latest_review_receipts(review_receipts)
    candidates: list[dict[str, Any]] = []
    by_kind: dict[str, int] = {}
    by_posture: dict[str, int] = {}
    for proposal in proposals:
        pid = str(proposal.get("proposal_id") or "")
        review = latest.get(pid)
        if not review:
            continue
        candidate = build_embodied_handoff_candidate(proposal_record=proposal, review_receipt=review, created_at=created_at)
        posture = str(candidate["handoff_posture"])
        by_posture[posture] = by_posture.get(posture, 0) + 1
        if posture == "eligible_for_next_stage_review":
            kind = str(candidate["handoff_candidate_kind"])
            by_kind[kind] = by_kind.get(kind, 0) + 1
            candidates.append(candidate)
    return {
        "handoff_candidates": candidates,
        "counts_by_proposal_kind": dict(sorted(by_kind.items())),
        "counts_by_handoff_posture": dict(sorted(by_posture.items())),
    }


def summarize_embodied_handoff_candidates(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    blocked: dict[str, int] = {}
    for row in candidates:
        kind = str(row.get("handoff_candidate_kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        posture = str(row.get("handoff_posture") or "")
        if posture != "eligible_for_next_stage_review":
            blocked[posture] = blocked.get(posture, 0) + 1
    return {
        "handoff_candidate_count": len(candidates),
        "handoff_counts_by_kind": dict(sorted(by_kind.items())),
        "blocked_handoff_counts_by_reason": dict(sorted(blocked.items())),
    }


__all__ = [
    "SCHEMA_VERSION",
    "build_embodied_handoff_candidate",
    "resolve_embodied_handoff_candidates",
    "embodied_handoff_candidate_ref",
    "classify_embodied_handoff_candidate_kind",
    "summarize_embodied_handoff_candidates",
    "filter_review_approved_embodied_proposals",
]
