from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import time
from typing import Sequence

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_goals.registry import REGISTRY
from sentientos.goal_planner import ExecutorState, GoalPlanDraft, GoalPlanner
from sentientos.goal_completion import CompletionContext, eval_check, persist_completion_result
from sentientos.goal_graph import Goal, GoalGraph, GoalStateRecord, default_goal_state_record
from sentientos.work_plan import (Task, TaskRun, WorkPlan, WorkPlanError,
    WORK_PLAN_EVIDENCE_DIR, WorkPlanRun, load_work_plan_evidence, load_work_run,
    work_plan_id_from_evidence, work_run_id)
from sentientos.work_plan_execution_journal import WorkPlanExecutionJournal


def _persisted_work_plan_evidence_present(repo_root: Path, plan: WorkPlan) -> bool:
    """Detect persisted evidence envelopes without following filesystem links."""
    plan_key = hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest()
    evidence_dir = repo_root.resolve() / WORK_PLAN_EVIDENCE_DIR
    for name in (f"evidence_{plan_key}.json", f"binding_{plan_key}.json"):
        try:
            (evidence_dir / name).lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise WorkPlanError("work_plan_evidence_presence_unreadable") from exc
        return True
    return False


class GoalExecutor:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def execute_plan(
        self, plan: WorkPlan, state: ExecutorState, *,
        expected_evidence_digest: str | None = None,
    ) -> WorkPlanRun:
        if (expected_evidence_digest is None
                and _persisted_work_plan_evidence_present(self.repo_root, plan)):
            raise WorkPlanError("work_plan_evidence_digest_required")
        if expected_evidence_digest is not None:
            evidence = load_work_plan_evidence(self.repo_root, plan)
            if evidence.get("evidence_digest") != expected_evidence_digest:
                raise WorkPlanError("work_plan_evidence_digest_mismatch")
            evidence_binding = evidence.get("evidence_binding")
            if (not isinstance(evidence_binding, dict)
                    or evidence_binding.get("allocation_artifact_path") != state.allocation_id
                    or evidence_binding.get("allocation_artifact_digest")
                        != state.allocation_artifact_digest):
                raise WorkPlanError(
                    "work_plan_execution_allocation_binding_mismatch")
            if (evidence_binding.get("target_active_model_identity_digest")
                    != state.target_active_model_identity_digest
                    or evidence_binding.get("target_identity_observed_at")
                        != state.target_identity_observed_at):
                raise WorkPlanError(
                    "work_plan_execution_model_identity_binding_mismatch")
        # Reject a mismatched execution envelope before opening journals or
        # invoking any task. The run-id helper enforces the plan timestamp as
        # part of the durable identity; waiting until the end could otherwise
        # allow effects before discovering that mismatch.
        work_run_id(plan, created_at=state.created_at)
        task_runs: list[TaskRun] = []
        reasons: list[str] = []
        effective_task_status: dict[str, str] = {}
        journal = WorkPlanExecutionJournal(self.repo_root, plan)
        persisted_run = load_work_run(self.repo_root, plan, created_at=state.created_at)
        if persisted_run is not None:
            if persisted_run.evidence_digest != expected_evidence_digest:
                raise WorkPlanError("work_run_evidence_binding_mismatch")
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
        return WorkPlanRun(schema_version=3 if expected_evidence_digest is not None else 2,
            run_id=run_id, plan_id=plan.plan_id,
            created_at=state.created_at, status=overall_status,
            operating_mode=state.operating_mode, quarantine_active=state.quarantine_active,
            task_runs=tuple(task_runs), reason_stack=tuple(reasons[:12]),
            plan_digest=plan.identity_digest(), evidence_digest=expected_evidence_digest)

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
            work_run_id=run.run_id,
            work_run_evidence_digest=run.evidence_digest,
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


_SAFE_PLAN_COMMANDS: dict[str, tuple[str, tuple[str, ...]]] = {
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


def _deterministic_progress(task_runs: list[TaskRun], milestones: Sequence[object], completion_result: object) -> float:
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
    return work_plan_id_from_evidence(created_at, goal_graph_hash, allocation_id,
        evidence_binding or {})


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


__all__ = ["ExecutorState", "GoalExecutor", "GoalPlanDraft", "GoalPlanner",
    "update_goal_state_from_run"]
