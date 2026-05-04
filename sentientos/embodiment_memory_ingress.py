from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping, Sequence

from sentientos.embodiment_fulfillment import embodied_fulfillment_candidate_ref, embodied_fulfillment_receipt_ref

VALIDATION_SCHEMA_VERSION = "embodiment.memory_ingress_validation.v1"

SUPPORTED_FULFILLMENT_KIND = "memory_fulfillment_candidate"

ALLOWED_OUTCOMES = {
    "memory_ingress_validated_for_future_write",
    "memory_ingress_blocked_missing_consent",
    "memory_ingress_blocked_privacy_sensitive",
    "memory_ingress_blocked_raw_retention",
    "memory_ingress_blocked_missing_provenance",
    "memory_ingress_blocked_unsupported_kind",
    "memory_ingress_needs_more_context",
}


def memory_ingress_validation_ref(record: Mapping[str, Any]) -> str:
    return f"memory_ingress_validation:{record['memory_ingress_validation_id']}"


def classify_memory_ingress_validation_outcome(candidate: Mapping[str, Any]) -> str:
    kind = str(candidate.get("fulfillment_candidate_kind") or "")
    if kind != SUPPORTED_FULFILLMENT_KIND:
        return "memory_ingress_blocked_unsupported_kind"

    if not all(
        [
            candidate.get("fulfillment_candidate_id"),
            candidate.get("source_governance_bridge_candidate_ref"),
            candidate.get("source_handoff_candidate_ref"),
            candidate.get("source_proposal_id"),
            candidate.get("source_review_receipt_id"),
        ]
    ):
        return "memory_ingress_blocked_missing_provenance"

    privacy_posture = str(candidate.get("privacy_retention_posture") or "")
    risk_flags = dict(candidate.get("risk_flags") or {})
    privacy_allow = bool(risk_flags.get("allow_privacy_sensitive_memory_ingress"))
    if privacy_posture in {"sensitive", "restricted"} and not privacy_allow:
        return "memory_ingress_blocked_privacy_sensitive"

    payload = dict(candidate.get("candidate_payload_summary") or {})
    raw_requested = bool(risk_flags.get("raw_retention_requested") or payload.get("raw_retention_requested"))
    raw_allowed = bool(risk_flags.get("allow_raw_retention_memory_ingress") or payload.get("allow_raw_retention_memory_ingress"))
    if raw_requested and not raw_allowed:
        return "memory_ingress_blocked_raw_retention"

    consent_posture = str(candidate.get("consent_posture") or "")
    if consent_posture in {"", "unknown", "not_asserted", "required"}:
        return "memory_ingress_blocked_missing_consent"
    if consent_posture in {"review", "conditional"}:
        return "memory_ingress_needs_more_context"

    return "memory_ingress_validated_for_future_write"


def build_memory_ingress_validation_record(*, memory_fulfillment_candidate: Mapping[str, Any], validation_outcome: str | None = None, source_fulfillment_receipt: Mapping[str, Any] | None = None, created_at: float | None = None) -> dict[str, Any]:
    source_ref = embodied_fulfillment_candidate_ref(memory_fulfillment_candidate)
    outcome = validation_outcome or classify_memory_ingress_validation_outcome(memory_fulfillment_candidate)
    if outcome not in ALLOWED_OUTCOMES:
        outcome = "memory_ingress_needs_more_context"
    material = {
        "source_fulfillment_candidate_id": memory_fulfillment_candidate.get("fulfillment_candidate_id"),
        "validation_outcome": outcome,
        "source_review_receipt_id": memory_fulfillment_candidate.get("source_review_receipt_id"),
    }
    validation_id = "miv_" + hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    provenance_complete = outcome != "memory_ingress_blocked_missing_provenance"
    raw_allowed = bool(
        (memory_fulfillment_candidate.get("risk_flags") or {}).get("allow_raw_retention_memory_ingress")
        or (memory_fulfillment_candidate.get("candidate_payload_summary") or {}).get("allow_raw_retention_memory_ingress")
    )
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "memory_ingress_validation_id": validation_id,
        "source_fulfillment_candidate_id": memory_fulfillment_candidate.get("fulfillment_candidate_id"),
        "source_fulfillment_candidate_ref": source_ref,
        "source_governance_bridge_candidate_ref": memory_fulfillment_candidate.get("source_governance_bridge_candidate_ref"),
        "source_handoff_candidate_ref": memory_fulfillment_candidate.get("source_handoff_candidate_ref"),
        "source_proposal_id": memory_fulfillment_candidate.get("source_proposal_id"),
        "source_review_receipt_id": memory_fulfillment_candidate.get("source_review_receipt_id"),
        "source_ingress_receipt_ref": memory_fulfillment_candidate.get("source_ingress_receipt_ref"),
        "source_event_refs": list(memory_fulfillment_candidate.get("source_event_refs") or []),
        "correlation_id": memory_fulfillment_candidate.get("correlation_id"),
        "source_module": memory_fulfillment_candidate.get("source_module"),
        "source_fulfillment_receipt_ref": embodied_fulfillment_receipt_ref(source_fulfillment_receipt) if source_fulfillment_receipt else None,
        "validation_outcome": outcome,
        "memory_candidate_summary": dict(memory_fulfillment_candidate.get("candidate_payload_summary") or {}),
        "privacy_retention_posture": memory_fulfillment_candidate.get("privacy_retention_posture", "review"),
        "consent_posture": memory_fulfillment_candidate.get("consent_posture", "not_asserted"),
        "risk_flags": dict(memory_fulfillment_candidate.get("risk_flags") or {}),
        "provenance_complete": provenance_complete,
        "raw_retention_allowed": raw_allowed,
        "rationale": list(memory_fulfillment_candidate.get("rationale") or []),
        "created_at": float(created_at if created_at is not None else time.time()),
        "non_authoritative": True,
        "decision_power": "none",
        "validation_is_not_memory_write": True,
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_commit_retention": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }


