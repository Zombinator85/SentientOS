from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sentientos.epistemic_planning import (epistemic_review_reason_for_goal,
    review_required_applicability)
from sentientos.goal_graph import Goal, GoalGraph, dependency_unmet, order_goals_deterministic
from sentientos.persistent_epistemic_state import EpistemicCognitiveProjection
from sentientos.risk_budget import RiskBudget


@dataclass(frozen=True, slots=True)
class DeferredGoal:
    goal_id: str
    reason: str
    epistemic_positions: tuple[dict[str, object], ...] = ()
    completion_evidence: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class AllocationDecision:
    selected: tuple[str, ...]
    deferred: tuple[DeferredGoal, ...]
    selected_reasons: tuple[dict[str, object], ...]
    budget_summary: dict[str, int]
    prior_epistemic_projection_digest: str | None = None
    prior_epistemic_projection_omitted_state_count: int | None = None


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
    prior_epistemic_projection: EpistemicCognitiveProjection | None = None,
    target_active_model_identity_digest: str | None = None,
    target_identity_observed_at: str | None = None,
    planning_time: str | None = None,
    verified_completion_evidence: Mapping[str, dict[str, object]] | None = None,
) -> AllocationDecision:
    selected: list[str] = []
    selected_reasons: list[dict[str, object]] = []
    deferred: list[DeferredGoal] = []
    spent_risk = 0
    spent_throughput = 0
    all_goal_ids = {goal.goal_id for goal in graph.goals}
    completed_evidence = dict(verified_completion_evidence or {})
    verified_completed_ids = set(completed_evidence)
    projection_digest: str | None = None
    projection_omitted_state_count: int | None = None
    review_scopes: dict[str, dict[str, object]] = {}
    if prior_epistemic_projection is not None:
        projection_digest, review_scopes = review_required_applicability(
            prior_epistemic_projection)
        # Older projections lack the omission manifest, so absence cannot prove zero.
        omission_manifest = getattr(prior_epistemic_projection,
            "omission_manifest", None)
        if isinstance(omission_manifest, Mapping):
            omitted_count = omission_manifest.get("omitted_state_count")
            if type(omitted_count) is int:
                projection_omitted_state_count = omitted_count

    for goal in order_goals_deterministic(graph.goals):
        positions = _epistemic_positions_for_goal(goal, review_scopes)
        completion_evidence = completed_evidence.get(goal.goal_id)
        if completion_evidence is not None:
            deferred.append(DeferredGoal(goal_id=goal.goal_id,
                reason="verified_completion", epistemic_positions=positions,
                completion_evidence=dict(completion_evidence)))
            continue
        if not goal.enabled:
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="disabled",
                epistemic_positions=positions))
            continue
        if dependency_unmet(goal, set(selected) | verified_completed_ids, all_goal_ids):
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="dependency_unmet",
                epistemic_positions=positions))
            continue
        if _is_mode_blocked(goal, operating_mode):
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="mode_blocked",
                epistemic_positions=positions))
            continue
        if quarantine_active and _is_quarantine_blocked(goal):
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="quarantine_blocked",
                epistemic_positions=positions))
            continue
        epistemic_reason = epistemic_review_reason_for_goal(goal.tags, review_scopes,
            target_active_model_identity_digest=target_active_model_identity_digest,
            target_identity_observed_at=target_identity_observed_at,
            planning_time=planning_time)
        if epistemic_reason is not None:
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason=epistemic_reason,
                epistemic_positions=positions))
            continue

        score = _goal_score(goal, posture=posture, pressure_level=integrity_pressure_level)
        if spent_risk + goal.risk_cost_estimate > budget.router_k_max:
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="budget_exceeded",
                epistemic_positions=positions))
            continue
        if spent_throughput + goal.throughput_cost_estimate > max(0, budget.router_m_max):
            deferred.append(DeferredGoal(goal_id=goal.goal_id, reason="throughput_exceeded",
                epistemic_positions=positions))
            continue
        selected.append(goal.goal_id)
        spent_risk += goal.risk_cost_estimate
        spent_throughput += goal.throughput_cost_estimate
        reason = {
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
        if projection_digest is not None:
            reason["epistemic_projection_digest"] = projection_digest
            reason["epistemic_positions"] = list(positions)
        verified_dependencies = [
            {"goal_id": dependency, **completed_evidence[dependency]}
            for dependency in goal.dependencies if dependency in completed_evidence
        ]
        if verified_dependencies:
            reason["verified_completed_dependencies"] = verified_dependencies
        selected_reasons.append(reason)

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
        prior_epistemic_projection_digest=projection_digest,
        prior_epistemic_projection_omitted_state_count=(
            projection_omitted_state_count),
    )


def _goal_score(goal: Goal, *, posture: str, pressure_level: int) -> float:
    return float(goal.weight) * _posture_multiplier(goal, posture) * _pressure_multiplier(goal, pressure_level) + float(goal.priority)


def _epistemic_positions_for_goal(
        goal: Goal, review_scopes: dict[str, dict[str, object]]) -> tuple[dict[str, object], ...]:
    """Bind each tagged position to this allocation decision deterministically."""
    tags = set(goal.tags)
    positions: list[dict[str, object]] = []
    for proposition_id, scope in sorted(review_scopes.items()):
        if f"epistemic_proposition:{proposition_id}" not in tags:
            continue
        identity = scope.get("position_identity")
        omitted_identity = scope.get("omitted_state_identity")
        positions.append({
            "proposition_id": proposition_id,
            "posture": scope.get("position_posture", "review_required"),
            "identity": dict(identity) if isinstance(identity, Mapping) else None,
            "omitted_state_identity": (dict(omitted_identity)
                if isinstance(omitted_identity, Mapping) else None),
        })
    return tuple(positions)


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
