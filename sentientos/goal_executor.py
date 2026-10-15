from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_goals.registry import REGISTRY
from sentientos.goal_completion import CompletionContext, eval_check, persist_completion_result
from sentientos.goal_graph import Goal, GoalGraph, GoalStateRecord, default_goal_state_record
from sentientos.epistemic_planning import (EpistemicPlanningError,
    epistemic_review_reason_for_goal, review_required_applicability)
from sentientos.persistent_epistemic_state import EpistemicCognitiveProjection
from sentientos.risk_budget import RiskBudget
from sentientos.work_allocator import AllocationDecision
from sentientos.work_plan import (Task, TaskOmission, TaskRun, WorkPlan, WorkPlanError,
    WorkPlanRun, load_work_run, work_run_id)
from sentientos.work_plan_execution_journal import WorkPlanExecutionJournal


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


class GoalExecutor:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def build_plan(self, allocation: AllocationDecision, state: ExecutorState, graph: GoalGraph) -> WorkPlan:
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
                            or (task_run.reason or "").startswith(
                                "prior_terminal_") and task_run.reason.endswith(
                                    "_not_replayed"))):
                    prior_goal_outcomes.setdefault(task_run.goal_id, set()).add(task_run.status)
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
            "deferred_goals": [{"goal_id": item.goal_id, "reason": item.reason}
                for item in allocation.deferred],
            "selected_reasons": list(allocation.selected_reasons),
            "prior_run_digest": next((part.split("=", 1)[1] for part in context_parts
                if part.startswith("prior_work_run_digest=")), None),
            "no_replay_goal_outcomes": {goal_id: sorted(statuses)
                for goal_id, statuses in sorted(prior_goal_outcomes.items())},
        }
        plan_id = _plan_id(state.created_at, state.goal_graph_hash, state.allocation_id,
            evidence_binding=epistemic_binding)
        context = "|".join(context_parts)
        if len(context) > 512:
            raise WorkPlanError("planning_evidence_context_bound_exceeded")
        return WorkPlan(schema_version=1, plan_id=plan_id, created_at=state.created_at,
            context=context, selected_goals=tuple(allocation.selected), tasks=tuple(tasks),
            omissions=tuple(omissions))

    def execute_plan(self, plan: WorkPlan, state: ExecutorState) -> WorkPlanRun:
        task_runs: list[TaskRun] = []
        reasons: list[str] = []
        effective_task_status: dict[str, str] = {}
        journal = WorkPlanExecutionJournal(self.repo_root, plan)
        persisted_run = load_work_run(self.repo_root, plan, created_at=state.created_at)
        if persisted_run is not None:
            for task_run in persisted_run.task_runs:
                journal_state = journal.state(task_run.task_id)
                journal_result = journal.result(task_run.task_id)
                if (journal_state is not None and journal_state != task_run.status
                        or journal_result is not None and journal_result != task_run):
                    raise WorkPlanError("work_run_journal_identity_conflict")
            return persisted_run
        for task in plan.tasks:
            started = _iso_now()
            started_mono = time.monotonic()
            status = "success"
            reason: str | None = None
            artifacts: tuple[str, ...] = ()
            destructive = task.destructive or task.kind == "forge_apply"
            retry_interrupted = False

            prior_state = journal.state(task.task_id)
            if prior_state is not None:
                prior_result = journal.result(task.task_id)
                if prior_result is not None:
                    task_runs.append(prior_result)
                    effective_task_status[task.task_id] = prior_result.status
                    if prior_result.status in {"failed", "skipped", "partial"} and prior_result.reason:
                        reasons.append(prior_result.reason)
                    continue
                retry_interrupted = (prior_state == "interrupted"
                    and task.kind in {"diagnostic", "verify"} and not task.destructive)
                if not retry_interrupted:
                    status = "skipped"
                    reason = ("prior_attempt_outcome_unknown" if prior_state == "interrupted"
                        else f"prior_terminal_{prior_state}_not_replayed")
                    effective_task_status[task.task_id] = (
                        "unknown" if prior_state == "interrupted" else prior_state)
                    finished = _iso_now()
                    task_runs.append(TaskRun(task_id=task.task_id, goal_id=task.goal_id,
                        kind=task.kind, status=status, reason=reason, started_at=started,
                        finished_at=finished, duration_ms=0, artifacts=(), destructive=destructive))
                    reasons.append(reason)
                    continue

            blocked_dependencies = tuple(dependency for dependency in task.depends_on
                if effective_task_status.get(dependency) != "success")
            if blocked_dependencies:
                status = "skipped"
                reason = "dependency_not_satisfied:" + ",".join(blocked_dependencies)
                if not retry_interrupted:
                    journal.start(task.task_id)
                effective_task_status[task.task_id] = status
                finished = _iso_now()
                task_run = TaskRun(task_id=task.task_id, goal_id=task.goal_id,
                    kind=task.kind, status=status, reason=reason, started_at=started,
                    finished_at=finished, duration_ms=0, artifacts=(), destructive=destructive)
                journal.finish(task.task_id, status=status, reason=reason, result=task_run)
                task_runs.append(task_run)
                reasons.append(reason)
                continue

            if retry_interrupted:
                journal.retry_start(task.task_id)
            else:
                journal.start(task.task_id)

            if destructive and (state.quarantine_active or not state.allow_mutation):
                status = "skipped"
                reason = "mutation_disallowed"
            elif destructive and state.operating_mode in {"recovery", "lockdown", "cautious"}:
                status = "skipped"
                reason = f"mode_disallows_destructive:{state.operating_mode}"
            else:
                status, reason, artifacts = self._execute_task(task)
            finished = _iso_now()
            duration_ms = max(0, int((time.monotonic() - started_mono) * 1000))
            effective_task_status[task.task_id] = status
            task_run = TaskRun(task_id=task.task_id, goal_id=task.goal_id, kind=task.kind,
                status=status, reason=reason, started_at=started, finished_at=finished,
                duration_ms=duration_ms, artifacts=artifacts, destructive=destructive)
            journal.finish(task.task_id, status=status, reason=reason, result=task_run)
            task_runs.append(task_run)
            if status in {"failed", "skipped", "partial"} and reason:
                reasons.append(reason)

        run_id = work_run_id(plan, created_at=state.created_at)
        overall_status = _overall_status(task_runs)
        return WorkPlanRun(schema_version=2, run_id=run_id, plan_id=plan.plan_id,
            created_at=state.created_at, status=overall_status,
            operating_mode=state.operating_mode, quarantine_active=state.quarantine_active,
            task_runs=tuple(task_runs), reason_stack=tuple(reasons[:12]),
            plan_digest=plan.identity_digest())

    def _execute_task(self, task: Task) -> tuple[str, str | None, tuple[str, ...]]:
        if task.kind in {"diagnostic", "verify"}:
            expected_command, argv_tail = _SAFE_PLAN_COMMANDS[task.kind]
            if task.commands != (expected_command,):
                return "failed", "command_not_allowlisted", ()
            return _run_commands(argv_tail, repo_root=self.repo_root)
        if task.kind in {"fetch", "doc_update"}:
            if task.commands:
                return "failed", "command_not_allowlisted", ()
            return "skipped", "task_kind_not_implemented", ()
        if task.kind == "forge_propose":
            goal_name = _goal_to_forge_goal(task.goal_id)
            forge = CathedralForge(repo_root=self.repo_root)
            plan = forge.plan(goal_name)
            rel = str((self.repo_root / "glow/forge" / f"plan_{_safe_id(plan.generated_at)}.json").relative_to(self.repo_root))
            return "success", None, (rel,)
        if task.kind == "forge_apply":
            goal_name = _goal_to_forge_goal(task.goal_id)
            forge = CathedralForge(repo_root=self.repo_root)
            report = forge.run(goal_name, initiator="goal_executor")
            rel = str((self.repo_root / "glow/forge" / f"report_{_safe_id(report.generated_at)}.json").relative_to(self.repo_root))
            if report.outcome == "partial_success":
                return "partial", "forge_apply_partial_success", (rel,)
            status = "success" if report.outcome in {"success", "noop"} else "failed"
            return status, None if status == "success" else "forge_apply_failed", (rel,)
        return "skipped", f"unknown_task_kind:{task.kind}", ()


