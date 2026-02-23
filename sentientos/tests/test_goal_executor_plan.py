from __future__ import annotations

from pathlib import Path

from sentientos.goal_executor import ExecutorState, GoalExecutor
from sentientos.goal_graph import Goal, GoalGraph
from sentientos.risk_budget import RiskBudget
from sentientos.work_allocator import AllocationDecision


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


def test_build_plan_drops_tasks_when_budget_exhausted(tmp_path: Path) -> None:
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
