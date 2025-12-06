"""Consciousness Layer attention arbitrator.

This daemon selects the highest priority pulse event and publishes focus and
context updates for the rest of the system. The implementation here is a
lightweight scaffold to allow further integration work without blocking other
features.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PulseEvent:
    """Minimal pulse representation for arbitration."""

    payload: Dict[str, Any]
    priority: str = "normal"
    interruptible: bool = True
    origin: str = "unknown"
    timestamp: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)

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


__all__ = ["AttentionArbitrator", "PulseEvent"]
