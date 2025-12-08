"""Deterministic inner dialogue generator."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping


class InnerDialogueEngine:
    """Generate deterministic, analytical inner dialogue."""

    def __init__(self, max_lines: int = 3) -> None:
        """Generate deterministic internal monologue lines."""

        self.max_lines = max(int(max_lines), 1)

    def generate(
        self,
        spotlight: Mapping[str, Any],
        reflection: Mapping[str, Any],
        cognitive_report: Mapping[str, Any],
    ) -> List[str]:
        """
        Produce deterministic template-driven lines.
        """

        spotlight_snapshot = deepcopy(spotlight or {})
        reflection_snapshot = deepcopy(reflection or {})
        report_snapshot = deepcopy(cognitive_report or {})

        lines: List[str] = []
        lines.append(self._format_focus_line(spotlight_snapshot))

        trend_line = self._format_trend_line(reflection_snapshot)
        if trend_line:
            lines.append(trend_line)

        identity_line = self._format_identity_line(report_snapshot)
        if identity_line:
            lines.append(identity_line)

        return lines[: self.max_lines]

    def _format_focus_line(self, spotlight: Mapping[str, Any]) -> str:
        focus = spotlight.get("focus", "planning") if isinstance(spotlight, Mapping) else "planning"
        drivers = spotlight.get("drivers", {}) if isinstance(spotlight, Mapping) else {}
        primary_driver = self._primary_driver(drivers)
        return f"Focus on {focus} due to {primary_driver}."

    def _primary_driver(self, drivers: Mapping[str, Any]) -> str:
        if not isinstance(drivers, Mapping):
            return "baseline status"
        ordered_keys = (
            "conflict_severity",
            "conflict_count",
            "qualia_tension",
            "reflection_volatility",
            "identity_shift",
            "metacog_density",
        )
        for key in ordered_keys:
            value = drivers.get(key)
            if value in (None, "none"):
                continue
            if isinstance(value, (int, float)) and float(value) == 0.0:
                continue
            return f"{key}={value}"
        return "baseline status"

    def _format_trend_line(self, reflection: Mapping[str, Any]) -> str:
        if not isinstance(reflection, Mapping):
            return ""
        trends = reflection.get("trend_summary")
        if isinstance(trends, Mapping) and trends:
            trend_parts = [f"{key}:{value}" for key, value in sorted(trends.items()) if value is not None]
            if trend_parts:
                trend_text = ", ".join(trend_parts)
                return f"Recent cycles show {trend_text}."
        return "Recent cycles show stable patterns."

    def _format_identity_line(self, cognitive_report: Mapping[str, Any]) -> str:
        if not isinstance(cognitive_report, Mapping):
            return ""
        overview = cognitive_report.get("overview")
        if not isinstance(overview, Mapping):
            return "Identity remains stable."
        qualia_status = overview.get("qualia_stability", "stable")
        ethical_signal = overview.get("ethical_signal", "low")
        metacog = overview.get("metacog_activity", "low")
        return (
            "Identity remains "
            f"qualia={qualia_status}, ethics={ethical_signal}, metacognition={metacog}."
        )
