from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping, Sequence

from sentientos.embodiment_fulfillment import embodied_fulfillment_candidate_ref, embodied_fulfillment_receipt_ref

VALIDATION_SCHEMA_VERSION = "embodiment.action_ingress_validation.v1"
SUPPORTED_FULFILLMENT_KIND = "feedback_action_fulfillment_candidate"

ALLOWED_OUTCOMES = {
    "action_ingress_validated_for_future_trigger",
    "action_ingress_blocked_missing_consent",
    "action_ingress_blocked_missing_provenance",
    "action_ingress_blocked_unsafe_action",
    "action_ingress_blocked_high_risk_action",
    "action_ingress_blocked_privacy_sensitive",
    "action_ingress_blocked_unsupported_kind",
    "action_ingress_needs_more_context",
}


def action_ingress_validation_ref(record: Mapping[str, Any]) -> str:
    return f"action_ingress_validation:{record['action_ingress_validation_id']}"


def classify_action_ingress_validation_outcome(candidate: Mapping[str, Any]) -> str:
    kind = str(candidate.get("fulfillment_candidate_kind") or "")
    if kind != SUPPORTED_FULFILLMENT_KIND:
        return "action_ingress_blocked_unsupported_kind"

    if not all([
        candidate.get("fulfillment_candidate_id"),
        candidate.get("source_governance_bridge_candidate_ref"),
        candidate.get("source_handoff_candidate_ref"),
        candidate.get("source_proposal_id"),
        candidate.get("source_review_receipt_id"),
    ]):
        return "action_ingress_blocked_missing_provenance"

    consent_posture = str(candidate.get("consent_posture") or "")
    if consent_posture in {"", "unknown", "not_asserted", "required"}:
        return "action_ingress_blocked_missing_consent"
    if consent_posture in {"review", "conditional"}:
        return "action_ingress_needs_more_context"

    risk_flags = dict(candidate.get("risk_flags") or {})
    privacy_posture = str(candidate.get("privacy_retention_posture") or "")
    if privacy_posture in {"sensitive", "restricted"} and not bool(risk_flags.get("allow_privacy_sensitive_action_ingress")):
        return "action_ingress_blocked_privacy_sensitive"

    candidate_payload = dict(candidate.get("candidate_payload_summary") or {})
    requires_operator_confirmation = bool(
        candidate_payload.get("requires_operator_confirmation")
        or risk_flags.get("requires_operator_confirmation")
    )
    operator_confirmed = bool(
        candidate_payload.get("operator_confirmation_present")
        or risk_flags.get("operator_confirmation_present")
    )
    if requires_operator_confirmation and not operator_confirmed:
        return "action_ingress_needs_more_context"

    unsafe_requested = bool(
        risk_flags.get("unsafe_action")
        or risk_flags.get("action_dangerous")
        or risk_flags.get("external_side_effect")
        or candidate_payload.get("external_side_effect")
    )
    if unsafe_requested and not bool(risk_flags.get("allow_unsafe_action_ingress")):
        return "action_ingress_blocked_unsafe_action"

    high_risk = bool(risk_flags.get("high_risk_action") or risk_flags.get("action_high_risk"))
    if high_risk and not bool(risk_flags.get("allow_high_risk_action_ingress")):
        return "action_ingress_blocked_high_risk_action"

    return "action_ingress_validated_for_future_trigger"


