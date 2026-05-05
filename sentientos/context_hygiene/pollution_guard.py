from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sentientos.context_hygiene.context_packet import ContradictionStatus, FreshnessStatus, PollutionRisk

BLOCKING_TRUTH_INGRESS = {
    "blocked",
    "underconstrained",
    "unsupported",
    "contradiction-blocked",
    "no-new-evidence-reversal",
    "unknown-source-backed",
}
ALLOWED_REF_TYPES = {"memory", "claim", "evidence", "stance", "diagnostic", "embodiment", "dialogue"}


def provenance_is_complete(candidate: Any) -> bool:
    return bool(getattr(candidate, "provenance_refs", None))


def candidate_is_expired(candidate: Any, now: datetime | None = None) -> bool:
    expiry = getattr(candidate, "expires_at", None) or getattr(candidate, "valid_until", None)
    if expiry is None:
        return False
    current = now or datetime.now(timezone.utc)
    return current >= expiry


def classify_pollution_risk(candidate: Any, now: datetime | None = None) -> str:
    ref_type = str(getattr(candidate, "ref_type", "unknown")).lower()
    if not getattr(candidate, "ref_id", ""):
        return PollutionRisk.BLOCKED.value
    if not provenance_is_complete(candidate):
        return PollutionRisk.BLOCKED.value
    if ref_type not in ALLOWED_REF_TYPES:
        return PollutionRisk.BLOCKED.value
    if candidate_is_expired(candidate, now=now):
        return PollutionRisk.BLOCKED.value
    if str(getattr(candidate, "truth_ingress_status", "")).lower() in BLOCKING_TRUTH_INGRESS:
        return PollutionRisk.BLOCKED.value
    if str(getattr(candidate, "contradiction_status", "")).lower() == "blocked":
        return PollutionRisk.BLOCKED.value
    if ref_type == "embodiment" and not bool(getattr(candidate, "already_sanitized_context_summary", False)):
        return PollutionRisk.BLOCKED.value
    if str(getattr(candidate, "freshness_status", "")).lower() in {"stale", "unknown"}:
        return PollutionRisk.MEDIUM.value
    if str(getattr(candidate, "contradiction_status", "")).lower() in {"warning", "suspected", "contradicted"}:
        return PollutionRisk.MEDIUM.value
    return PollutionRisk.LOW.value


def combine_pollution_risk(candidates_or_decisions: Iterable[Any], now: datetime | None = None) -> str:
    risks = [classify_pollution_risk(item, now=now) for item in candidates_or_decisions]
    if not risks:
        return PollutionRisk.MEDIUM.value
    allowed = {risk.value for risk in PollutionRisk}
    normalized = [risk if risk in allowed else PollutionRisk.BLOCKED.value for risk in risks]
    if PollutionRisk.BLOCKED.value in normalized:
        return PollutionRisk.BLOCKED.value
    if PollutionRisk.HIGH.value in normalized:
        return PollutionRisk.HIGH.value
    if PollutionRisk.MEDIUM.value in normalized:
        return PollutionRisk.MEDIUM.value
    return PollutionRisk.LOW.value


def combine_freshness_status(candidates_or_decisions: Iterable[Any]) -> FreshnessStatus:
    statuses = {str(getattr(item, "freshness_status", "unknown")).lower() for item in candidates_or_decisions}
    if not statuses or statuses == {"unknown"}:
        return FreshnessStatus.UNKNOWN
    if statuses == {"fresh"}:
        return FreshnessStatus.FRESH
    if statuses == {"stale"}:
        return FreshnessStatus.STALE
    return FreshnessStatus.MIXED


def combine_contradiction_status(candidates_or_decisions: Iterable[Any]) -> ContradictionStatus:
    statuses = {str(getattr(item, "contradiction_status", "unknown")).lower() for item in candidates_or_decisions}
    if not statuses or statuses == {"unknown"}:
        return ContradictionStatus.UNKNOWN
    if "warning" in statuses or "suspected" in statuses:
        return ContradictionStatus.SUSPECTED
    if "contradicted" in statuses:
        return ContradictionStatus.CONTRADICTED
    return ContradictionStatus.NONE
