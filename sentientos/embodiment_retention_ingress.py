from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping, Sequence

from sentientos.embodiment_fulfillment import embodied_fulfillment_candidate_ref, embodied_fulfillment_receipt_ref

VALIDATION_SCHEMA_VERSION = "embodiment.retention_ingress_validation.v1"
SUPPORTED_RETENTION_CANDIDATE_KINDS = {
    "screen_retention_fulfillment_candidate",
    "vision_retention_fulfillment_candidate",
    "multimodal_retention_fulfillment_candidate",
}

ALLOWED_OUTCOMES = {
    "retention_ingress_validated_for_future_commit",
    "retention_ingress_blocked_missing_consent",
    "retention_ingress_blocked_missing_provenance",
    "retention_ingress_blocked_privacy_sensitive",
    "retention_ingress_blocked_raw_retention",
    "retention_ingress_blocked_biometric_or_emotion_sensitive",
    "retention_ingress_blocked_multimodal_context_sensitive",
    "retention_ingress_blocked_unsupported_kind",
    "retention_ingress_needs_more_context",
}


def retention_ingress_validation_ref(record: Mapping[str, Any]) -> str:
    return f"retention_ingress_validation:{record['retention_ingress_validation_id']}"


def classify_retention_ingress_validation_outcome(candidate: Mapping[str, Any]) -> str:
    kind = str(candidate.get("fulfillment_candidate_kind") or "")
    if kind not in SUPPORTED_RETENTION_CANDIDATE_KINDS:
        return "retention_ingress_blocked_unsupported_kind"

    if not all([
        candidate.get("fulfillment_candidate_id"),
        candidate.get("source_governance_bridge_candidate_ref"),
        candidate.get("source_handoff_candidate_ref"),
        candidate.get("source_proposal_id"),
        candidate.get("source_review_receipt_id"),
    ]):
        return "retention_ingress_blocked_missing_provenance"

    consent_posture = str(candidate.get("consent_posture") or "")
    if consent_posture in {"", "unknown", "not_asserted", "required"}:
        return "retention_ingress_blocked_missing_consent"
    if consent_posture in {"review", "conditional"}:
        return "retention_ingress_needs_more_context"

    risk_flags = dict(candidate.get("risk_flags") or {})
    payload = dict(candidate.get("candidate_payload_summary") or {})

    privacy_posture = str(candidate.get("privacy_retention_posture") or "")
    if privacy_posture in {"sensitive", "restricted"} and not bool(risk_flags.get("allow_privacy_sensitive_retention_ingress")):
        return "retention_ingress_blocked_privacy_sensitive"

    raw_requested = bool(risk_flags.get("raw_retention_requested") or payload.get("raw_retention_requested"))
    raw_allowed = bool(risk_flags.get("allow_raw_retention_ingress") or payload.get("allow_raw_retention_ingress"))
    if raw_requested and not raw_allowed:
        return "retention_ingress_blocked_raw_retention"

    biometric_sensitive = bool(
        risk_flags.get("biometric_sensitive")
        or risk_flags.get("emotion_sensitive")
        or payload.get("biometric_sensitive")
        or payload.get("emotion_sensitive")
    )
    if kind == "vision_retention_fulfillment_candidate" and biometric_sensitive and not bool(risk_flags.get("allow_biometric_or_emotion_sensitive_retention_ingress")):
        return "retention_ingress_blocked_biometric_or_emotion_sensitive"

    multimodal_sensitive = bool(
        risk_flags.get("multimodal_context_sensitive")
        or risk_flags.get("per_person_environment_fusion_sensitive")
        or payload.get("multimodal_context_sensitive")
        or payload.get("per_person_environment_fusion_sensitive")
    )
    if kind == "multimodal_retention_fulfillment_candidate" and multimodal_sensitive and not bool(risk_flags.get("allow_multimodal_context_sensitive_retention_ingress")):
        return "retention_ingress_blocked_multimodal_context_sensitive"

    requires_confirmation = bool(payload.get("requires_operator_confirmation") or risk_flags.get("requires_operator_confirmation"))
    confirmed = bool(payload.get("operator_confirmation_present") or risk_flags.get("operator_confirmation_present"))
    if requires_confirmation and not confirmed:
        return "retention_ingress_needs_more_context"

    return "retention_ingress_validated_for_future_commit"


