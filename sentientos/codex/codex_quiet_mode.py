"""Codex quiet mode contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class QuietPlan:
    suggested: bool
    reasons: tuple[str, ...]
    effects: dict[str, str]
    override: str = "Human override permitted"

    def to_dict(self) -> dict[str, object]:
        return {
            "suggested": self.suggested,
            "reasons": list(self.reasons),
            "effects": dict(self.effects),
            "override": self.override,
        }


class CodexQuietMode:
    """Recommend self-quieting when the system is stable."""

    def __init__(self, delta_threshold: float = 0.05) -> None:
        self.delta_threshold = float(delta_threshold)

    def assess(
        self,
        context_stable: bool,
        degradation_signals: Iterable[Mapping[str, object]],
        observer_delta: float,
    ) -> dict[str, object]:
        has_degradation = any(degradation_signals)
        low_delta = float(observer_delta) <= self.delta_threshold
        suggested = context_stable and not has_degradation and low_delta

        reasons = self._reasons(context_stable, has_degradation, low_delta)
        plan = QuietPlan(
            suggested=suggested,
            reasons=tuple(reasons),
            effects={
                "expansion_proposals": "suppressed" if suggested else "allowed",
                "self_repair": "allowed",
                "restructuring": "paused" if suggested else "enabled",
                "governance": "human override always allowed",
            },
        )

        return {"quiet": suggested, "plan": plan, "details": plan.to_dict()}

    def _reasons(self, context_stable: bool, has_degradation: bool, low_delta: bool) -> list[str]:
        reasons: list[str] = []
        if not context_stable:
            reasons.append("Context load still shifting")
        if has_degradation:
            reasons.append("Degradation signals present")
        if not low_delta:
            reasons.append("Observers reporting material deltas")
        if not reasons:
            reasons.append("Context stable with minimal observer delta")
        return reasons


__all__ = ["CodexQuietMode", "QuietPlan"]
