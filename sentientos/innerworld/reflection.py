"""Deterministic reflection engine for inner-world cycle history."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, List


class CycleReflectionEngine:
    """Generate deterministic reflective summaries from cycle history."""

    def __init__(self, max_insights: int = 10):
        self.max_insights = max(int(max_insights), 0)

    def reflect(self, history: List[dict]) -> dict:
        """Produce a deterministic reflection summary from cycle history."""

        safe_history = list(history or [])
        trend_summary = self.summarize_trends(safe_history)
        insights = self.extract_insights(safe_history)
        return {
            "trend_summary": trend_summary,
            "insights": insights,
        }

    def summarize_trends(self, history: List[dict]) -> Dict[str, str]:
        """Return categorical trends derived from numeric signals."""

        confidence_series = self._extract_series(history, "qualia", "confidence")
        tension_series = self._extract_series(history, "qualia", "tension")
        metacog_density_series = [
            self._metacog_length(entry) for entry in history if isinstance(entry, dict)
        ]
        conflict_rate = self._ethical_conflict_rate(history)

        return {
            "confidence": self._classify_trend(confidence_series),
            "tension": self._classify_trend(tension_series),
            "ethical_conflict_rate": self._categorize_conflict_rate(conflict_rate),
            "metacog_density": self._classify_trend(metacog_density_series),
        }

    def extract_insights(self, history: List[dict]) -> List[str]:
        """Generate template-based reflections from history trends."""

        if not history:
            return self._limit_insights(["No history available; trends are stable."])

        trends = self.summarize_trends(history)
        insights: List[str] = []

        confidence_trend = trends.get("confidence", "stable")
        if confidence_trend == "rising":
            insights.append("Over recent cycles, confidence has increased.")
        elif confidence_trend == "falling":
            insights.append("Over recent cycles, confidence has decreased.")
        else:
            insights.append("Confidence has remained stable across cycles.")

        tension_trend = trends.get("tension", "stable")
        if tension_trend == "rising":
            insights.append("Tension levels are rising.")
        elif tension_trend == "falling":
            insights.append("Tension levels are falling.")
        else:
            insights.append("Tension levels are stable.")

        conflict_category = trends.get("ethical_conflict_rate", "none")
        conflict_insight_map = {
            "high": "Ethical conflicts occur frequently.",
            "moderate": "Ethical conflicts appear intermittently.",
            "low": "Ethical conflicts remain low.",
            "none": "No ethical conflicts observed.",
        }
        insights.append(conflict_insight_map.get(conflict_category, "No ethical conflicts observed."))

        metacog_trend = trends.get("metacog_density", "stable")
        if metacog_trend == "rising":
            insights.append("Metacognitive note density is rising.")
        elif metacog_trend == "falling":
            insights.append("Metacognitive note density is falling.")
        else:
            insights.append("Metacognitive note density is stable.")

        return self._limit_insights(insights)

    def _limit_insights(self, insights: List[str]) -> List[str]:
        if self.max_insights <= 0:
            return []
        return insights[: self.max_insights]

    def _extract_series(self, history: List[dict], *path: str) -> List[float]:
        series: List[float] = []
        for entry in history:
            if not isinstance(entry, dict):
                continue
            cursor = deepcopy(entry)
            for key in path:
                if isinstance(cursor, dict):
                    cursor = cursor.get(key)
                else:
                    cursor = None
                    break
            if isinstance(cursor, (int, float)):
                series.append(float(cursor))
        return series

    def _classify_trend(self, values: List[float]) -> str:
        if len(values) < 2:
            return "stable"
        delta = values[-1] - values[0]
        tolerance = 1e-6
        if delta > tolerance:
            return "rising"
        if delta < -tolerance:
            return "falling"
        return "stable"

    def _ethical_conflict_rate(self, history: List[dict]) -> float:
        if not history:
            return 0.0
        conflict_cycles = 0
        for entry in history:
            if not isinstance(entry, dict):
                continue
            ethics = entry.get("ethics") if isinstance(entry, dict) else {}
            conflicts = ethics.get("conflicts") if isinstance(ethics, dict) else None
            if conflicts:
                conflict_cycles += 1
        return conflict_cycles / len(history)

    def _categorize_conflict_rate(self, rate: float) -> str:
        if rate == 0:
            return "none"
        if rate >= 0.75:
            return "high"
        if rate >= 0.34:
            return "moderate"
        return "low"

    def _metacog_length(self, entry: dict) -> int:
        metacog = None
        if isinstance(entry, dict):
            metacog = entry.get("metacog")
            if metacog is None:
                metacog = entry.get("meta")
        if isinstance(metacog, list):
            return len(metacog)
        return 0
