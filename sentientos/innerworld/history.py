"""Bounded, deterministic cycle history for inner-world introspection."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Deque, Dict, List


class CycleHistory:
    """Store deterministic, defensive snapshots of inner-world cycles."""

    def __init__(self, maxlen: int = 50):
        """Store up to maxlen cycle snapshots deterministically."""

        self._buffer: Deque[dict] = deque(maxlen=maxlen)

    def record(self, cycle_report: dict) -> None:
        """Add a defensive snapshot of a cycle report."""

        self._buffer.append(deepcopy(cycle_report))

    def get_recent(self, n: int = 10) -> List[dict]:
        """Return up to n most recent snapshots (defensive copies)."""

        if n <= 0:
            return []

        recent = list(self._buffer)[-n:]
        return [deepcopy(item) for item in recent]

    def get_all(self) -> List[dict]:
        """Return all stored snapshots."""

        return [deepcopy(item) for item in list(self._buffer)]

    def summarize(self) -> Dict[str, object]:
        """Return a deterministic summary (counts, trend values)."""

        snapshots = list(self._buffer)
        count = len(snapshots)

        qualia_totals: Dict[str, float] = {}
        qualia_counts: Dict[str, int] = {}
        conflict_count = 0
        metacog_notes = 0

        for snapshot in snapshots:
            qualia = snapshot.get("qualia") if isinstance(snapshot, dict) else {}
            if isinstance(qualia, dict):
                for channel, value in qualia.items():
                    if isinstance(value, (int, float)):
                        qualia_totals[channel] = qualia_totals.get(channel, 0.0) + float(value)
                        qualia_counts[channel] = qualia_counts.get(channel, 0) + 1

            ethics = snapshot.get("ethics") if isinstance(snapshot, dict) else {}
            if isinstance(ethics, dict):
                conflicts = ethics.get("conflicts")
                if conflicts:
                    conflict_count += 1

            metacog = None
            if isinstance(snapshot, dict):
                metacog = snapshot.get("metacog")
                if metacog is None:
                    metacog = snapshot.get("meta")
            if isinstance(metacog, list):
                metacog_notes += len(metacog)

        qualia_trends = {
            channel: qualia_totals[channel] / qualia_counts[channel]
            for channel in qualia_totals
            if qualia_counts.get(channel)
        }

        ethical_conflict_rate = conflict_count / count if count else 0.0

        return {
            "count": count,
            "qualia_trends": qualia_trends,
            "ethical_conflict_rate": ethical_conflict_rate,
            "metacog_note_frequency": metacog_notes,
        }
