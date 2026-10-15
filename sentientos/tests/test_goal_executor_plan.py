from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sentientos.goal_executor import ExecutorState, GoalExecutor
from sentientos.goal_graph import Goal, GoalGraph
from sentientos.risk_budget import RiskBudget
from sentientos.work_allocator import AllocationDecision
from sentientos.work_plan import (TaskRun, WorkPlanRun, load_work_plan,
    persist_work_plan, persist_work_run, work_run_id)


def test_build_plan_is_deterministic_and_budgeted(tmp_path: Path) -> None:
    graph = GoalGraph(
        schema_version=1,
        goals=(
            Goal("g1", "desc", 1.0, 1, (), "task:forge_propose", 2, 1, ("integrity",), True),
        ),
    )
    allocation = AllocationDecision(selected=("g1",), deferred=(), selected_reasons=(), budget_summary={})
    state = ExecutorState(
        repo_root=tmp_path,
        created_at="2026-01-01T00:00:00Z",
        context="manual",
        operating_mode="normal",
        quarantine_active=False,
        allow_mutation=True,
        goal_graph_hash="abcd" * 16,
        allocation_id="allocation_1",
        risk_budget=RiskBudget(router_k_max=3, router_m_max=3, forge_max_files_changed=10),
    )
    executor = GoalExecutor(repo_root=tmp_path)

    plan_one = executor.build_plan(allocation, state, graph)
    plan_two = executor.build_plan(allocation, state, graph)

    assert plan_one.plan_id == plan_two.plan_id
    assert [task.kind for task in plan_one.tasks]
    assert sum(task.risk_cost for task in plan_one.tasks) <= state.risk_budget.router_k_max


def test_build_plan_records_risk_budget_omissions(tmp_path: Path) -> None:
    graph = GoalGraph(
        schema_version=1,
        goals=(
            Goal("g1", "desc", 1.0, 1, (), "always", 2, 2, ("integrity",), True),
        ),
    )
    allocation = AllocationDecision(selected=("g1",), deferred=(), selected_reasons=(), budget_summary={})
    state = ExecutorState(
        repo_root=tmp_path,
        created_at="2026-01-01T00:00:00Z",
        context="manual",
        operating_mode="normal",
        quarantine_active=False,
        allow_mutation=True,
        goal_graph_hash="abcd" * 16,
        allocation_id="allocation_1",
        risk_budget=RiskBudget(router_k_max=1, router_m_max=1, forge_max_files_changed=10),
    )

    plan = GoalExecutor(repo_root=tmp_path).build_plan(allocation, state, graph)
    assert len(plan.tasks) <= 1
    assert [(item.goal_id, item.kind, item.reason) for item in plan.omissions
        if item.reason == "risk_budget_exceeded"] == [
        ("g1", "verify", "risk_budget_exceeded"),
        ("g1", "forge_propose", "risk_budget_exceeded"),
    ]
    assert ("g1", "doc_update", "task_kind_not_implemented") in {
        (item.goal_id, item.kind, item.reason) for item in plan.omissions}
    assert load_work_plan(tmp_path / persist_work_plan(tmp_path, plan)) == plan


def test_build_plan_records_throughput_budget_omissions(tmp_path: Path) -> None:
    graph = GoalGraph(schema_version=1, goals=(
        Goal("g1", "desc", 1.0, 1, (), "always", 2, 2, ("integrity",), True),))
    allocation = AllocationDecision(selected=("g1",), deferred=(), selected_reasons=(),
        budget_summary={})
    state = ExecutorState(repo_root=tmp_path, created_at="2026-01-01T00:00:00Z",
        context="manual", operating_mode="cautious", quarantine_active=False,
        allow_mutation=False, goal_graph_hash="abcd" * 16, allocation_id="allocation_1",
        risk_budget=RiskBudget(router_k_max=8, router_m_max=1, forge_max_files_changed=0))

    plan = GoalExecutor(repo_root=tmp_path).build_plan(allocation, state, graph)

    assert [task.kind for task in plan.tasks] == ["diagnostic", "forge_propose"]
    assert [(item.goal_id, item.kind, item.reason) for item in plan.omissions
        if item.reason == "throughput_budget_exceeded"] == [
        ("g1", "verify", "throughput_budget_exceeded"),
    ]
    assert load_work_plan(tmp_path / persist_work_plan(tmp_path, plan)) == plan


def test_plan_records_unimplemented_task_kinds_without_executable_rows(tmp_path: Path) -> None:
    graph = GoalGraph(schema_version=1, goals=(
        Goal("external-goal", "external work", 1.0, 1, (), "always", 2, 1,
            ("external",), True),))
    allocation = AllocationDecision(selected=("external-goal",), deferred=(),
        selected_reasons=(), budget_summary={})
    state = ExecutorState(repo_root=tmp_path, created_at="2026-01-01T00:00:00Z",
        context="manual", operating_mode="cautious", quarantine_active=False,
        allow_mutation=False, goal_graph_hash="abcd" * 16, allocation_id="allocation_1",
        risk_budget=RiskBudget(router_k_max=8, router_m_max=8,
            forge_max_files_changed=0))

    plan = GoalExecutor(repo_root=tmp_path).build_plan(allocation, state, graph)

    assert {task.kind for task in plan.tasks}.isdisjoint({"fetch", "doc_update"})
    assert [(item.goal_id, item.kind, item.reason) for item in plan.omissions] == [
        ("external-goal", "fetch", "task_kind_not_implemented"),
        ("external-goal", "doc_update", "task_kind_not_implemented"),
    ]


