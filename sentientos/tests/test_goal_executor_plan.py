from __future__ import annotations

from pathlib import Path

from sentientos.goal_executor import ExecutorState, GoalExecutor
from sentientos.goal_graph import Goal, GoalGraph
from sentientos.risk_budget import RiskBudget
from sentientos.work_allocator import AllocationDecision
from sentientos.work_plan import load_work_plan, persist_work_plan


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