def build_retention_ingress_validation_record(*, retention_fulfillment_candidate: Mapping[str, Any], validation_outcome: str | None = None, source_fulfillment_receipt: Mapping[str, Any] | None = None, created_at: float | None = None) -> dict[str, Any]:
    outcome = validation_outcome or classify_retention_ingress_validation_outcome(retention_fulfillment_candidate)
    if outcome not in ALLOWED_OUTCOMES:
        outcome = "retention_ingress_needs_more_context"
    material = {
        "source_fulfillment_candidate_id": retention_fulfillment_candidate.get("fulfillment_candidate_id"),
        "validation_outcome": outcome,
        "source_review_receipt_id": retention_fulfillment_candidate.get("source_review_receipt_id"),
    }
    validation_id = "riv_" + hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    kind = str(retention_fulfillment_candidate.get("fulfillment_candidate_kind") or "")
    risk_flags = dict(retention_fulfillment_candidate.get("risk_flags") or {})
    payload = dict(retention_fulfillment_candidate.get("candidate_payload_summary") or {})
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "retention_ingress_validation_id": validation_id,
        "source_fulfillment_candidate_id": retention_fulfillment_candidate.get("fulfillment_candidate_id"),
        "source_fulfillment_candidate_ref": embodied_fulfillment_candidate_ref(retention_fulfillment_candidate),
        "source_governance_bridge_candidate_ref": retention_fulfillment_candidate.get("source_governance_bridge_candidate_ref"),
        "source_handoff_candidate_ref": retention_fulfillment_candidate.get("source_handoff_candidate_ref"),
        "source_proposal_id": retention_fulfillment_candidate.get("source_proposal_id"),
        "source_review_receipt_id": retention_fulfillment_candidate.get("source_review_receipt_id"),
        "source_ingress_receipt_ref": retention_fulfillment_candidate.get("source_ingress_receipt_ref"),
        "source_event_refs": list(retention_fulfillment_candidate.get("source_event_refs") or []),
        "correlation_id": retention_fulfillment_candidate.get("correlation_id"),
        "source_module": retention_fulfillment_candidate.get("source_module"),
        "source_fulfillment_receipt_ref": embodied_fulfillment_receipt_ref(source_fulfillment_receipt) if source_fulfillment_receipt else None,
        "retention_candidate_kind": kind,
        "validation_outcome": outcome,
        "retention_candidate_summary": payload,
        "privacy_retention_posture": retention_fulfillment_candidate.get("privacy_retention_posture", "review"),
        "consent_posture": retention_fulfillment_candidate.get("consent_posture", "not_asserted"),
        "risk_flags": risk_flags,
        "provenance_complete": outcome != "retention_ingress_blocked_missing_provenance",
        "raw_retention_allowed": bool(risk_flags.get("allow_raw_retention_ingress") or payload.get("allow_raw_retention_ingress")),
        "biometric_or_emotion_sensitive": bool(risk_flags.get("biometric_sensitive") or risk_flags.get("emotion_sensitive") or payload.get("biometric_sensitive") or payload.get("emotion_sensitive")),
        "multimodal_context_sensitive": bool(risk_flags.get("multimodal_context_sensitive") or risk_flags.get("per_person_environment_fusion_sensitive") or payload.get("multimodal_context_sensitive") or payload.get("per_person_environment_fusion_sensitive")),
        "requires_operator_confirmation": bool(payload.get("requires_operator_confirmation") or risk_flags.get("requires_operator_confirmation")),
        "rationale": list(retention_fulfillment_candidate.get("rationale") or []),
        "created_at": float(created_at if created_at is not None else time.time()),
        "non_authoritative": True,
        "decision_power": "none",
        "validation_is_not_retention_commit": True,
        "does_not_commit_retention": True,
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }


