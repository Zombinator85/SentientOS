from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import time

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_goals.registry import REGISTRY
from sentientos.goal_completion import CompletionContext, eval_check, persist_completion_result
from sentientos.goal_graph import Goal, GoalGraph, GoalStateRecord, default_goal_state_record
from sentientos.risk_budget import RiskBudget
from sentientos.work_allocator import AllocationDecision
from sentientos.work_plan import Task, TaskRun, WorkPlan, WorkPlanRun


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


class GoalExecutor:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def build_plan(self, allocation: AllocationDecision, state: ExecutorState, graph: GoalGraph) -> WorkPlan:
        goals_by_id = {goal.goal_id: goal for goal in graph.goals}
        tasks: list[Task] = []
        spent_risk = 0
        spent_throughput = 0
        for goal_id in allocation.selected:
            goal = goals_by_id.get(goal_id)
            if goal is None:
                continue
            for task in _map_goal_to_tasks(goal=goal, state=state):
                if spent_risk + task.risk_cost > state.risk_budget.router_k_max:
                    continue
                if spent_throughput + task.throughput_cost > state.risk_budget.router_m_max:
                    continue
                tasks.append(task)
                spent_risk += task.risk_cost
                spent_throughput += task.throughput_cost

        plan_id = _plan_id(state.created_at, state.goal_graph_hash, state.allocation_id)
        return WorkPlan(schema_version=1, plan_id=plan_id, created_at=state.created_at, context=state.context, selected_goals=tuple(allocation.selected), tasks=tuple(tasks))

    def execute_plan(self, plan: WorkPlan, state: ExecutorState) -> WorkPlanRun:
        task_runs: list[TaskRun] = []
        reasons: list[str] = []
        for task in plan.tasks:
            started = _iso_now()
            started_mono = time.monotonic()
            status = "success"
            reason: str | None = None
            artifacts: tuple[str, ...] = ()

            if task.destructive and (state.quarantine_active or not state.allow_mutation):
                status = "skipped"
                reason = "mutation_disallowed"
            elif task.destructive and state.operating_mode in {"recovery", "lockdown", "cautious"}:
                status = "skipped"
                reason = f"mode_disallows_destructive:{state.operating_mode}"
            else:
                status, reason, artifacts = self._execute_task(task)
            finished = _iso_now()
            duration_ms = max(0, int((time.monotonic() - started_mono) * 1000))
            task_runs.append(TaskRun(task_id=task.task_id, goal_id=task.goal_id, kind=task.kind, status=status, reason=reason, started_at=started, finished_at=finished, duration_ms=duration_ms, artifacts=artifacts, destructive=task.destructive))
            if status in {"failed", "skipped"} and reason:
                reasons.append(reason)

        run_id = f"run_{_safe_id(state.created_at)}_{plan.plan_id}"
        overall_status = _overall_status(task_runs)
        return WorkPlanRun(schema_version=1, run_id=run_id, plan_id=plan.plan_id, created_at=state.created_at, status=overall_status, operating_mode=state.operating_mode, quarantine_active=state.quarantine_active, task_runs=tuple(task_runs), reason_stack=tuple(reasons[:12]))

    def _execute_task(self, task: Task) -> tuple[str, str | None, tuple[str, ...]]:
        if task.kind in {"diagnostic", "verify", "fetch", "doc_update"}:
            if task.commands:
                return _run_commands(task.commands, repo_root=self.repo_root)
            return "success", None, task.expected_artifacts
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
            status = "success" if report.outcome in {"success", "noop", "partial_success"} else "failed"
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
        elif any(row.status == "skipped" for row in runs):
            last_result = "skipped"
            blocked_reason = runs[-1].reason

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


def _map_goal_to_tasks(*, goal: Goal, state: ExecutorState) -> tuple[Task, ...]:
    plan: list[Task] = []
    plan.append(_task(goal, "diagnostic", 1, 1, destructive=False, commands=("python -m scripts.contract_drift",), expected=("glow/contracts/contract_status.json",)))
    plan.append(_task(goal, "verify", 1, 1, destructive=False, commands=("python -m scripts.run_tests -q",), expected=()))
    if any(tag in {"external", "federation", "fetch"} for tag in goal.tags):
        plan.append(_task(goal, "fetch", 0, 1, destructive=False, commands=(), expected=()))

    plan.append(_task(goal, "forge_propose", 1, 0, destructive=False, commands=(), expected=("glow/forge",)))

    allow_apply = state.operating_mode == "normal" and state.allow_mutation and not state.quarantine_active and state.risk_budget.forge_max_files_changed > 0
    close_to_done = goal.completion_check_name in {"check_forge_last_run_ok", "check_mypy_forge_ok"}
    if allow_apply and close_to_done:
        plan.append(_task(goal, "forge_apply", max(1, goal.risk_cost_estimate), max(1, goal.throughput_cost_estimate), destructive=True, commands=(), expected=("glow/forge",)))
    else:
        plan.append(_task(goal, "doc_update", 0, 1, destructive=False, commands=(), expected=()))

    return tuple(plan)


def _task(goal: Goal, kind: str, risk_cost: int, throughput_cost: int, *, destructive: bool, commands: tuple[str, ...], expected: tuple[str, ...]) -> Task:
    task_id = f"{goal.goal_id}:{kind}"
    return Task(schema_version=1, task_id=task_id, goal_id=goal.goal_id, kind=kind, commands=commands, callable_ref=None, risk_cost=max(0, risk_cost), throughput_cost=max(0, throughput_cost), preconditions={"requires_mutation": destructive}, expected_artifacts=expected, destructive=destructive)


def _run_commands(commands: tuple[str, ...], *, repo_root: Path) -> tuple[str, str | None, tuple[str, ...]]:
    for command in commands:
        proc = subprocess.run(command, shell=True, cwd=repo_root, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return "failed", f"command_failed:{command}", ()
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


def _plan_id(created_at: str, goal_graph_hash: str, allocation_id: str) -> str:
    short_hash = goal_graph_hash[:8]
    alloc_short = hashlib.sha256(allocation_id.encode("utf-8")).hexdigest()[:6]
    return f"{_safe_id(created_at)}_{short_hash}_{alloc_short}"


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
    if any(row.status == "skipped" for row in task_runs):
        return "partial"
    return "ok"


__all__ = ["ExecutorState", "GoalExecutor", "update_goal_state_from_run"]
