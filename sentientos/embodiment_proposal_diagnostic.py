from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from sentientos.embodiment_proposals import embodied_proposal_ref, list_recent_embodied_proposals

SUMMARY_SCHEMA_VERSION = "embodiment.proposal.review_summary.v1"


def group_embodied_proposals_by_kind(proposals: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    grouped: dict[str, int] = {}
    for row in proposals:
        kind = str(row.get("proposal_kind") or "unknown")
        grouped[kind] = grouped.get(kind, 0) + 1
    return dict(sorted(grouped.items()))


def count_pending_embodied_proposals(proposals: Iterable[Mapping[str, Any]]) -> int:
    return sum(1 for row in proposals if str(row.get("review_status") or "") == "pending_review")


def _counts_by_source_module(proposals: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    grouped: dict[str, int] = {}
    for row in proposals:
        source = str(row.get("source_module") or "unknown")
        grouped[source] = grouped.get(source, 0) + 1
    return dict(sorted(grouped.items()))


def _truthy(value: Any) -> bool:
    return bool(value) and value not in {"none", "not_asserted", "unknown"}


def _high_risk_counts(pending: list[Mapping[str, Any]]) -> dict[str, int]:
    out = {
        "memory_write_pressure": 0,
        "action_trigger_pressure": 0,
        "privacy_sensitive_retention": 0,
        "biometric_or_emotion_sensitive": 0,
        "multimodal_retention": 0,
    }
    for row in pending:
        kind = str(row.get("proposal_kind") or "")
        blocked = str(row.get("blocked_effect_type") or "")
        risk_flags = row.get("risk_flags") if isinstance(row.get("risk_flags"), Mapping) else {}
        privacy = str(row.get("privacy_retention_posture") or "")
        candidate = row.get("candidate_payload_summary") if isinstance(row.get("candidate_payload_summary"), Mapping) else {}

        if kind == "memory_ingress_candidate" or blocked == "memory_write":
            out["memory_write_pressure"] += 1
        if kind == "feedback_action_candidate" or blocked == "feedback_action":
            out["action_trigger_pressure"] += 1
        if "retention" in kind or blocked.startswith("retention:"):
            if privacy in {"review", "restricted", "sensitive"}:
                out["privacy_sensitive_retention"] += 1
        if kind == "multimodal_retention_candidate" or blocked.startswith("retention:multimodal"):
            out["multimodal_retention"] += 1
        if _truthy(risk_flags.get("biometric_sensitive")) or _truthy(risk_flags.get("emotion_sensitive")) or _truthy(candidate.get("emotion")):
            out["biometric_or_emotion_sensitive"] += 1
    return out


def classify_embodied_proposal_review_posture(*, pending_review_count: int, high_risk_counts: Mapping[str, int]) -> str:
    if pending_review_count <= 0:
        return "no_pending_embodied_proposals"

    has_memory_or_action = (high_risk_counts.get("memory_write_pressure", 0) > 0 or high_risk_counts.get("action_trigger_pressure", 0) > 0)
    has_privacy = high_risk_counts.get("privacy_sensitive_retention", 0) > 0
    if has_memory_or_action and has_privacy:
        return "pending_mixed_high_risk_review"
    if has_memory_or_action:
        return "pending_action_or_memory_review"
    if has_privacy:
        return "pending_privacy_sensitive_review"
    return "pending_low_risk_review"


def _recent_refs(proposals: list[Mapping[str, Any]], *, limit: int = 5) -> list[str]:
    ordered = sorted(
        proposals,
        key=lambda row: (float(row.get("created_at") or 0.0), str(row.get("proposal_id") or "")),
        reverse=True,
    )
    return [embodied_proposal_ref(row) for row in ordered[: max(1, limit)] if "proposal_id" in row]


def summarize_recent_embodied_proposals(proposals: list[Mapping[str, Any]], *, generated_at: float | None = None) -> dict[str, Any]:
    pending = [row for row in proposals if str(row.get("review_status") or "") == "pending_review"]
    pending_times = [float(row.get("created_at")) for row in pending if isinstance(row.get("created_at"), (int, float))]
    risk = _high_risk_counts(pending)
    posture = classify_embodied_proposal_review_posture(pending_review_count=len(pending), high_risk_counts=risk)
    summary_material = {
        "pending_review_count": len(pending),
        "counts_by_kind": group_embodied_proposals_by_kind(pending),
        "counts_by_source_module": _counts_by_source_module(pending),
        "posture": posture,
    }
    digest = hashlib.sha256(json.dumps(summary_material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:20]
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "summary_id": f"eprs_{digest}",
        "generated_at": float(generated_at if generated_at is not None else time.time()),
        "proposal_count_total": len(proposals),
        "pending_review_count": len(pending),
        "counts_by_kind": group_embodied_proposals_by_kind(pending),
        "counts_by_source_module": _counts_by_source_module(pending),
        "high_risk_counts": risk,
        "most_recent_proposal_refs": _recent_refs(pending),
        "oldest_pending_created_at": min(pending_times) if pending_times else None,
        "newest_pending_created_at": max(pending_times) if pending_times else None,
        "recommended_review_posture": posture,
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }


def build_embodied_proposal_review_summary(*, path: Path, limit: int = 200, generated_at: float | None = None) -> dict[str, Any]:
    proposals = list_recent_embodied_proposals(path=path, limit=limit)
    return summarize_recent_embodied_proposals(proposals, generated_at=generated_at)


__all__ = [
    "SUMMARY_SCHEMA_VERSION",
    "build_embodied_proposal_review_summary",
    "summarize_recent_embodied_proposals",
    "classify_embodied_proposal_review_posture",
    "group_embodied_proposals_by_kind",
    "count_pending_embodied_proposals",
]
