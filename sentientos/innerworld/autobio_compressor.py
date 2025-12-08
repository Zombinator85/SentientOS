"""Deterministic autobiographical compressor."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Dict, List, Mapping


class AutobiographicalCompressor:
    """Compress narrative artifacts into stable autobiographical entries."""

    def __init__(self, max_entries: int = 10) -> None:
        """Store compressed autobiographical milestones."""

        self.max_entries = max(int(max_entries), 1)
        self._entries: List[Dict[str, Any]] = []
        self._entry_counter = 0

    def compress(
        self,
        chapters: List[Mapping[str, Any]],
        reflection_summary: Mapping[str, Any],
        identity_summary: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a compressed autobiographical entry from current summaries.
        """

        chapter_snapshot = [deepcopy(chapter) for chapter in (chapters or [])]
        reflection_snapshot = deepcopy(reflection_summary or {})
        identity_snapshot = deepcopy(identity_summary or {})

        self._entry_counter += 1
        dominant_themes = self._dominant_themes(chapter_snapshot)
        core_insights = self._core_insights(reflection_snapshot)
        identity_shift = self._identity_shift(identity_snapshot)

        return {
            "entry_id": self._entry_counter,
            "dominant_themes": dominant_themes,
            "core_insights": core_insights,
            "identity_shift": identity_shift,
        }

    def record(self, entry: Mapping[str, Any]):
        """Insert into FIFO memory."""

        self._entries.append(deepcopy(entry))
        if len(self._entries) > self.max_entries:
            self._entries.pop(0)

    def get_entries(self) -> List[Dict[str, Any]]:
        """Return defensive copies."""

        return [deepcopy(entry) for entry in self._entries]

    def _dominant_themes(self, chapters: List[Mapping[str, Any]]) -> Dict[str, str]:
        qualia_values = [chapter.get("qualia_theme") for chapter in chapters if isinstance(chapter, Mapping)]
        ethical_values = [chapter.get("ethical_theme") for chapter in chapters if isinstance(chapter, Mapping)]
        metacog_values = [chapter.get("metacog_theme") for chapter in chapters if isinstance(chapter, Mapping)]

        return {
            "qualia": self._most_common(qualia_values, default="stable"),
            "ethics": self._most_common(ethical_values, default="low"),
            "metacognition": self._most_common(metacog_values, default="low"),
        }

    def _core_insights(self, reflection_summary: Mapping[str, Any]) -> List[str]:
        if not isinstance(reflection_summary, Mapping):
            return []
        insights = reflection_summary.get("insights")
        if isinstance(insights, list):
            normalized = [insight for insight in insights if isinstance(insight, str)]
            return normalized[:3]
        return []

    def _identity_shift(self, identity_summary: Mapping[str, Any]) -> str:
        if not isinstance(identity_summary, Mapping):
            return "stable"
        core = identity_summary.get("core_themes")
        if isinstance(core, Mapping):
            values = [value for value in core.values() if isinstance(value, str)]
            if any(value in {"shifting", "volatile"} for value in values):
                return "shifting"
        return "stable"

    def _most_common(self, values: List[Any], default: str) -> str:
        filtered = [value for value in values if isinstance(value, str)]
        if not filtered:
            return default
        counts = Counter(filtered)
        max_count = max(counts.values())
        candidates = [value for value, count in counts.items() if count == max_count]
        candidates.sort()
        return candidates[0] if candidates else default
