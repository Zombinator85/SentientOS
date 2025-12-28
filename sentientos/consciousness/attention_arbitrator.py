# NOTE:
# This module is part of the Consciousness Layer scaffolding.
# It does not perform autonomous execution.
# All operations must be driven by explicit orchestrator calls.
# Guardrails and covenant autoalignment remain authoritative.
"""Deterministic attention arbitrator scaffolding.

This module tracks arbitration inputs for the Consciousness Layer described in
``docs/CONSCIOUSNESS_LAYER.md``. It preserves the previous lightweight
structures while exposing the ``run_cycle`` hook expected by the runtime
wiring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sentientos.daemons import pulse_bus
from sentientos.glow.self_state import load as load_self_state
from sentientos.integrity import covenant_autoalign

logger = logging.getLogger(__name__)

ALLOWED_EVENT_ORIGINS = {"local", "system", "peer", "reflection", "sensor"}
PRIORITY_ORDER = {
    "urgent": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
}
INTERNAL_PRIORITY_ORDER = {
    "critical": -2.0,
    "elevated": -1.0,
    "baseline": 0.0,
    "routine": 0.5,
    "low": 1.0,
}
ORIGIN_ORDER = {
    "local": 0,
    "system": 1,
    "reflection": 2,
    "sensor": 3,
    "peer": 4,
}


@dataclass
class PulseEvent:
    """Minimal pulse representation for arbitration."""

    payload: Dict[str, Any]
    priority: str = "normal"
    interruptible: bool = True
    origin: str = "unknown"
    timestamp: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)
    focus: Optional[str] = None
    internal_priority: Optional[str] = "baseline"
    event_origin: str = "local"

    def score(self) -> tuple:
        """Return ordering metrics; higher priority first."""

        return (
            PRIORITY_ORDER.get(self.priority, PRIORITY_ORDER["normal"]),
            -len(self.context),
            self.timestamp or 0.0,
        )

    def to_pulse(self) -> Dict[str, Any]:
        """Return a pulse bus compatible payload with safe defaults."""

        base = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "attention_arbitrator",
            "event_type": "attention_update",
            "payload": self.payload,
            "priority": "info",
        }
        enriched = pulse_bus.apply_pulse_defaults({**base, **self.__dict__})
        return enriched


class AttentionArbitrator:
    """Stub attention arbitrator that picks a single winner."""

    def __init__(self) -> None:
        self.history: List[PulseEvent] = []
        self.last_focus: Optional[PulseEvent] = None
        self._last_decision: Dict[str, Any] = {}

    def submit(self, event: PulseEvent) -> None:
        self.history.append(event)

    def choose_focus(self) -> Optional[PulseEvent]:
        if not self.history:
            self._record_decision("no_events", skipped=0)
            return self.last_focus

        valid_events: List[tuple[PulseEvent, Tuple[int, float, int, int, int, float]]] = []
        skipped = 0
        for event in self.history:
            if not self._validate_event(event):
                skipped += 1
                continue
            score = self._score(event)
            valid_events.append((event, score))

        if not valid_events:
            self._record_decision("no_valid_events", skipped=skipped)
            return self.last_focus

        valid_events.sort(key=lambda item: item[1])
        winner = valid_events[0][0]
        self.last_focus = winner
        self.history.clear()
        self._record_decision("focus_selected", skipped=skipped, winner=winner)
        return winner

    def reset(self) -> None:
        self.history.clear()
        self.last_focus = None
        self._last_decision = {}

    def telemetry_snapshot(self) -> Dict[str, Any]:
        """Return a lightweight snapshot describing the last arbitration."""

        return {
            "last_focus": getattr(self.last_focus, "focus", None),
            "last_origin": getattr(self.last_focus, "event_origin", None),
            "last_decision": self._last_decision,
        }

    def _score(self, event: PulseEvent) -> Tuple[int, float, int, int, int, float]:
        priority_score = PRIORITY_ORDER.get(event.priority, PRIORITY_ORDER["normal"])
        internal = event.internal_priority
        internal_score = INTERNAL_PRIORITY_ORDER.get(internal, 0.0)
        if isinstance(internal, (int, float)):
            internal_score = float(internal)

        origin_score = ORIGIN_ORDER.get(event.event_origin, len(ORIGIN_ORDER))
        focus_bias = 0 if self.last_focus and event.focus == self.last_focus.focus else 1
        context_depth = -len(event.context)
        timestamp_bias = -float(event.timestamp or datetime.now(timezone.utc).timestamp())
        return (priority_score, internal_score, origin_score, focus_bias, context_depth, timestamp_bias)

    def _validate_event(self, event: PulseEvent) -> bool:
        try:
            pulse_bus.apply_pulse_defaults(event.to_pulse())
        except Exception:  # pragma: no cover - defensive guardrail
            logger.warning("Pulse event failed schema defaults", extra={"event": event})
            return False

        if event.event_origin not in ALLOWED_EVENT_ORIGINS:
            logger.warning(
                "Rejected pulse with unsupported origin", extra={"event_origin": event.event_origin}
            )
            return False
        if not isinstance(event.context, dict):
            logger.warning("Rejected pulse with invalid context", extra={"context_type": type(event.context)})
            return False
        if event.internal_priority is not None and not isinstance(
            event.internal_priority, (str, int, float)
        ):
            logger.warning(
                "Rejected pulse with invalid internal priority",
                extra={"internal_priority": event.internal_priority},
            )
            return False
        if event.focus is not None and not isinstance(event.focus, str):
            logger.warning("Rejected pulse with invalid focus", extra={"focus_type": type(event.focus)})
            return False
        return True

    def _record_decision(self, reason: str, *, skipped: int, winner: PulseEvent | None = None) -> None:
        self._last_decision = {
            "reason": reason,
            "skipped": skipped,
            "selected": getattr(winner, "focus", None),
            "origin": getattr(winner, "event_origin", None),
            "priority": getattr(winner, "priority", None),
        }
        logger.info(
            "Attention arbitration decision",
            extra={"decision": self._last_decision, "history_size": len(self.history)},
        )


class AttentionArbitratorDaemon:
    """Placeholder consciousness daemon for focus arbitration cycles."""

    def __init__(self) -> None:
        self.arbitrator = AttentionArbitrator()
        self._last_cycle: datetime | None = None

    def run_cycle(self, *, context: Mapping[str, object] | None = None) -> None:
        covenant_autoalign.autoalign_before_cycle()
        glow_state = load_self_state()
        winner = self.arbitrator.choose_focus()
        pressure_snapshot = context.get("pressure_snapshot") if isinstance(context, Mapping) else None
        pressure_total = None
        overload = None
        if isinstance(pressure_snapshot, Mapping):
            pressure_total = pressure_snapshot.get("total_active_pressure")
            overload = pressure_snapshot.get("overload")
        logger.debug(
            "Attention arbitrator scaffold cycle executed",
            extra={
                "identity": glow_state.get("identity"),
                "last_focus": getattr(winner, "focus", glow_state.get("last_focus")),
                "decision": self.arbitrator.telemetry_snapshot(),
                "pressure_total": pressure_total,
                "pressure_overload": overload,
            },
        )
        self._last_cycle = datetime.now(timezone.utc)

    def choose_focus(self) -> PulseEvent | None:
        """Expose deterministic focus resolution for callers and tests."""

        return self.arbitrator.choose_focus()

    def telemetry_snapshot(self) -> Dict[str, Any]:
        """Proxy telemetry for observability and testing."""

        return self.arbitrator.telemetry_snapshot()


_DAEMON = AttentionArbitratorDaemon()


def run_cycle() -> None:
    """Execute a placeholder arbitration cycle for the Consciousness Layer."""

    _DAEMON.run_cycle()


__all__ = [
    "AttentionArbitrator",
    "AttentionArbitratorDaemon",
    "PulseEvent",
    "run_cycle",
]