def update_goal_state_from_run(
    graph: GoalGraph,
    existing: dict[str, GoalStateRecord],
    run: WorkPlanRun,
    *,
    repo_root: Path,
    operating_mode: str,
    pressure_level: int,
    posture: str,
    quarantine_active: bool,
    risk_budget_summary: dict[str, object],
    blocked_threshold: int = 2,
) -> dict[str, GoalStateRecord]:
    by_goal: dict[str, list[TaskRun]] = {}
    for task_run in run.task_runs:
        by_goal.setdefault(task_run.goal_id, []).append(task_run)

    result: dict[str, GoalStateRecord] = dict(existing)
    for goal in graph.goals:
        prev = result.get(goal.goal_id, default_goal_state_record())
        runs = by_goal.get(goal.goal_id, [])
        if not runs:
            continue
        latest = runs[-1]
        evidence = tuple(sorted({artifact for row in runs for artifact in row.artifacts}))

        ctx = CompletionContext(
            repo_root=repo_root,
            goal_id=goal.goal_id,
            operating_mode=operating_mode,
            pressure_level=pressure_level,
            posture=posture,
            quarantine_active=quarantine_active,
            risk_budget_summary=risk_budget_summary,
        )
        milestone_results = [eval_check(name, ctx) for name in goal.milestone_checks]
        completion_result = eval_check(goal.completion_check_name, ctx)
        persist_completion_result(repo_root, completion_result, work_run_id=run.run_id)

        progress = _deterministic_progress(runs, milestone_results, completion_result)
        completed = completion_result.done

        status = "active"
        blocked_reason: str | None = None
        failure_count = prev.failure_count
        last_result = "success"
        reason_stack = completion_result.reason_stack
        combined_evidence = tuple(sorted(set(evidence + completion_result.evidence_paths)))

        if completed:
            status = "completed"
            progress = 1.0
            failure_count = 0
            last_result = "success"
        elif completion_result.status in {"blocked", "error"} or any(row.status == "failed" for row in runs):
            last_result = "failed"
            primary = reason_stack[0] if reason_stack else ((next((row.reason for row in runs if row.status == "failed" and row.reason), None)) or "verify_failed")
            marker = f"{primary}|{'|'.join(combined_evidence)}"
            if prev.last_result == "failed" and prev.blocked_reason == marker:
                failure_count = prev.failure_count + 1
            else:
                failure_count = 1
            blocked_reason = marker
            if failure_count >= max(1, blocked_threshold):
                status = "blocked"
        elif any(row.status in {"skipped", "partial"} for row in runs):
            partial = next((row for row in reversed(runs) if row.status == "partial"), None)
            last_result = "partial" if partial is not None else "skipped"
            blocked_reason = partial.reason if partial is not None else runs[-1].reason

        result[goal.goal_id] = GoalStateRecord(
            schema_version=1,
            progress=progress,
            status=status,
            last_attempt_at=latest.finished_at,
            last_result=last_result,
            last_evidence_paths=combined_evidence,
            blocked_reason=blocked_reason,
            failure_count=failure_count,
        )

    return result


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


