"""Federation guard utilities for experiment execution."""

from __future__ import annotations

from typing import Callable, Dict, Literal, Optional

from sentientos.federation.window import FederationWindow

ExperimentGuardDecision = Literal["allow", "warn", "hold"]

_WINDOW_PROVIDER: Optional[Callable[[], Optional[FederationWindow]]] = None
_EVENT_SINK: Optional[Callable[[ExperimentGuardDecision, Dict[str, object]], None]] = None

_KNOWN_RISKS = {"low", "medium", "high"}


def _coerce_risk(value: object) -> str:
    if isinstance(value, str) and value:
        lowered = value.strip().lower()
        if lowered in _KNOWN_RISKS:
            return lowered
    return "medium"


def should_run_experiment(
    window: Optional[FederationWindow],
    risk_level: str,
) -> ExperimentGuardDecision:
    """Return the guard decision for an experiment under current drift."""

    risk = _coerce_risk(risk_level)
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

    if risk == "high":
        return "hold"
    if risk == "medium":
        return "warn"
    return "allow"


def set_window_provider(provider: Optional[Callable[[], Optional[FederationWindow]]]) -> None:
    """Register a callable that returns the latest :class:`FederationWindow`."""

    global _WINDOW_PROVIDER
    _WINDOW_PROVIDER = provider


def current_window() -> Optional[FederationWindow]:
    provider = _WINDOW_PROVIDER
    if provider is None:
        return None
    try:
        return provider()
    except Exception:  # pragma: no cover - defensive
        return None


def set_event_sink(callback: Optional[Callable[[ExperimentGuardDecision, Dict[str, object]], None]]) -> None:
    """Register a callback invoked whenever the guard makes a decision."""

    global _EVENT_SINK
    _EVENT_SINK = callback


def emit_guard_event(decision: ExperimentGuardDecision, payload: Dict[str, object]) -> None:
    if _EVENT_SINK is None:
        return
    try:
        _EVENT_SINK(decision, payload)
    except Exception:  # pragma: no cover - defensive
        pass


__all__ = [
    "ExperimentGuardDecision",
    "should_run_experiment",
    "set_window_provider",
    "current_window",
    "set_event_sink",
    "emit_guard_event",
]
