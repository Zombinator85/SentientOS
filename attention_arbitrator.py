"""Attention arbitration daemon for the Consciousness Layer.

This lightweight scaffold applies priority-aware ordering with covenant-ready
tie breakers. It exposes a small API suitable for runtime integration and for
tests that validate arbitration correctness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


PRIORITY_ORDER = {
    "urgent": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
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
    novelty: float = 0.0
    relevance: float = 0.0
    reliability: float = 0.5

    def score(self) -> tuple[int, float, float, float, float]:
        """Return ordering metrics; lower tuple wins."""
        return (
            PRIORITY_ORDER.get(self.priority, PRIORITY_ORDER["normal"]),
            -self.relevance,
            -self.novelty,
            -self.reliability,
            self.timestamp or 0.0,
        )


class AttentionArbitrator:
    """Selects a single pulse to become the system focus."""

    def __init__(self) -> None:
        self.history: List[PulseEvent] = []
        self.last_focus: Optional[PulseEvent] = None

    def submit(self, event: PulseEvent) -> None:
        """Queue a pulse event for consideration."""
        self.history.append(event)

    def choose_focus(self) -> Optional[PulseEvent]:
        """Pick the winning event and return it."""
        if not self.history:
            return None
        self.history.sort(key=lambda e: e.score())
        self.last_focus = self.history[0]
        return self.last_focus

    def focus_snapshot(self) -> Dict[str, Any]:
        """Return a compact focus representation for the pulse bus."""
        winner = self.last_focus
        if not winner:
            return {"topic": "", "priority": "normal", "source": "attention_arbitrator"}
        return {
            "topic": winner.payload.get("topic", ""),
            "priority": winner.priority,
            "source": winner.origin,
            "context": winner.context,
        }

    def context_window(self, limit: int = 5) -> Dict[str, Any]:
        """Summarize the most recent events for downstream consumers."""
        tail = self.history[-limit:]
        return {
            "summary": [event.payload for event in tail],
            "window": [event.origin for event in tail],
            "last_update": tail[-1].timestamp if tail else None,
        }

    def reset(self) -> None:
        self.history.clear()
        self.last_focus = None


__all__ = ["AttentionArbitrator", "PulseEvent", "PRIORITY_ORDER"]
