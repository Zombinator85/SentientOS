"""Consciousness Layer attention arbitrator scaffold.

This module tracks arbitration inputs for the Consciousness Layer described in
``docs/CONSCIOUSNESS_LAYER.md``. It preserves the previous lightweight
structures while exposing the ``run_cycle`` hook expected by the new runtime
wiring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sentientos.daemons import pulse_bus
from sentientos.glow import self_state

logger = logging.getLogger(__name__)


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
    internal_priority: Optional[str] = None
    event_origin: str = "local"

    def score(self) -> tuple:
        """Return ordering metrics; higher priority first."""

        priority_order = {
            "urgent": 0,
            "high": 1,
            "normal": 2,
            "low": 3,
        }
        return (
            priority_order.get(self.priority, 2),
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

    def submit(self, event: PulseEvent) -> None:
        self.history.append(event)

    def choose_focus(self) -> Optional[PulseEvent]:
        if not self.history:
            return None
        self.history.sort(key=lambda e: e.score())
        self.last_focus = self.history[0]
        return self.last_focus

    def reset(self) -> None:
        self.history.clear()
        self.last_focus = None


class AttentionArbitratorDaemon:
    """Placeholder consciousness daemon for focus arbitration cycles."""

    def __init__(self) -> None:
        self._last_cycle: datetime | None = None

    def run_cycle(self) -> None:
        glow_state = self_state.load()
        logger.debug(
            "Attention arbitrator scaffold cycle executed",
            extra={
                "identity": glow_state.get("identity"),
                "last_focus": glow_state.get("last_focus"),
            },
        )
        self._last_cycle = datetime.now(timezone.utc)


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
