"""Deterministic global workspace spotlight selection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping


class GlobalWorkspace:
    """Compute a deterministic attention spotlight for a cognition cycle."""

    def __init__(self) -> None:
        """Initialize empty spotlight state."""

    def compute_spotlight(
        self,
        qualia: Mapping[str, Any],
        meta_notes: List[Mapping[str, Any]],
        ethics: Mapping[str, Any] | None,
        reflection: Mapping[str, Any],
        identity_summary: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """
        Deterministically choose a dominant focus theme.

        Returns:
            {
                "focus": "ethics|tension|identity|uncertainty|planning|reflection",
                "drivers": {...}
            }
        """

        qualia_snapshot = deepcopy(qualia or {})
        meta_snapshot = [deepcopy(note) for note in (meta_notes or [])]
        ethics_snapshot = deepcopy(ethics or {})
        reflection_snapshot = deepcopy(reflection or {})
        identity_snapshot = deepcopy(identity_summary or {})

        drivers = self._derive_drivers(
            qualia_snapshot, meta_snapshot, ethics_snapshot, reflection_snapshot, identity_snapshot
        )

        if drivers["ethical_conflict"]:
            focus = "ethics"
        elif drivers["tension_rising"]:
            focus = "tension"
        elif drivers["identity_shift"]:
            focus = "identity"
        elif drivers["metacog_dense"]:
            focus = "reflection"
        else:
            focus = "planning"

        return {"focus": focus, "drivers": drivers}

    def _derive_drivers(
        self,
        qualia: Mapping[str, Any],
        meta_notes: List[Mapping[str, Any]],
        ethics: Mapping[str, Any],
        reflection: Mapping[str, Any],
        identity_summary: Mapping[str, Any],
    ) -> Dict[str, Any]:
        conflict_count = self._count_conflicts(ethics)
        severity_label = self._extract_severity(ethics)
        metacog_density = len(meta_notes)
        qualia_tension = self._qualia_tension(qualia)
        reflection_volatility = self._reflection_volatility(reflection)
        identity_shift = self._identity_shift(identity_summary)

        ethical_conflict = conflict_count >= 2 or severity_label in {"high", "critical"}
        tension_rising = qualia_tension >= 1.0 or reflection_volatility == "rising"
        metacog_dense = metacog_density >= 3

        return {
            "conflict_count": conflict_count,
            "conflict_severity": severity_label,
            "qualia_tension": qualia_tension,
            "reflection_volatility": reflection_volatility,
            "identity_shift": identity_shift,
            "metacog_density": metacog_density,
            "ethical_conflict": ethical_conflict,
            "tension_rising": tension_rising,
            "metacog_dense": metacog_dense,
        }

    def _count_conflicts(self, ethics: Mapping[str, Any]) -> int:
        conflicts = ethics.get("conflicts") if isinstance(ethics, Mapping) else []
        if not isinstance(conflicts, list):
            return 0
        return len(conflicts)

    def _extract_severity(self, ethics: Mapping[str, Any]) -> str:
        if not isinstance(ethics, Mapping):
            return "none"
        severity = ethics.get("severity") or ethics.get("signal") or ethics.get("ethical_signal")
        if isinstance(severity, str):
            return severity
        return "none"

    def _qualia_tension(self, qualia: Mapping[str, Any]) -> float:
        if not isinstance(qualia, Mapping):
            return 0.0
        stress = qualia.get("errors") or 0.0
        novelty = qualia.get("novelty") or 0.0
        progress_gap = 1.0 - float(qualia.get("progress", 1.0)) if "progress" in qualia else 0.0

        numeric_parts = [value for value in (stress, novelty, progress_gap) if isinstance(value, (int, float))]
        if not numeric_parts:
            return 0.0
        return float(sum(numeric_parts)) / float(len(numeric_parts))

    def _reflection_volatility(self, reflection: Mapping[str, Any]) -> str:
        if not isinstance(reflection, Mapping):
            return "stable"
        trend = reflection.get("trend_summary")
        if isinstance(trend, Mapping):
            volatility = trend.get("volatility")
            if isinstance(volatility, str):
                return volatility
        return "stable"

    def _identity_shift(self, identity_summary: Mapping[str, Any]) -> bool:
        if not isinstance(identity_summary, Mapping):
            return False
        core_themes = identity_summary.get("core_themes")
        if not isinstance(core_themes, Mapping):
            return False
        values = list(core_themes.values())
        if any(value in {"shifting", "volatile"} for value in values if isinstance(value, str)):
            return True
        return False