def test_forge_apply_plan_declares_validation_and_proposal_dependencies(
    tmp_path: Path,
) -> None:
    graph = GoalGraph(schema_version=1, goals=(
        Goal("forge-goal", "apply only after checks", 1.0, 1, (),
            "check_forge_last_run_ok", 2, 1, ("integrity",), True),))
    allocation = AllocationDecision(selected=("forge-goal",), deferred=(),
        selected_reasons=(), budget_summary={})
    state = ExecutorState(repo_root=tmp_path, created_at="2026-01-01T00:00:00Z",
        context="manual", operating_mode="normal", quarantine_active=False,
        allow_mutation=True, goal_graph_hash="abcd" * 16, allocation_id="allocation_1",
        risk_budget=RiskBudget(router_k_max=8, router_m_max=8,
            forge_max_files_changed=10))

    plan = GoalExecutor(repo_root=tmp_path).build_plan(allocation, state, graph)
    apply = next(task for task in plan.tasks if task.kind == "forge_apply")

    assert apply.depends_on == ("forge-goal:verify", "forge-goal:forge_propose")


@pytest.mark.parametrize(("terminal_status", "terminal_reason"), [
    ("partial", "forge_apply_partial_success"),
    ("skipped", "prior_attempt_outcome_unknown"),
])
def test_prior_partial_or_unknown_outcome_informs_later_plan(
        tmp_path: Path, terminal_status: str, terminal_reason: str) -> None:
    graph = GoalGraph(schema_version=1, goals=(
        Goal("g1", "prior partial", 1.0, 1, (), "check_forge_last_run_ok", 2, 1,
            ("integrity",), True),
        Goal("g2", "independent", 0.5, 1, (), "check_forge_last_run_ok", 2, 1,
            ("integrity",), True)))
    allocation = AllocationDecision(selected=("g1", "g2"), deferred=(),
        selected_reasons=(), budget_summary={})
    base_state = ExecutorState(repo_root=tmp_path, created_at="2026-01-01T00:00:00Z",
        context="manual", operating_mode="normal", quarantine_active=False,
        allow_mutation=True, goal_graph_hash="abcd" * 16, allocation_id="prior",
        risk_budget=RiskBudget(router_k_max=20, router_m_max=20,
            forge_max_files_changed=10))
    executor = GoalExecutor(repo_root=tmp_path)
    prior_plan = executor.build_plan(allocation, base_state, graph)
    persist_work_plan(tmp_path, prior_plan)
    prior_tasks = tuple(TaskRun(task.task_id, task.goal_id, task.kind,
        terminal_status if task.kind == "forge_apply" and task.goal_id == "g1" else "success",
        terminal_reason if task.kind == "forge_apply" and task.goal_id == "g1"
            else None,
        "2026-01-01T00:00:01Z", "2026-01-01T00:00:02Z", 1,
        ("glow/forge/report.json",) if task.kind == "forge_apply" and task.goal_id == "g1"
            else (), task.destructive)
        for task in prior_plan.tasks)
    prior_run_id = work_run_id(prior_plan, created_at=prior_plan.created_at)
    prior_run = WorkPlanRun(2, prior_run_id, prior_plan.plan_id, prior_plan.created_at,
        "partial", "normal", False, prior_tasks, (terminal_reason,),
        prior_plan.identity_digest())
    persist_work_run(tmp_path, prior_run)

    next_state = ExecutorState(repo_root=tmp_path, created_at="2026-01-02T00:00:00Z",
        context="followup", operating_mode="normal", quarantine_active=False,
        allow_mutation=True, goal_graph_hash="abcd" * 16, allocation_id="next",
        risk_budget=base_state.risk_budget, prior_plan=prior_plan)
    next_plan = executor.build_plan(allocation, next_state, graph)

    expected_run_digest = hashlib.sha256(json.dumps(prior_run.to_dict(),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .encode("utf-8")).hexdigest()
    assert next_plan.context.endswith(f"prior_work_run_digest={expected_run_digest}")
    assert not any(task.goal_id == "g1" and task.kind == "forge_apply"
        for task in next_plan.tasks)
    assert any(task.goal_id == "g2" and task.kind == "forge_apply"
        for task in next_plan.tasks)
    assert ("g1", "forge_apply", "prior_terminal_outcome_requires_review") in {
        (row.goal_id, row.kind, row.reason) for row in next_plan.omissions}


def test_prior_plan_without_recovered_run_blocks_outcome_informed_planning(
        tmp_path: Path) -> None:
    graph = GoalGraph(schema_version=1, goals=(
        Goal("g1", "prior", 1.0, 1, (), "check_forge_last_run_ok", 2, 1,
            ("integrity",), True),))
    allocation = AllocationDecision(selected=("g1",), deferred=(),
        selected_reasons=(), budget_summary={})
    state = ExecutorState(repo_root=tmp_path, created_at="2026-01-02T00:00:00Z",
        context="followup", operating_mode="normal", quarantine_active=False,
        allow_mutation=True, goal_graph_hash="abcd" * 16, allocation_id="next",
        risk_budget=RiskBudget(router_k_max=20, router_m_max=20,
            forge_max_files_changed=10),
        prior_plan=GoalExecutor(repo_root=tmp_path).build_plan(allocation,
            ExecutorState(repo_root=tmp_path, created_at="2026-01-01T00:00:00Z",
                context="prior", operating_mode="normal", quarantine_active=False,
                allow_mutation=True, goal_graph_hash="abcd" * 16, allocation_id="prior",
                risk_budget=RiskBudget(router_k_max=20, router_m_max=20,
                    forge_max_files_changed=10)), graph))

    from sentientos.work_plan import WorkPlanError
    with pytest.raises(WorkPlanError, match="prior_work_run_unavailable"):
        GoalExecutor(repo_root=tmp_path).build_plan(allocation, state, graph)