_SAFE_PLAN_COMMANDS: dict[str, tuple[str, str]] = {
    "diagnostic": ("python -m scripts.contract_drift", ("-m", "scripts.contract_drift")),
    "verify": ("python -m scripts.run_tests -q", ("-m", "scripts.run_tests", "-q")),
}

PLAN_COMMAND_TIMEOUT_SECONDS = 300


def _run_commands(argv_tail: tuple[str, ...], *, repo_root: Path) -> tuple[str, str | None, tuple[str, ...]]:
    argv = [sys.executable, *argv_tail]
    try:
        proc = subprocess.run(argv, shell=False, cwd=repo_root,
            capture_output=True, text=True, check=False,
            timeout=PLAN_COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return "failed", "command_timeout", ()
    except OSError as exc:
        return "failed", f"command_launch_failed:{type(exc).__name__}", ()
    if proc.returncode != 0:
        return "failed", f"command_failed:{argv[1:]}", ()
    return "success", None, ()


def _deterministic_progress(task_runs: list[TaskRun], milestones: list[object], completion_result: object) -> float:
    milestone_done = 0
    if milestones:
        milestone_done = sum(1 for row in milestones if bool(getattr(row, "done", False)))
    milestone_score = (milestone_done / len(milestones)) * 0.5 if milestones else 0.0
    completion_score = float(getattr(completion_result, "progress", 0.0)) * 0.4
    execution_score = 0.1 * min(1.0, sum(1 for row in task_runs if row.status == "success") / max(1, len(task_runs)))
    return round(max(0.0, min(1.0, milestone_score + completion_score + execution_score)), 3)


def _goal_to_forge_goal(goal_id: str) -> str:
    if goal_id in REGISTRY:
        return goal_id
    return "forge_smoke_noop"


def _plan_id(created_at: str, goal_graph_hash: str, allocation_id: str,
        *, evidence_binding: dict[str, object] | None = None) -> str:
    short_hash = goal_graph_hash[:8]
    alloc_short = hashlib.sha256(allocation_id.encode("utf-8")).hexdigest()[:6]
    evidence_short = hashlib.sha256(json.dumps(evidence_binding or {}, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    return f"{_safe_id(created_at)}_{short_hash}_{alloc_short}_{evidence_short}"


def _safe_id(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _overall_status(task_runs: list[TaskRun]) -> str:
    if not task_runs:
        return "skipped"
    if all(row.status == "skipped" for row in task_runs):
        return "skipped"
    if any(row.status == "failed" for row in task_runs):
        return "failed"
    if any(row.status in {"skipped", "partial"} for row in task_runs):
        return "partial"
    return "ok"


__all__ = ["ExecutorState", "GoalExecutor", "update_goal_state_from_run"]
