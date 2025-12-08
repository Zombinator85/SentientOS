"""Deterministic cognitive report generator for inner-world snapshots."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Mapping, Any


class CognitiveReportGenerator:
    """Produce structured, deterministic cognitive reports."""

    def __init__(self) -> None:
        """Initialize without external dependencies."""

    def generate(
        self,
        history_summary: Dict[str, Any],
        reflection_summary: Dict[str, Any],
        latest_cycle: Dict[str, Any],
        ethical_report: Dict[str, Any] | None = None,
        simulation_report: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Combine subsystem summaries into a unified cognitive report."""

        history_safe = deepcopy(history_summary or {})
        reflection_safe = deepcopy(reflection_summary or {})
        cycle_safe = deepcopy(latest_cycle or {})
        ethics_safe = deepcopy(ethical_report or {})
        simulation_safe = deepcopy(simulation_report or {})

        overview = {
            "cycle_count": int(cycle_safe.get("cycle_id") or history_safe.get("count", 0)),
            "qualia_stability": self._classify_qualia_stability(
                history_safe.get("qualia_trends", {}), cycle_safe.get("qualia", {})
            ),
            "ethical_signal": self._classify_ethical_signal(
                history_safe.get("ethical_conflict_rate", 0.0)
            ),
            "metacog_activity": self._classify_metacog_density(
                history_safe.get("metacog_note_frequency", 0), history_safe.get("count", 0)
            ),
        }

        trend_analysis = deepcopy(reflection_safe.get("trend_summary", {}))
        insights = deepcopy(reflection_safe.get("insights", []))

        report = {
            "overview": overview,
            "trend_analysis": trend_analysis,
            "insights": insights,
            "recent_cycle": {
                "qualia": deepcopy(cycle_safe.get("qualia", {})),
                "ethics": ethics_safe,
                "meta": deepcopy(cycle_safe.get("meta", [])),
            },
            "simulation_notes": simulation_safe,
            "diagnostics": {
                "history_size": history_safe.get("count", 0),
                "conflict_rate": history_safe.get("ethical_conflict_rate", 0.0),
                "metacog_frequency": history_safe.get("metacog_note_frequency", 0),
            },
        }

        return report

    def _classify_qualia_stability(
        self, qualia_trends: Mapping[str, Any], latest_qualia: Mapping[str, Any]
    ) -> str:
        if not qualia_trends or not latest_qualia:
            return "stable"

        deviations = []
        for key, baseline in qualia_trends.items():
            current_value = latest_qualia.get(key)
            if isinstance(baseline, (int, float)) and isinstance(current_value, (int, float)):
                deviations.append(abs(float(current_value) - float(baseline)))

        if not deviations:
            return "stable"

        max_deviation = max(deviations)
        if max_deviation < 0.25:
            return "stable"
        if max_deviation < 0.75:
            return "shifting"
        return "volatile"

    def _classify_ethical_signal(self, conflict_rate: float) -> str:
        if conflict_rate <= 0:
            return "low"
        if conflict_rate < 0.25:
            return "moderate"
        if conflict_rate < 0.5:
            return "high"
        return "critical"

    def _classify_metacog_density(self, note_count: int, history_size: int) -> str:
        cycles = max(int(history_size), 1)
        rate = float(note_count) / float(cycles)
        if rate < 1.0:
            return "low"
        if rate < 2.0:
            return "moderate"
        return "high"
