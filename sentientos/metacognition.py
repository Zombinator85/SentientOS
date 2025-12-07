"""Stage 3: Rule-based metacognitive monitoring for SentientOS."""

from __future__ import annotations

from typing import Dict, List


class MetaMonitor:
    """Inspect and record reflections on current cognitive state."""

    def __init__(self, max_notes: int = 50) -> None:
        self._notes: List[Dict[str, object]] = []
        self._counter: int = 0
        self._max_notes = max_notes

    def _next_timestamp(self) -> int:
        self._counter += 1
        return self._counter

    def _add_note(self, level: str, message: str) -> Dict[str, object]:
        note = {
            "timestamp": self._next_timestamp(),
            "level": level,
            "message": message,
        }
        self._notes.append(note)
        if len(self._notes) > self._max_notes:
            self._notes = self._notes[-self._max_notes :]
        return note

    def review_cycle(self, state: Dict[str, float]) -> List[Dict[str, object]]:
        """Perform a deterministic metacognitive review of the provided state."""

        new_notes: List[Dict[str, object]] = []

        confidence = state.get("confidence")
        if confidence is not None and confidence < 0.3:
            new_notes.append(self._add_note("warning", "Low confidence detected."))

        tension = state.get("tension")
        if tension is not None and tension > 0.7:
            new_notes.append(self._add_note("warning", "Elevated tension detected."))

        errors = state.get("errors")
        if errors is not None and errors > 0:
            new_notes.append(self._add_note("info", "Errors observed in cycle."))

        return [note.copy() for note in new_notes]

    def get_recent_notes(self, limit: int = 10) -> List[Dict[str, object]]:
        """Retrieve recent metacognitive observations."""

        if limit <= 0:
            return []
        return [note.copy() for note in self._notes[-limit:]]