def build_action_ingress_validation_record(*, feedback_action_fulfillment_candidate: Mapping[str, Any], validation_outcome: str | None = None, source_fulfillment_receipt: Mapping[str, Any] | None = None, created_at: float | None = None) -> dict[str, Any]:
    outcome = validation_outcome or classify_action_ingress_validation_outcome(feedback_action_fulfillment_candidate)
    if outcome not in ALLOWED_OUTCOMES:
        outcome = "action_ingress_needs_more_context"

    material = {
        "source_fulfillment_candidate_id": feedback_action_fulfillment_candidate.get("fulfillment_candidate_id"),
        "validation_outcome": outcome,
        "source_review_receipt_id": feedback_action_fulfillment_candidate.get("source_review_receipt_id"),
    }
    validation_id = "aiv_" + hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    payload = dict(feedback_action_fulfillment_candidate.get("candidate_payload_summary") or {})
    risk_flags = dict(feedback_action_fulfillment_candidate.get("risk_flags") or {})
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "action_ingress_validation_id": validation_id,
        "source_fulfillment_candidate_id": feedback_action_fulfillment_candidate.get("fulfillment_candidate_id"),
        "source_fulfillment_candidate_ref": embodied_fulfillment_candidate_ref(feedback_action_fulfillment_candidate),
        "source_governance_bridge_candidate_ref": feedback_action_fulfillment_candidate.get("source_governance_bridge_candidate_ref"),
        "source_handoff_candidate_ref": feedback_action_fulfillment_candidate.get("source_handoff_candidate_ref"),
        "source_proposal_id": feedback_action_fulfillment_candidate.get("source_proposal_id"),
        "source_review_receipt_id": feedback_action_fulfillment_candidate.get("source_review_receipt_id"),
        "source_ingress_receipt_ref": feedback_action_fulfillment_candidate.get("source_ingress_receipt_ref"),
        "source_event_refs": list(feedback_action_fulfillment_candidate.get("source_event_refs") or []),
        "correlation_id": feedback_action_fulfillment_candidate.get("correlation_id"),
        "source_module": feedback_action_fulfillment_candidate.get("source_module"),
        "source_fulfillment_receipt_ref": embodied_fulfillment_receipt_ref(source_fulfillment_receipt) if source_fulfillment_receipt else None,
        "validation_outcome": outcome,
        "action_candidate_summary": payload,
        "privacy_retention_posture": feedback_action_fulfillment_candidate.get("privacy_retention_posture", "review"),
        "consent_posture": feedback_action_fulfillment_candidate.get("consent_posture", "not_asserted"),
        "risk_flags": risk_flags,
        "provenance_complete": outcome != "action_ingress_blocked_missing_provenance",
        "action_risk_class": "high" if (risk_flags.get("high_risk_action") or risk_flags.get("action_high_risk")) else ("unsafe" if (risk_flags.get("unsafe_action") or risk_flags.get("action_dangerous") or risk_flags.get("external_side_effect")) else "low"),
        "requires_operator_confirmation": bool(payload.get("requires_operator_confirmation") or risk_flags.get("requires_operator_confirmation")),
        "rationale": list(feedback_action_fulfillment_candidate.get("rationale") or []),
        "created_at": float(created_at if created_at is not None else time.time()),
        "non_authoritative": True,
        "decision_power": "none",
        "validation_is_not_action_trigger": True,
        "does_not_trigger_feedback": True,
        "does_not_execute_or_route_work": True,
        "does_not_admit_work": True,
        "does_not_write_memory": True,
        "does_not_commit_retention": True,
    }


def validate_action_fulfillment_candidate(*, feedback_action_fulfillment_candidate: Mapping[str, Any], source_fulfillment_receipt: Mapping[str, Any] | None = None, created_at: float | None = None) -> dict[str, Any]:
    return build_action_ingress_validation_record(
        feedback_action_fulfillment_candidate=feedback_action_fulfillment_candidate,
        source_fulfillment_receipt=source_fulfillment_receipt,
        created_at=created_at,
    )


def resolve_action_ingress_validations(*, fulfillment_candidates: Sequence[Mapping[str, Any]], fulfillment_receipts: Sequence[Mapping[str, Any]] | None = None, created_at: float | None = None) -> dict[str, Any]:
    receipt_by_candidate = {str(r.get("source_fulfillment_candidate_id") or ""): r for r in (fulfillment_receipts or []) if isinstance(r, Mapping)}
    rows: list[dict[str, Any]] = []
    by_outcome: dict[str, int] = {}
    for candidate in fulfillment_candidates:
        row = validate_action_fulfillment_candidate(
            feedback_action_fulfillment_candidate=candidate,
            source_fulfillment_receipt=receipt_by_candidate.get(str(candidate.get("fulfillment_candidate_id") or "")),
            created_at=created_at,
        )
        rows.append(row)
        by_outcome[row["validation_outcome"]] = by_outcome.get(row["validation_outcome"], 0) + 1
    return {
        "action_ingress_validations": rows,
        "action_ingress_validation_counts_by_outcome": dict(sorted(by_outcome.items())),
    }


def summarize_action_ingress_validation_status(*, action_ingress_validations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts_by_outcome: dict[str, int] = {}
    validated = 0
    blocked = 0
    for row in action_ingress_validations:
        outcome = str(row.get("validation_outcome") or "action_ingress_needs_more_context")
        counts_by_outcome[outcome] = counts_by_outcome.get(outcome, 0) + 1
        if outcome == "action_ingress_validated_for_future_trigger":
            validated += 1
        elif outcome.startswith("action_ingress_blocked"):
            blocked += 1

    if not action_ingress_validations:
        posture = "no_action_ingress_candidates"
    else:
        labels = []
        if blocked > 0:
            labels.append("action_ingress_blocked_items_present")
        if validated > 0:
            labels.append("action_ingress_future_trigger_candidates_present")
        posture = "mixed_action_ingress_state" if len(labels) > 1 else (labels[0] if labels else "action_ingress_validations_present")

    return {
        "action_ingress_validation_count": len(action_ingress_validations),
        "action_ingress_validation_counts_by_outcome": dict(sorted(counts_by_outcome.items())),
        "action_ingress_validated_for_future_trigger_count": validated,
        "action_ingress_blocked_count": blocked,
        "action_ingress_posture": posture,
    }


__all__ = [k for k in globals().keys() if k.startswith(("VALIDATION_", "SUPPORTED_", "ALLOWED_", "build_", "validate_", "resolve_", "classify_", "summarize_", "action_ingress_"))]