def validate_retention_fulfillment_candidate(*, retention_fulfillment_candidate: Mapping[str, Any], source_fulfillment_receipt: Mapping[str, Any] | None = None, created_at: float | None = None) -> dict[str, Any]:
    return build_retention_ingress_validation_record(retention_fulfillment_candidate=retention_fulfillment_candidate, source_fulfillment_receipt=source_fulfillment_receipt, created_at=created_at)


def resolve_retention_ingress_validations(*, fulfillment_candidates: Sequence[Mapping[str, Any]], fulfillment_receipts: Sequence[Mapping[str, Any]] | None = None, created_at: float | None = None) -> dict[str, Any]:
    receipt_by_candidate = {str(r.get("source_fulfillment_candidate_id") or ""): r for r in (fulfillment_receipts or []) if isinstance(r, Mapping)}
    rows: list[dict[str, Any]] = []
    by_outcome: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for candidate in fulfillment_candidates:
        row = validate_retention_fulfillment_candidate(retention_fulfillment_candidate=candidate, source_fulfillment_receipt=receipt_by_candidate.get(str(candidate.get("fulfillment_candidate_id") or "")), created_at=created_at)
        rows.append(row)
        by_outcome[row["validation_outcome"]] = by_outcome.get(row["validation_outcome"], 0) + 1
        k = str(row.get("retention_candidate_kind") or "unknown")
        by_kind[k] = by_kind.get(k, 0) + 1
    return {
        "retention_ingress_validations": rows,
        "retention_ingress_validation_counts_by_outcome": dict(sorted(by_outcome.items())),
        "retention_ingress_counts_by_candidate_kind": dict(sorted(by_kind.items())),
    }


def summarize_retention_ingress_validation_status(*, retention_ingress_validations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_outcome: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    validated = blocked = 0
    privacy_or_bio_holds = 0
    for row in retention_ingress_validations:
        outcome = str(row.get("validation_outcome") or "retention_ingress_needs_more_context")
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        kind = str(row.get("retention_candidate_kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if outcome == "retention_ingress_validated_for_future_commit":
            validated += 1
        elif outcome.startswith("retention_ingress_blocked"):
            blocked += 1
        if outcome in {"retention_ingress_blocked_privacy_sensitive", "retention_ingress_blocked_biometric_or_emotion_sensitive", "retention_ingress_blocked_multimodal_context_sensitive"}:
            privacy_or_bio_holds += 1
    if not retention_ingress_validations:
        posture = "no_retention_ingress_candidates"
    else:
        labels = []
        if blocked > 0:
            labels.append("retention_ingress_blocked_items_present")
        if validated > 0:
            labels.append("retention_ingress_future_commit_candidates_present")
        if privacy_or_bio_holds > 0:
            labels.append("privacy_or_biometric_retention_holds_present")
        posture = "mixed_retention_ingress_state" if len(labels) > 1 else (labels[0] if labels else "retention_ingress_validations_present")
    return {
        "retention_ingress_validation_count": len(retention_ingress_validations),
        "retention_ingress_validation_counts_by_outcome": dict(sorted(by_outcome.items())),
        "retention_ingress_validated_for_future_commit_count": validated,
        "retention_ingress_blocked_count": blocked,
        "retention_ingress_counts_by_candidate_kind": dict(sorted(by_kind.items())),
        "retention_ingress_posture": posture,
    }


__all__ = [k for k in globals().keys() if k.startswith(("VALIDATION_", "SUPPORTED_", "ALLOWED_", "build_", "validate_", "resolve_", "classify_", "summarize_", "retention_ingress_"))]
