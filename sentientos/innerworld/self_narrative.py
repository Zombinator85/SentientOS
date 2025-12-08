"""Deterministic self-narrative engine for autobiographical summaries."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Dict, List


class SelfNarrativeEngine:
    """Manage structured narrative chapters derived from cognitive reports."""

    QUALIA_ORDER = ("stable", "shifting", "volatile")
    ETHICAL_ORDER = ("low", "moderate", "high", "critical")
    METACOG_ORDER = ("low", "moderate", "high")

    def __init__(self, max_chapters: int = 20):
        """Manage narrative chapters summarizing internal development."""

        self.max_chapters = max(int(max_chapters), 1)
        self._chapters: List[Dict[str, Any]] = []
        self._chapter_counter = 0

    def update_chapter(self, cognitive_report: dict) -> None:
        """Derive and append a narrative chapter from a cognitive report."""

        report_snapshot = deepcopy(cognitive_report or {})
        overview = report_snapshot.get("overview", {}) if isinstance(report_snapshot, dict) else {}
        trend_summary = (
            deepcopy(report_snapshot.get("trend_analysis", {}))
            if isinstance(report_snapshot, dict)
            else {}
        )
        insights = deepcopy(report_snapshot.get("insights", [])) if isinstance(report_snapshot, dict) else []

        self._chapter_counter += 1
        chapter = {
            "chapter_id": self._chapter_counter,
            "qualia_theme": self._select_theme(
                overview, "qualia_stability", self.QUALIA_ORDER, default=self.QUALIA_ORDER[0]
            ),
            "ethical_theme": self._select_theme(
                overview, "ethical_signal", self.ETHICAL_ORDER, default=self.ETHICAL_ORDER[0]
            ),
            "metacog_theme": self._select_theme(
                overview, "metacog_activity", self.METACOG_ORDER, default=self.METACOG_ORDER[0]
            ),
            "trend_highlights": trend_summary if isinstance(trend_summary, dict) else {},
            "key_insights": insights[:3] if isinstance(insights, list) else [],
        }

        self._chapters.append(chapter)
        if len(self._chapters) > self.max_chapters:
            self._chapters.pop(0)

    def get_chapters(self) -> list[dict]:
        """Return defensive copies of stored chapters."""

        return deepcopy(self._chapters)

    def summarize_identity(self) -> dict:
        """
        Return a stable, deterministic identity snapshot:
        - dominant cognitive trends
        - recurring insights
        - stability metrics
        - ethical character profile
        - meta-patterns over time
        """

        if not self._chapters:
            return {
                "core_themes": {
                    "qualia": self.QUALIA_ORDER[0],
                    "ethics": self.ETHICAL_ORDER[0],
                    "metacognition": self.METACOG_ORDER[0],
                },
                "recurring_insights": [],
                "chapter_count": 0,
            }

        qualia_values = [chapter.get("qualia_theme") for chapter in self._chapters]
        ethics_values = [chapter.get("ethical_theme") for chapter in self._chapters]
        metacog_values = [chapter.get("metacog_theme") for chapter in self._chapters]

        return {
            "core_themes": {
                "qualia": self._dominant_theme(qualia_values, self.QUALIA_ORDER, self.QUALIA_ORDER[0]),
                "ethics": self._dominant_theme(ethics_values, self.ETHICAL_ORDER, self.ETHICAL_ORDER[0]),
                "metacognition": self._dominant_theme(
                    metacog_values, self.METACOG_ORDER, self.METACOG_ORDER[0]
                ),
            },
            "recurring_insights": self._aggregate_insights(limit=5),
            "chapter_count": len(self._chapters),
        }

    def _select_theme(
        self, source: Dict[str, Any], key: str, allowed: tuple[str, ...], default: str
    ) -> str:
        if not isinstance(source, dict):
            return default
        value = source.get(key)
        if isinstance(value, str) and value in allowed:
            return value
        return default

    def _dominant_theme(self, values: List[str], order: tuple[str, ...], default: str) -> str:
        filtered = [value for value in values if isinstance(value, str) and value in order]
        if not filtered:
            return default
        counts = Counter(filtered)
        max_count = max(counts.values())
        candidates = [value for value in order if counts.get(value, 0) == max_count]
        return candidates[0] if candidates else default

    def _aggregate_insights(self, limit: int) -> List[str]:
        seen = set()
        ordered_insights: List[str] = []
        for chapter in self._chapters:
            for insight in chapter.get("key_insights", []):
                if not isinstance(insight, str):
                    continue
                if insight in seen:
                    continue
                seen.add(insight)
                ordered_insights.append(insight)
                if len(ordered_insights) >= limit:
                    return ordered_insights
        return ordered_insights
