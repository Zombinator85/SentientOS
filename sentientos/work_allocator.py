from __future__ import annotations

from dataclasses import dataclass

from sentientos.goal_graph import Goal, GoalGraph, dependency_unmet, order_goals_deterministic
from sentientos.risk_budget import RiskBudget


@dataclass(frozen=True, slots=True)
class DeferredGoal:
    goal_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class AllocationDecision:
    selected: tuple[str, ...]
    deferred: tuple[DeferredGoal, ...]
    selected_reasons: tuple[dict[str, object], ...]
    budget_summary: dict[str, int]


_RECOVERY_ALLOWED_TAGS = {"integrity", "stability"}
_QUARANTINE_ALLOWED_TAGS = {"integrity", "remediation", "stability"}
_HIGH_PRESSURE_DEPRIORITIZE_TAGS = {"feature", "performance"}


def allocate_goals(
    *,
    graph: GoalGraph,
    budget: RiskBudget,
    operating_mode: str,
    integrity_pressure_level: int,
    quarantine_active: bool,
    posture: str,
) -> AllocationDecision:
    selected: list[str] = []
    selected_reasons: list[dict[str, object]] = []
    deferred: list[DeferredGoal] = []
    spent_risk = 0
    spent_throughput = 0
    all_goal_ids = {goal.goal_id for goal in graph.goals}

    for goal in order_goals_deterministic(graph.goals):
        if not goal.enabled:
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="disabled"))
            continue
        if dependency_unmet(goal, set(selected), all_goal_ids):
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="dependency_unmet"))
            continue
        if _is_mode_blocked(goal, operating_mode):
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="mode_blocked"))
            continue
        if quarantine_active and _is_quarantine_blocked(goal):
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="quarantine_blocked"))
            continue

        score = _goal_score(goal, posture=posture, pressure_level=integrity_pressure_level)
        if spent_risk + goal.risk_cost_estimate > budget.router_k_max:
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="budget_exceeded"))
            continue
        if spent_throughput + goal.throughput_cost_estimate > max(0, budget.router_m_max):
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="throughput_exceeded"))
            continue
        selected.append(goal.goal_id)
        spent_risk += goal.risk_cost_estimate
        spent_throughput += goal.throughput_cost_estimate
        selected_reasons.append(
            {
                "goal_id": goal.goal_id,
                "score": round(score, 6),
                "base_weight": goal.weight,
                "priority": goal.priority,
                "tags": list(goal.tags),
                "risk_cost_estimate": goal.risk_cost_estimate,
                "throughput_cost_estimate": goal.throughput_cost_estimate,
                "posture_multiplier": _posture_multiplier(goal, posture),
                "pressure_multiplier": _pressure_multiplier(goal, integrity_pressure_level),
            }
        )

    return AllocationDecision(
        selected=tuple(selected),
        deferred=tuple(sorted(deferred, key=lambda item: (item.reason, item.goal_id))),
        selected_reasons=tuple(selected_reasons),
        budget_summary={
            "risk_spent": spent_risk,
            "risk_cap": int(budget.router_k_max),
            "throughput_spent": spent_throughput,
            "throughput_cap": int(max(0, budget.router_m_max)),
        },
    )


def _goal_score(goal: Goal, *, posture: str, pressure_level: int) -> float:
    return float(goal.weight) * _posture_multiplier(goal, posture) * _pressure_multiplier(goal, pressure_level) + float(goal.priority)


def _is_mode_blocked(goal: Goal, operating_mode: str) -> bool:
    if operating_mode in {"recovery", "lockdown"}:
        return not any(tag in _RECOVERY_ALLOWED_TAGS for tag in goal.tags)
    return False


def _is_quarantine_blocked(goal: Goal) -> bool:
    return not any(tag in _QUARANTINE_ALLOWED_TAGS for tag in goal.tags)


def _pressure_multiplier(goal: Goal, pressure_level: int) -> float:
    if pressure_level >= 2 and any(tag in _HIGH_PRESSURE_DEPRIORITIZE_TAGS for tag in goal.tags):
        return 0.5
    return 1.0


def _posture_multiplier(goal: Goal, posture: str) -> float:
    if posture == "velocity" and "feature" in goal.tags:
        return 1.25
    if posture == "stability" and any(tag in {"integrity", "stability"} for tag in goal.tags):
        return 1.25
    return 1.0


__all__ = ["AllocationDecision", "DeferredGoal", "allocate_goals"]
