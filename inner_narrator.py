"""Inner Narrator for post-cycle introspective logging.

This scaffold captures reflective summaries with mood and confidence metadata
and keeps an in-memory log suitable for serialization to the glow store.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, List


@dataclass
class Reflection:
    """Simple reflection entry."""

    timestamp: str
    summary: str
    mood: str
    confidence: float
    focus: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "summary": self.summary,
            "mood": self.mood,
            "confidence": self.confidence,
            "focus": self.focus,
            "tags": self.tags,
        }


class InnerNarrator:
    """Collects reflections for each runtime cycle."""

    def __init__(self) -> None:
        self.log: List[Reflection] = []

    def reflect(
        self,
        summary: str,
        mood: str = "stable",
        confidence: float = 0.5,
        focus: str = "",
        tags: Iterable[str] | None = None,
    ) -> Reflection:
        entry = Reflection(
            timestamp=datetime.utcnow().isoformat() + "Z",
            summary=summary,
            mood=mood,
            confidence=confidence,
            focus=focus,
            tags=list(tags) if tags else [],
        )
        self.log.append(entry)
        return entry

    def latest(self) -> Reflection | None:
        return self.log[-1] if self.log else None

    def persist(self, path: Path) -> None:
        """Append reflections to a JSONL file."""
        if not self.log:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for reflection in self.log:
                handle.write(json.dumps(reflection.to_dict()) + "\n")


__all__ = ["InnerNarrator", "Reflection"]
