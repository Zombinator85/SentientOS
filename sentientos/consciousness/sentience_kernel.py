# NOTE:
# This module is part of the Consciousness Layer scaffolding.
# It does not perform autonomous execution.
# All operations must be driven by explicit orchestrator calls.
# Guardrails and covenant autoalignment remain authoritative.
"""Goal-selection scaffolding for the Consciousness Layer.

The kernel keeps goals minimal, auditable, and covenant-aligned, exposing a
``run_cycle`` hook for kernel orchestration. See
``docs/CONSCIOUSNESS_LAYER.md`` for architectural context.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Mapping, Optional

from sentientos.daemons import pulse_bus
from sentientos.glow.self_state import load as load_self_state, update as update_self_state
from sentientos.integrity import covenant_autoalign

logger = logging.getLogger(__name__)


GoalDict = Dict[str, object]
PulseEmitter = Callable[[Dict[str, object]], Dict[str, object]]


@dataclass
class KernelProposal:
    """Container for kernel-generated intentions."""

    goal: str
    rationale: str
    confidence: float = 0.5


class SentienceKernel:
    """Autonomous goal generator with covenant guardrails."""

    def __init__(self, *, emitter: PulseEmitter | None = None, self_path: Optional[str] = None) -> None:
        self.proposals: List[KernelProposal] = []
        self._last_cycle: datetime | None = None
        self._recent_failures: int = 0
        self._emitter: PulseEmitter = emitter or pulse_bus.publish
        self._self_path = self_path

    def _clamp_priority(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _should_generate_goal(
        self,
        state: Mapping[str, object],
        *,
        pressure_snapshot: Mapping[str, object] | None = None,
    ) -> tuple[bool, str]:
        idle = state.get("last_focus") in (None, "")
        goal_context = state.get("goal_context") if isinstance(state.get("goal_context"), dict) else {}
        system_load = goal_context.get("system_load", 0.2)
        try:
            low_load = float(system_load) < 0.5
        except (TypeError, ValueError):
            low_load = True
        novelty_score = float(state.get("novelty_score", 0.0) or 0.0)
        curiosity_trigger = novelty_score < 0.6

        if self._recent_failures >= 3:
            return False, "distress_guardrail_active"
        if not (idle or curiosity_trigger) and not low_load:
            return False, "high_priority_activity"
        trigger = "curiosity" if curiosity_trigger else "idle"
        if pressure_snapshot and bool(pressure_snapshot.get("overload")) and trigger == "curiosity":
            return True, "reflection_overload"
        return True, trigger

    def _misaligned_goal(self, goal: GoalDict) -> bool:
        description = str(goal.get("description", "")).lower()
        forbidden_markers = [
            "external call",
            "network request",
            "privilege escalation",
            "modify covenant",
            "self-modification",
        ]
        if any(marker in description for marker in forbidden_markers):
            return True
        if goal.get("goal_type") not in {"optimization", "reflection", "curiosity_probe"}:
            return True
        priority = goal.get("priority")
        return not isinstance(priority, (int, float)) or not 0.0 <= float(priority) <= 1.0

    def _build_goal(self, state: Mapping[str, object], trigger: str) -> GoalDict:
        mood = str(state.get("mood", "neutral"))
        confidence = float(state.get("confidence", 0.5) or 0.5)
        novelty_score = float(state.get("novelty_score", 0.0) or 0.0)
        baseline = 0.35 if trigger == "idle" else 0.45
        novelty_boost = (0.6 - novelty_score) * 0.25
        confidence_boost = (confidence - 0.5) * 0.4
        priority = self._clamp_priority(baseline + novelty_boost + confidence_boost)

        goal_type = "curiosity_probe" if trigger == "curiosity" else "reflection"
        description = (
            "Run a brief reflective scan for novel internal signals"
            if goal_type == "curiosity_probe"
            else "Summarize recent focus and tune internal readiness"
        )
        context = {
            "mood": mood,
            "confidence": round(confidence, 3),
            "novelty_score": round(novelty_score, 3),
            "trigger": trigger,
        }

        return {
            "goal_type": goal_type,
            "description": description,
            "priority": round(priority, 3),
            "context": context,
            "origin": "sentience_kernel",
        }

    def emit_goal_event(self, goal: GoalDict, focus: str | None) -> Dict[str, object]:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "sentience_kernel",
            "event_type": "internal_goal",
            "priority": "info",
            "payload": {
                "goal": goal,
                "attention_hint": focus,
            },
            "focus": focus,
            "context": goal.get("context", {}),
            "internal_priority": goal.get("priority", 0.0),
            "event_origin": "system",
        }
        enriched = pulse_bus.apply_pulse_defaults(event)
        return self._emitter(enriched)

    def _update_self_model(
        self, *, goal: GoalDict | None, result: str, attention_hint: str | None, novelty_score: float
    ) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "last_cycle_result": result,
            "novelty_score": round(max(0.0, novelty_score), 3),
            "attention_hint": attention_hint,
        }
        if goal:
            payload["last_generated_goal"] = goal
            payload["goal_context"] = goal.get("context", {})
        return update_self_state(payload, path=self._self_path)

    def run_cycle(self, *, pressure_snapshot: Mapping[str, object] | None = None) -> Dict[str, object]:
        covenant_autoalign.autoalign_before_cycle()
        self._last_cycle = datetime.now(timezone.utc)
        glow_state = load_self_state(path=self._self_path)
        should_generate, trigger = self._should_generate_goal(glow_state, pressure_snapshot=pressure_snapshot)
        report: Dict[str, object] = {
            "timestamp": self._last_cycle.isoformat(),
            "generated": False,
            "reason": trigger,
            "goal": None,
            "emitted": False,
        }

        if not should_generate:
            self._update_self_model(goal=None, result=trigger, attention_hint=glow_state.get("attention_hint"), novelty_score=float(glow_state.get("novelty_score", 0.0) or 0.0))
            return report

        goal = self._build_goal(glow_state, trigger)
        if pressure_snapshot:
            goal_context = goal.get("context", {}) if isinstance(goal.get("context"), dict) else {}
            goal_context.update({
                "pressure_total": pressure_snapshot.get("total_active_pressure", 0),
                "pressure_overload": bool(pressure_snapshot.get("overload")),
            })
            goal["context"] = goal_context
        if self._misaligned_goal(goal):
            logger.warning("Discarded misaligned goal from sentience kernel", extra={"goal": goal})
            self._recent_failures += 1
            self._update_self_model(goal=None, result="misaligned", attention_hint=glow_state.get("attention_hint"), novelty_score=float(glow_state.get("novelty_score", 0.0) or 0.0))
            report["reason"] = "misaligned"
            return report

        attention_hint = glow_state.get("last_focus") if isinstance(glow_state.get("last_focus"), str) else None
        emitted = False
        try:
            self.emit_goal_event(goal, attention_hint)
            emitted = True
            self._recent_failures = 0
        except Exception:
            self._recent_failures += 1
            logger.exception("Failed to emit sentience kernel goal event")

        novelty_score = float(glow_state.get("novelty_score", 0.0) or 0.0)
        novelty_score = max(0.0, novelty_score + (0.05 if emitted else -0.02))
        self._update_self_model(
            goal=goal if emitted else None,
            result="emitted" if emitted else "emit_failed",
            attention_hint=attention_hint,
            novelty_score=novelty_score,
        )

        self.proposals.append(
            KernelProposal(
                goal=goal["description"],
                rationale="autonomous_generation",
                confidence=float(goal.get("priority", 0.0)),
            )
        )

        report.update({"generated": True, "goal": goal, "emitted": emitted, "reason": trigger})
        return report


_KERNEL = SentienceKernel()


def run_cycle() -> Dict[str, object]:
    """Execute a kernel cycle for the Consciousness Layer."""

    return _KERNEL.run_cycle()


__all__ = ["KernelProposal", "SentienceKernel", "run_cycle"]
