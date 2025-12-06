"""Inner narrator scaffold capturing lightweight reflections.

The narrator records summaries and mood snapshots to support self-modeling.
Future iterations should plug into the runtime loop and covenant validators.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List


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


__all__ = ["InnerNarrator", "Reflection"]
