from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping

from sentientos.epistemic_planning import (
    EpistemicPlanningError,
    epistemic_review_reason_for_goal,
    review_required_applicability,
)
from sentientos.goal_graph import Goal, GoalGraph
from sentientos.persistent_epistemic_state import EpistemicCognitiveProjection
from sentientos.risk_budget import RiskBudget
from sentientos.work_allocator import AllocationDecision
from sentientos.work_plan import (
    Task,
    TaskOmission,
    WorkPlan,
    WorkPlanError,
    load_work_run,
    work_plan_id_from_evidence,
)


@dataclass(frozen=True, slots=True)
class ExecutorState:
    repo_root: Path
    created_at: str
    context: str
    operating_mode: str
    quarantine_active: bool
    allow_mutation: bool
    goal_graph_hash: str
    allocation_id: str
    risk_budget: RiskBudget
    pressure_level: int = 0
    posture: str = "balanced"
    prior_plan: WorkPlan | None = None
    prior_epistemic_projection: EpistemicCognitiveProjection | None = None
    target_active_model_identity_digest: str | None = None
    target_identity_observed_at: str | None = None
    prior_run_outcome_unknown: bool = False


class GoalPlanner:
    """Deterministically construct work plans without executing their tasks."""

    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def build_plan(self, allocation: AllocationDecision, state: ExecutorState, graph: GoalGraph) -> WorkPlan:
        return self.build_plan_with_evidence(allocation, state, graph).work_plan

    def build_plan_with_evidence(
        self, allocation: AllocationDecision, state: ExecutorState, graph: GoalGraph,
    ) -> "GoalPlanDraft":
        goals_by_id = {goal.goal_id: goal for goal in graph.goals}
        tasks: list[Task] = []
        omissions: list[TaskOmission] = []
        spent_risk = 0
        spent_throughput = 0
        prior_run = None
        if state.prior_plan is not None:
            prior_run = load_work_run(self.repo_root, state.prior_plan,
                created_at=state.prior_plan.created_at)
            if prior_run is None:
                raise WorkPlanError("prior_work_run_unavailable")
        prior_goal_outcomes: dict[str, set[str]] = {}
        if prior_run is not None:
            for task_run in prior_run.task_runs:
                if task_run.status in {"partial", "failed"} or (
                        task_run.status == "skipped"
                        and (task_run.reason == "prior_attempt_outcome_unknown"
                            or ((task_run.reason or "").startswith(
                                "prior_terminal_") and (task_run.reason or "").endswith(
                                    "_not_replayed")))):
                    prior_goal_outcomes.setdefault(task_run.goal_id, set()).add(task_run.status)
        elif state.prior_run_outcome_unknown:
            for goal_id in allocation.selected:
                prior_goal_outcomes[goal_id] = {"unknown"}
        epistemic_review_goal_ids: set[str] = set()
        epistemic_projection_digest: str | None = None
        epistemic_review_scopes: dict[str, dict[str, object]] = {}
        if state.prior_epistemic_projection is not None:
            try:
                epistemic_projection_digest, epistemic_review_scopes = review_required_applicability(
                    state.prior_epistemic_projection)
            except EpistemicPlanningError as exc:
                raise WorkPlanError("prior_epistemic_projection_invalid") from exc
            epistemic_review_goal_ids.update(goal.goal_id for goal in graph.goals
                if epistemic_review_reason_for_goal(goal.tags,
                    epistemic_review_scopes,
                    target_active_model_identity_digest=
                        state.target_active_model_identity_digest,
                    target_identity_observed_at=state.target_identity_observed_at,
                    planning_time=state.created_at) is not None)
        for goal_id in allocation.selected:
            goal = goals_by_id.get(goal_id)
            if goal is None:
                continue
            omissions.extend(_goal_task_omissions(goal=goal, state=state))
            prior_outcome = prior_goal_outcomes.get(goal_id, set())
            epistemic_review = goal_id in epistemic_review_goal_ids
            if _forge_apply_would_be_allowed(goal, state):
                if prior_outcome:
                    omissions.append(TaskOmission(goal_id, "forge_apply",
                        "prior_terminal_outcome_requires_review"))
                elif epistemic_review:
                    omissions.append(TaskOmission(goal_id, "forge_apply",
                        "epistemic_position_requires_review"))
            for task in _map_goal_to_tasks(goal=goal, state=state,
                    prior_outcome=prior_outcome, epistemic_review=epistemic_review):
                if spent_risk + task.risk_cost > state.risk_budget.router_k_max:
                    omissions.append(TaskOmission(
                        goal_id=task.goal_id, kind=task.kind, reason="risk_budget_exceeded"))
                    continue
                if spent_throughput + task.throughput_cost > state.risk_budget.router_m_max:
                    omissions.append(TaskOmission(
                        goal_id=task.goal_id, kind=task.kind, reason="throughput_budget_exceeded"))
                    continue
                tasks.append(task)
                spent_risk += task.risk_cost
                spent_throughput += task.throughput_cost

        context = state.context
        context_parts = [context]
        if prior_run is not None:
            prior_run_digest = hashlib.sha256(json.dumps(prior_run.to_dict(),
                sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                .encode("utf-8")).hexdigest()
            context_parts.append(f"prior_work_run_digest={prior_run_digest}")
        if epistemic_projection_digest is not None:
            context_parts.append(f"epistemic_projection_digest={epistemic_projection_digest}")
        if state.target_active_model_identity_digest is not None:
            context_parts.append("target_model_identity_digest="
                + state.target_active_model_identity_digest)
            context_parts.append("target_identity_observed_at="
                + str(state.target_identity_observed_at))
        epistemic_binding = {
            "planning_time": state.created_at,
            "goal_graph_hash": state.goal_graph_hash,
            "allocation_artifact_path": state.allocation_id,
            "operating_mode": state.operating_mode,
            "pressure_level": state.pressure_level,
            "quarantine_active": state.quarantine_active,
            "posture": state.posture,
            "risk_budget": state.risk_budget.to_dict(),
            "projection_digest": epistemic_projection_digest,
            "review_scopes": epistemic_review_scopes,
            "target_active_model_identity_digest":
                state.target_active_model_identity_digest,
            "target_identity_observed_at": state.target_identity_observed_at,
            "goal_tags": {goal.goal_id: list(goal.tags) for goal in graph.goals},
            "goal_applicability": {goal.goal_id:
                epistemic_review_reason_for_goal(goal.tags, epistemic_review_scopes,
                    target_active_model_identity_digest=
                        state.target_active_model_identity_digest,
                    target_identity_observed_at=state.target_identity_observed_at,
                    planning_time=state.created_at)
                for goal in graph.goals if any(tag.startswith("epistemic_")
                    for tag in goal.tags)},
            "omissions": [item.to_dict() for item in omissions],
            "deferred_goals": [{"goal_id": item.goal_id, "reason": item.reason,
                "epistemic_positions": list(item.epistemic_positions),
                "completion_evidence": item.completion_evidence}
                for item in allocation.deferred],
            "selected_reasons": list(allocation.selected_reasons),
            "prior_run_digest": next((part.split("=", 1)[1] for part in context_parts
                if part.startswith("prior_work_run_digest=")), None),
            "prior_run_outcome_unknown": state.prior_run_outcome_unknown,
            "no_replay_goal_outcomes": {goal_id: sorted(statuses)
                for goal_id, statuses in sorted(prior_goal_outcomes.items())},
        }
        omission_manifest = (getattr(state.prior_epistemic_projection,
            "omission_manifest", None) if state.prior_epistemic_projection is not None else None)
        if omission_manifest is not None:
            epistemic_binding["projection_omission_manifest"] = dict(omission_manifest)
        plan_id = work_plan_id_from_evidence(state.created_at, state.goal_graph_hash,
            state.allocation_id, epistemic_binding)
        context = "|".join(context_parts)
        if len(context) > 512:
            raise WorkPlanError("planning_evidence_context_bound_exceeded")
        plan = WorkPlan(schema_version=1, plan_id=plan_id, created_at=state.created_at,
            context=context, selected_goals=tuple(allocation.selected), tasks=tuple(tasks),
            omissions=tuple(omissions))
        return GoalPlanDraft(work_plan=plan, evidence_binding=epistemic_binding)


@dataclass(frozen=True, slots=True)
class GoalPlanDraft:
    """A plan plus the exact canonical evidence binding used to derive it."""

    work_plan: WorkPlan
    evidence_binding: Mapping[str, object]


def _map_goal_to_tasks(*, goal: Goal, state: ExecutorState,
        prior_outcome: set[str] | None = None,
        epistemic_review: bool = False) -> tuple[Task, ...]:
    plan: list[Task] = []
    plan.append(_task(goal, "diagnostic", 1, 1, destructive=False, commands=("python -m scripts.contract_drift",), expected=("glow/contracts/contract_status.json",)))
    plan.append(_task(goal, "verify", 1, 1, destructive=False, commands=("python -m scripts.run_tests -q",), expected=()))
    plan.append(_task(goal, "forge_propose", 1, 0, destructive=False, commands=(), expected=("glow/forge",)))

    allow_apply = state.operating_mode == "normal" and state.allow_mutation and not state.quarantine_active and state.risk_budget.forge_max_files_changed > 0
    close_to_done = goal.completion_check_name in {"check_forge_last_run_ok", "check_mypy_forge_ok"}
    if allow_apply and close_to_done and not prior_outcome and not epistemic_review:
        plan.append(_task(goal, "forge_apply", max(1, goal.risk_cost_estimate),
            max(1, goal.throughput_cost_estimate), destructive=True, commands=(),
            expected=("glow/forge",),
            depends_on=(f"{goal.goal_id}:verify", f"{goal.goal_id}:forge_propose")))
    return tuple(plan)


def _forge_apply_would_be_allowed(goal: Goal, state: ExecutorState) -> bool:
    return (state.operating_mode == "normal" and state.allow_mutation
        and not state.quarantine_active and state.risk_budget.forge_max_files_changed > 0
        and goal.completion_check_name in {"check_forge_last_run_ok", "check_mypy_forge_ok"})


def _goal_task_omissions(*, goal: Goal, state: ExecutorState) -> tuple[TaskOmission, ...]:
    omissions: list[TaskOmission] = []
    if any(tag in {"external", "federation", "fetch"} for tag in goal.tags):
        omissions.append(TaskOmission(goal.goal_id, "fetch", "task_kind_not_implemented"))
    allow_apply = (state.operating_mode == "normal" and state.allow_mutation
        and not state.quarantine_active and state.risk_budget.forge_max_files_changed > 0)
    close_to_done = goal.completion_check_name in {
        "check_forge_last_run_ok", "check_mypy_forge_ok"}
    if not (allow_apply and close_to_done):
        omissions.append(TaskOmission(goal.goal_id, "doc_update", "task_kind_not_implemented"))
    return tuple(omissions)


def _task(goal: Goal, kind: str, risk_cost: int, throughput_cost: int, *, destructive: bool, commands: tuple[str, ...], expected: tuple[str, ...], depends_on: tuple[str, ...] = ()) -> Task:
    task_id = f"{goal.goal_id}:{kind}"
    return Task(schema_version=1, task_id=task_id, goal_id=goal.goal_id, kind=kind,
        commands=commands, callable_ref=None, risk_cost=max(0, risk_cost),
        throughput_cost=max(0, throughput_cost), preconditions={"requires_mutation": destructive},
        expected_artifacts=expected, destructive=destructive, depends_on=depends_on)


