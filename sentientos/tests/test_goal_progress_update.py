from __future__ import annotations

import json
from pathlib import Path

from sentientos.artifact_catalog import append_catalog_entry
from sentientos.goal_executor import ExecutorState, GoalPlanner, update_goal_state_from_run
from sentientos.goal_completion import CompletionContext, eval_check
from sentientos.goal_graph import Goal, GoalGraph
from sentientos.risk_budget import RiskBudget
from sentientos.work_allocator import AllocationDecision
from sentientos.work_plan import (TaskRun, WorkPlanRun, persist_work_plan,
    persist_work_plan_evidence, persist_work_run, work_run_id)


def _mk_run(status: str, reason: str | None = None) -> WorkPlanRun:
    return WorkPlanRun(
        schema_version=1,
        run_id="r1",
        plan_id="p1",
        created_at="2026-01-01T00:00:00Z",
        status=status,
        operating_mode="normal",
        quarantine_active=False,
        task_runs=(TaskRun("t1", "g1", "verify", status, reason, "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z", 1, (), False),),
        reason_stack=(),
    )


def test_progress_and_completion(tmp_path: Path) -> None:
    (tmp_path / "glow/forge/work_runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/work_runs/run.json").write_text('{"status":"ok"}\n', encoding="utf-8")
    append_catalog_entry(tmp_path, kind="work_run", artifact_id="r1", relative_path="glow/forge/work_runs/run.json", schema_name="work_run", schema_version=1, links={"goal_id": "g1"}, summary={"status": "ok"})
    graph = GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 1, (), "check_forge_last_run_ok", 1, 1, ("integrity",), True),))
    out = update_goal_state_from_run(graph, {}, _mk_run("success"), repo_root=tmp_path, operating_mode="normal", pressure_level=0, posture="balanced", quarantine_active=False, risk_budget_summary={})
    # A successful task run cannot complete a goal without a matching
    # persisted run and canonical plan evidence digest.
    assert out["g1"].status == "active"
    assert out["g1"].progress < 1.0
    assert "run_evidence_binding_missing" in (out["g1"].blocked_reason or "")


def test_repeated_failure_blocks(tmp_path: Path) -> None:
    graph = GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 1, (), "check_federation_ok", 1, 1, ("federation",), True),))
    first = update_goal_state_from_run(graph, {}, _mk_run("failed", "x"), repo_root=tmp_path, operating_mode="normal", pressure_level=0, posture="balanced", quarantine_active=False, risk_budget_summary={})
    second = update_goal_state_from_run(graph, first, _mk_run("failed", "x"), repo_root=tmp_path, operating_mode="normal", pressure_level=0, posture="balanced", quarantine_active=False, risk_budget_summary={})
    assert second["g1"].status == "blocked"


def test_persisted_evidence_bound_run_completes_goal(tmp_path: Path) -> None:
    from sentientos.artifact_catalog import append_catalog_entry

    graph = GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 1, (),
        "check_forge_last_run_ok", 1, 1, ("integrity",), True),))
    allocation = AllocationDecision(selected=("g1",), deferred=(),
        selected_reasons=(), budget_summary={})
    state = ExecutorState(repo_root=tmp_path, created_at="2026-10-16T00:00:00Z",
        context="manual", operating_mode="normal", quarantine_active=False,
        allow_mutation=False, goal_graph_hash="b" * 64, allocation_id="allocation_1",
        risk_budget=RiskBudget(router_k_max=8, router_m_max=8,
            forge_max_files_changed=0))
    draft = GoalPlanner(repo_root=tmp_path).build_plan_with_evidence(
        allocation, state, graph)
    plan = draft.work_plan
    plan_path = persist_work_plan(tmp_path, plan)
    _, evidence_digest = persist_work_plan_evidence(
        tmp_path, plan, dict(draft.evidence_binding))
    run_id = work_run_id(plan, created_at=plan.created_at)
    task_runs = tuple(TaskRun(task.task_id, task.goal_id, task.kind, "success",
        None, "2026-10-16T00:00:00Z", "2026-10-16T00:00:01Z", 1, (),
        task.destructive) for task in plan.tasks)
    plan_digest = plan.identity_digest()
    run = WorkPlanRun(
        schema_version=3, run_id=run_id, plan_id=plan.plan_id,
        created_at=plan.created_at, status="ok",
        operating_mode="normal", quarantine_active=False,
        task_runs=task_runs,
        reason_stack=(), plan_digest=plan_digest,
        evidence_digest=evidence_digest,
    )
    run_path = persist_work_run(tmp_path, run)
    append_catalog_entry(tmp_path, kind="work_plan", artifact_id=plan.plan_id,
        relative_path=plan_path, schema_name="work_plan", schema_version=1,
        links={"work_plan_id": plan.plan_id}, summary={"status": "persisted"})
    append_catalog_entry(tmp_path, kind="work_run", artifact_id=run_id,
        relative_path=run_path, schema_name="", schema_version=3,
        links={"work_run_id": run_id, "goal_ids": ["g1"]},
        summary={"status": "ok"})

    out = update_goal_state_from_run(graph, {}, run, repo_root=tmp_path,
        operating_mode="normal", pressure_level=0, posture="balanced",
        quarantine_active=False, risk_budget_summary={})

    assert out["g1"].status == "completed"
    completion_path = next((tmp_path / "glow/forge/completion_checks").glob("*.json"))
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    assert completion["schema_version"] == 2
    assert completion["evidence_digest"] == evidence_digest
    reopened = eval_check("check_forge_last_run_ok", CompletionContext(
        tmp_path, "g1", "normal", 0, "balanced", False, {}))
    assert reopened.done is True
    assert reopened.evidence_digest == evidence_digest