def validate_memory_fulfillment_candidate(*, memory_fulfillment_candidate: Mapping[str, Any], source_fulfillment_receipt: Mapping[str, Any] | None = None, created_at: float | None = None) -> dict[str, Any]:
    return build_memory_ingress_validation_record(
        memory_fulfillment_candidate=memory_fulfillment_candidate,
        source_fulfillment_receipt=source_fulfillment_receipt,
        created_at=created_at,
    )


def resolve_memory_ingress_validations(*, fulfillment_candidates: Sequence[Mapping[str, Any]], fulfillment_receipts: Sequence[Mapping[str, Any]] | None = None, created_at: float | None = None) -> dict[str, Any]:
    receipt_by_candidate = {
        str(r.get("source_fulfillment_candidate_id") or ""): r
        for r in (fulfillment_receipts or [])
        if isinstance(r, Mapping)
    }
    rows: list[dict[str, Any]] = []
    by_outcome: dict[str, int] = {}
    for candidate in fulfillment_candidates:
        candidate_id = str(candidate.get("fulfillment_candidate_id") or "")
        row = validate_memory_fulfillment_candidate(
            memory_fulfillment_candidate=candidate,
            source_fulfillment_receipt=receipt_by_candidate.get(candidate_id),
            created_at=created_at,
        )
        rows.append(row)
        by_outcome[row["validation_outcome"]] = by_outcome.get(row["validation_outcome"], 0) + 1
    return {
        "memory_ingress_validations": rows,
        "memory_ingress_validation_counts_by_outcome": dict(sorted(by_outcome.items())),
    }


def summarize_memory_ingress_validation_status(*, memory_ingress_validations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts_by_outcome: dict[str, int] = {}
    validated = 0
    blocked = 0
    for row in memory_ingress_validations:
        outcome = str(row.get("validation_outcome") or "memory_ingress_needs_more_context")
        counts_by_outcome[outcome] = counts_by_outcome.get(outcome, 0) + 1
        if outcome == "memory_ingress_validated_for_future_write":
            validated += 1
        elif outcome.startswith("memory_ingress_blocked"):
            blocked += 1

    if not memory_ingress_validations:
        posture = "no_memory_ingress_candidates"
    else:
        flags = []
        if blocked > 0:
            flags.append("memory_ingress_blocked_items_present")
        if validated > 0:
            flags.append("memory_ingress_future_write_candidates_present")
        if len(flags) > 1:
            posture = "mixed_memory_ingress_state"
        elif flags:
            posture = flags[0]
        else:
            posture = "memory_ingress_validations_present"

    return {
        "memory_ingress_validation_count": len(memory_ingress_validations),
        "memory_ingress_validation_counts_by_outcome": dict(sorted(counts_by_outcome.items())),
        "memory_ingress_validated_for_future_write_count": validated,
        "memory_ingress_blocked_count": blocked,
        "memory_ingress_posture": posture,
    }


__all__ = [k for k in globals().keys() if k.startswith(("VALIDATION_", "SUPPORTED_", "ALLOWED_", "build_", "validate_", "resolve_", "classify_", "summarize_", "memory_ingress_"))]
