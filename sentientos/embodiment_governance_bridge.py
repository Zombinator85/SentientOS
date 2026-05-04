from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping, Sequence

from sentientos.embodiment_proposal_handoff import embodied_handoff_candidate_ref

SCHEMA_VERSION = "embodiment.governance_bridge_candidate.v1"

_BRIDGE_KIND_BY_HANDOFF_KIND = {
    "memory_ingress_handoff_candidate": "memory_governance_review_candidate",
    "feedback_action_handoff_candidate": "feedback_action_governance_review_candidate",
    "screen_retention_handoff_candidate": "screen_retention_governance_review_candidate",
    "vision_retention_handoff_candidate": "vision_retention_governance_review_candidate",
    "multimodal_retention_handoff_candidate": "multimodal_retention_governance_review_candidate",
    "operator_attention_handoff_candidate": "operator_attention_governance_review_candidate",
}


def embodied_governance_bridge_candidate_ref(record: Mapping[str, Any]) -> str:
    return f"governance_bridge_candidate:{record['governance_bridge_candidate_id']}"


def classify_embodied_governance_bridge_kind(handoff_candidate_kind: str) -> str:
    return _BRIDGE_KIND_BY_HANDOFF_KIND.get(str(handoff_candidate_kind or ""), "unsupported_governance_bridge_candidate")


def map_handoff_candidate_to_governance_bridge(handoff_candidate: Mapping[str, Any]) -> tuple[str, str]:
    posture = str(handoff_candidate.get("handoff_posture") or "")
    kind = classify_embodied_governance_bridge_kind(str(handoff_candidate.get("handoff_candidate_kind") or ""))
    if kind == "unsupported_governance_bridge_candidate":
        return kind, "blocked_unsupported_kind"
    if posture != "eligible_for_next_stage_review":
        return kind, "blocked_handoff_not_eligible"
    privacy = str(handoff_candidate.get("privacy_retention_posture") or "")
    consent = str(handoff_candidate.get("consent_posture") or "")
    if privacy in {"restricted", "sensitive"} and consent in {"", "unknown", "not_asserted", "required"}:
        return kind, "blocked_privacy_or_consent_required"
    return kind, "eligible_for_governance_review"


def build_embodied_governance_bridge_candidate(*, handoff_candidate: Mapping[str, Any], created_at: float | None = None) -> dict[str, Any]:
    kind, posture = map_handoff_candidate_to_governance_bridge(handoff_candidate)
    material = {
        "handoff_candidate_id": handoff_candidate.get("handoff_candidate_id"),
        "handoff_kind": handoff_candidate.get("handoff_candidate_kind"),
        "bridge_kind": kind,
        "bridge_posture": posture,
    }
    bridge_id = "egbc_" + hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return {
        "schema_version": SCHEMA_VERSION,
        "governance_bridge_candidate_id": bridge_id,
        "governance_bridge_candidate_kind": kind,
        "source_handoff_candidate_id": handoff_candidate.get("handoff_candidate_id"),
        "source_handoff_candidate_ref": embodied_handoff_candidate_ref(handoff_candidate),
        "source_proposal_id": handoff_candidate.get("source_proposal_id"),
        "source_review_receipt_id": handoff_candidate.get("source_review_receipt_id"),
        "source_ingress_receipt_ref": handoff_candidate.get("source_ingress_receipt_ref"),
        "source_event_refs": list(handoff_candidate.get("source_event_refs") or []),
        "correlation_id": handoff_candidate.get("correlation_id"),
        "source_module": handoff_candidate.get("source_module"),
        "proposal_kind": handoff_candidate.get("proposal_kind"),
        "risk_flags": dict(handoff_candidate.get("risk_flags") or {}),
        "privacy_retention_posture": handoff_candidate.get("privacy_retention_posture", "review"),
        "consent_posture": handoff_candidate.get("consent_posture", "not_asserted"),
        "bridge_posture": posture,
        "candidate_payload_summary": dict(handoff_candidate.get("candidate_payload_summary") or {}),
        "rationale": list(handoff_candidate.get("rationale") or []),
        "created_at": float(created_at if created_at is not None else time.time()),
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "approval_is_not_execution": True,
        "handoff_is_not_fulfillment": True,
        "bridge_is_not_admission": True,
    }


def resolve_embodied_governance_bridge_candidates(*, handoff_candidates: Sequence[Mapping[str, Any]], created_at: float | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_kind: dict[str, int] = {}
    by_posture: dict[str, int] = {}
    for handoff in handoff_candidates:
        row = build_embodied_governance_bridge_candidate(handoff_candidate=handoff, created_at=created_at)
        by_posture[row["bridge_posture"]] = by_posture.get(row["bridge_posture"], 0) + 1
        if row["bridge_posture"] == "eligible_for_governance_review":
            by_kind[row["governance_bridge_candidate_kind"]] = by_kind.get(row["governance_bridge_candidate_kind"], 0) + 1
            rows.append(row)
    return {
        "governance_bridge_candidates": rows,
        "governance_bridge_counts_by_kind": dict(sorted(by_kind.items())),
        "blocked_bridge_counts_by_reason": dict(sorted((k, v) for k, v in by_posture.items() if k != "eligible_for_governance_review")),
        "counts_by_bridge_posture": dict(sorted(by_posture.items())),
    }


def summarize_embodied_governance_bridge_candidates(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    blocked: dict[str, int] = {}
    for row in candidates:
        by_kind[row.get("governance_bridge_candidate_kind", "unknown")] = by_kind.get(row.get("governance_bridge_candidate_kind", "unknown"), 0) + 1
        posture = str(row.get("bridge_posture") or "")
        if posture != "eligible_for_governance_review":
            blocked[posture] = blocked.get(posture, 0) + 1
    return {
        "governance_bridge_candidate_count": len(candidates),
        "governance_bridge_counts_by_kind": dict(sorted(by_kind.items())),
        "blocked_bridge_counts_by_reason": dict(sorted(blocked.items())),
    }


__all__ = [
    "SCHEMA_VERSION",
    "build_embodied_governance_bridge_candidate",
    "resolve_embodied_governance_bridge_candidates",
    "embodied_governance_bridge_candidate_ref",
    "classify_embodied_governance_bridge_kind",
    "summarize_embodied_governance_bridge_candidates",
    "map_handoff_candidate_to_governance_bridge",
]
