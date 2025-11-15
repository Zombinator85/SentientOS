"""Federation-aware Cathedral amendment guard."""

from __future__ import annotations

from typing import Literal, Optional

from sentientos.federation.window import FederationWindow

GuardDecision = Literal["allow", "warn", "hold"]

_KNOWN_RISKS = {"low", "medium", "high"}


def _coerce_risk_level(value: object) -> str:
    if isinstance(value, str) and value:
        lowered = value.strip().lower()
        if lowered in _KNOWN_RISKS:
            return lowered
    return "medium"


def should_accept_amendment(
    window: Optional[FederationWindow],
    risk_level: str,
) -> GuardDecision:
    """Determine whether an amendment should proceed under current drift."""

    risk = _coerce_risk_level(risk_level)
    if window is None:
        return "allow"

    if window.is_cluster_unstable:
        if risk == "high":
            return "hold"
        if risk == "medium":
            return "warn"
        return "allow"

    if window.is_quorum_healthy:
        if (window.warn_count or window.drift_count) and risk in {"medium", "high"}:
            return "warn"
        return "allow"

    # Degraded but not explicitly unstable. Default to caution.
    if risk == "high":
        return "hold"
    if risk == "medium":
        return "warn"
    return "allow"


def can_apply_amendment_now(amendment, window: Optional[FederationWindow]) -> bool:
    """Helper that returns ``True`` if the amendment can be applied immediately."""

    decision = should_accept_amendment(window, getattr(amendment, "risk_level", "medium"))
    return decision == "allow"


__all__ = ["GuardDecision", "should_accept_amendment", "can_apply_amendment_now"]
