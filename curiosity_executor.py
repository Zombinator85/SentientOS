"""Curiosity goal execution pipeline hooking into Reflexion and Critic."""

from __future__ import annotations

import json
import time
from typing import Callable, Mapping, Optional

import memory_manager as mm
import reflexion_loop
from curiosity_goal_helper import CuriosityGoalHelper
from oracle_bridge import consult as oracle_consult
from sentientos.metrics import MetricsRegistry


Investigator = Callable[[Mapping[str, object]], Mapping[str, object]]


class CuriosityExecutor:
    """Execute curiosity goals using local search/oracle tools."""

    def __init__(
        self,
        helper: CuriosityGoalHelper,
        *,
        metrics: MetricsRegistry | None = None,
        investigator: Investigator | None = None,
        critic: Optional[object] = None,
    ) -> None:
        self._helper = helper
        self._metrics = metrics
        self._critic = critic
        self._investigator = investigator or self._default_investigator

    def _default_investigator(self, goal_payload: Mapping[str, object]) -> Mapping[str, object]:
        goal = goal_payload.get("goal", {})
        question = goal.get("text", "Curiosity investigation")
        intent = goal.get("intent", {})
        return oracle_consult(question, intent=intent)

    def execute_next(self) -> Optional[Mapping[str, object]]:
        entry = self._helper.pop_goal()
        if entry is None:
            return None
        goal = entry["goal"]
        observation = entry.get("observation", {})
        start = time.monotonic()
        investigation = self._investigator(entry)
        summary = self._summarise_investigation(goal, observation, investigation)
        reflection = reflexion_loop.reflect_curiosity_result(goal, summary)
        stored = mm.store_reflection(reflection)
        critique = None
        if self._critic is not None:
            review_payload = {
                "reflection": stored,
                "disagreement": False,
            }
            try:
                critique = self._critic.review(review_payload, corr_id=goal.get("id", "curiosity"))
            except Exception:
                critique = None
        result = {
            "goal_id": goal.get("id"),
            "observation_id": observation.get("observation_id"),
            "insight_summary": stored.get("insight_summary"),
            "reflection_id": stored.get("reflection_id"),
            "investigation": investigation,
            "reflection": stored,
            "critic": critique,
        }
        if self._metrics is not None:
            self._metrics.increment("reflections_logged_total")
            self._metrics.increment("insights_committed_total")
            elapsed_ms = (time.monotonic() - start) * 1000
            self._metrics.observe("curiosity_execution_latency_ms", elapsed_ms)
        mm.append_memory(
            json.dumps({"curiosity_execution": result}, ensure_ascii=False),
            tags=["curiosity", "executor"],
            source="curiosity_executor",
        )
        self._helper.complete_goal(goal.get("id", ""), result)
        return result

    def drain(self) -> list[Mapping[str, object]]:
        """Execute every pending curiosity goal until the queue is empty."""

        processed: list[Mapping[str, object]] = []
        while True:
            result = self.execute_next()
            if result is None:
                break
            processed.append(result)
        return processed

    def _summarise_investigation(
        self,
        goal: Mapping[str, object],
        observation: Mapping[str, object],
        investigation: Mapping[str, object],
    ) -> Mapping[str, object]:
        question = goal.get("text", "Curiosity investigation")
        insight = investigation.get("recommendation") or investigation.get("insight")
        context = investigation.get("context")
        summary_text = question
        if insight:
            summary_text += f" → {insight}"
        if context:
            preview = "; ".join(str(item) for item in list(context)[:2])
            summary_text += f" | context: {preview}"
        payload = {
            "goal_id": goal.get("id"),
            "observation_id": observation.get("observation_id"),
            "insight_summary": summary_text,
            "insight": insight,
            "context": context,
            "timestamp": time.time(),
        }
        return payload


__all__ = ["CuriosityExecutor"]

