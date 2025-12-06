"""Consciousness Layer inner narrator scaffold.

Provides the Consciousness Layer narration hooks outlined in
``docs/CONSCIOUSNESS_LAYER.md`` and exposes a ``run_cycle`` entrypoint.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from sentientos.glow import self_state

logger = logging.getLogger(__name__)


@dataclass
class Reflection:
    """Simple reflection entry."""

    timestamp: str
    summary: str
    mood: str
    confidence: float
    focus: str = ""


class InnerNarrator:
    """Collects reflections for each runtime cycle."""

    def __init__(self) -> None:
        self.log: List[Reflection] = []
        self._last_cycle: datetime | None = None

    def reflect(self, summary: str, mood: str = "stable", confidence: float = 0.5, focus: str = "") -> Reflection:
        entry = Reflection(
            timestamp=datetime.utcnow().isoformat() + "Z",
            summary=summary,
            mood=mood,
            confidence=confidence,
            focus=focus,
        )
        self.log.append(entry)
        return entry

    def latest(self) -> Reflection | None:
        return self.log[-1] if self.log else None

    def run_cycle(self) -> None:
        glow_state = self_state.load()
        self._last_cycle = datetime.now(timezone.utc)
        logger.debug(
            "Inner narrator scaffold cycle executed",
            extra={
                "identity": glow_state.get("identity"),
                "mood": glow_state.get("mood"),
            },
        )


_NARRATOR = InnerNarrator()


def run_cycle() -> None:
    """Execute a placeholder narration cycle for the Consciousness Layer."""

    _NARRATOR.run_cycle()


__all__ = ["InnerNarrator", "Reflection", "run_cycle"]
