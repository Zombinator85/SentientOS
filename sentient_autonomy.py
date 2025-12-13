"""Autonomous Sentient Script planning for the Sentient Mesh."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

import memory_governor
from sentient_mesh import MeshJob, SentientMesh

__all__ = [
    "AutonomyPlan",
    "SentientAutonomyEngine",
]

# Definition anchor:
# Term: "autonomy"
# Frozen meaning: coordination that queues operator-supplied goals without generating its own incentives.
# See: SEMANTIC_GLOSSARY.md#autonomy

# Boundary assertion:
# This module does not originate goals, preferences, or incentives; it schedules operator-supplied strings without reward loops.
# Any priority value is copied deterministically into job metadata and has no effect on privileges or learning.
# See: NON_GOALS_AND_FREEZE.md §Autonomy freeze, NAIR_CONFORMANCE_AUDIT.md §2 (NO_GRADIENT_INVARIANT)

# Interpretation tripwire:
# If this planning queue is described as "the engine choosing to pursue goals" or "deciding to continue on its own",
# that is incorrect. The queue is a deterministic list of operator-supplied or policy-derived strings with no appetite or desire.
# See: INTERPRETATION_DRIFT_SIGNALS.md §Agency language and §Persistence framing.


@dataclass
class AutonomyPlan:
    """Generated plan produced by the autonomy engine."""

    # Definition anchor:
    # Terms: "goal", "plan"
    # Frozen meaning: goals are operator- or policy-specified strings; plans are deterministic payloads derived from them.
    # See: SEMANTIC_GLOSSARY.md#goal and SEMANTIC_GLOSSARY.md#plan

    plan_id: str
    goal: str
    script: Mapping[str, object]
    created_at: float
    status: str = "pending"
    priority: int = 1
    assigned_node: Optional[str] = None
    confidence: float = 0.5
    bias_vector: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "status": self.status,
            "priority": self.priority,
            "assigned_node": self.assigned_node,
            "created_at": self.created_at,
            "confidence": round(self.confidence, 3),
            "bias_vector": dict(self.bias_vector),
            "script": json.loads(json.dumps(self.script, sort_keys=True)),
        }


class SentientAutonomyEngine:
    """Produces new Sentient Script plans based on mesh state."""

    def __init__(self, mesh: SentientMesh, *, allow_fallback_goals: Optional[bool] = None) -> None:
        self._mesh = mesh
        self._plans: Dict[str, AutonomyPlan] = {}
        self._goal_queue: List[str] = []
        self._lock = threading.RLock()
        self._enabled = False
        self._last_cycle: Optional[float] = None
        self._last_bias: Mapping[str, float] = {}
        env_fallback = os.getenv("SENTIENT_AUTONOMY_ENABLE_FALLBACK", "1")
        self._fallback_enabled = allow_fallback_goals if allow_fallback_goals is not None else env_fallback not in {"0", "false", "False"}

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            self._enabled = True

    def stop(self) -> None:
        with self._lock:
            self._enabled = False

    # -- goal management --------------------------------------------------
    def queue_goal(self, goal: str, *, priority: int = 1) -> str:
        plan_id = f"goal-{uuid.uuid4().hex[:10]}"
        with self._lock:
            self._goal_queue.append(goal)
            self._plans[plan_id] = AutonomyPlan(
                plan_id=plan_id,
                goal=goal,
                script={"goal": goal, "priority": priority},
                created_at=time.time(),
                priority=priority,
            )
        return plan_id

    # -- reflective planning ----------------------------------------------
    def reflective_cycle(self, *, limit: int = 3, force: bool = False) -> List[Dict[str, object]]:
        with self._lock:
            if not self._enabled and not force:
                return []
            metrics = memory_governor.mesh_metrics()
            goals = list(self._goal_queue)
            if not goals and metrics.get("open_goals"):
                goals = [str(goal) for goal in metrics["open_goals"]]
            if not goals:
                if not self._fallback_enabled:
                    return []
                goals = ["stabilise mesh trust", "synchronise council insights"]
            selected = goals[:limit]
            jobs: List[MeshJob] = []
            generated_plans: List[AutonomyPlan] = []
            emotion_bias = metrics.get("emotion_consensus", {})
            for goal in selected:
                plan = self._create_or_update_plan(goal, bias_vector=emotion_bias)
                script_payload = {
                    "goal": goal,
                    "insights": metrics,
                    "bias_vector": plan.bias_vector,
                }
                prompt = self._render_prompt(goal, metrics)
                job = MeshJob(
                    job_id=plan.plan_id,
                    script=script_payload,
                    prompt=prompt,
                    priority=plan.priority,
                    requirements=("sentient_script",),
                    metadata={"origin": "autonomy"},
                )
                jobs.append(job)
                generated_plans.append(plan)
            snapshot = self._mesh.cycle(jobs) if jobs else self._mesh.cycle(())
            now = time.time()
            self._last_cycle = now
            self._last_bias = dict(emotion_bias)
            for plan in generated_plans:
                assignment = snapshot.assignments.get(plan.plan_id)
                plan.assigned_node = assignment
                plan.status = "scheduled" if assignment else "queued"
                plan.confidence = self._estimate_confidence(plan, metrics)
            self._goal_queue = [goal for goal in self._goal_queue if goal not in selected]
            return [plan.to_dict() for plan in generated_plans]

    def _create_or_update_plan(
        self,
        goal: str,
        *,
        bias_vector: Mapping[str, float],
    ) -> AutonomyPlan:
        for plan in self._plans.values():
            if plan.goal == goal:
                plan.bias_vector = dict(bias_vector)
                return plan
        plan_id = f"auto-{uuid.uuid4().hex[:10]}"
        plan = AutonomyPlan(
            plan_id=plan_id,
            goal=goal,
            script={"goal": goal},
            created_at=time.time(),
            bias_vector=dict(bias_vector),
        )
        self._plans[plan_id] = plan
        return plan

    def _render_prompt(self, goal: str, metrics: Mapping[str, object]) -> str:
        histogram = metrics.get("trust_histogram", {})
        council = metrics.get("active_council_sessions", 0)
        summary = json.dumps({"trust": histogram, "council": council}, sort_keys=True)
        return f"Goal: {goal}\nMesh metrics: {summary}"

    def _estimate_confidence(self, plan: AutonomyPlan, metrics: Mapping[str, object]) -> float:
        nodes = max(1, int(metrics.get("nodes", 1)))
        council = max(1, int(metrics.get("active_council_sessions", 1)))
        base = min(0.95, 0.45 + (nodes / (nodes + council)))
        if plan.assigned_node:
            base += 0.1
        return max(0.3, min(0.99, base))

    # -- telemetry --------------------------------------------------------
    def status(self) -> Dict[str, object]:
        with self._lock:
            counts = {"pending": 0, "scheduled": 0, "completed": 0}
            plans = []
            for plan in self._plans.values():
                counts_key = plan.status if plan.status in counts else "pending"
                counts[counts_key] = counts.get(counts_key, 0) + 1
                plans.append(plan.to_dict())
            return {
                "enabled": self._enabled,
                "plans": sorted(plans, key=lambda entry: entry["created_at"], reverse=True),
                "counts": counts,
                "last_cycle": self._last_cycle,
                "bias_vector": dict(self._last_bias),
            }

    def active_plan_ids(self) -> Sequence[str]:
        with self._lock:
            return [plan.plan_id for plan in self._plans.values() if plan.status != "completed"]

    def mark_completed(self, plan_id: str) -> None:
        with self._lock:
            plan = self._plans.get(plan_id)
            if plan:
                plan.status = "completed"
