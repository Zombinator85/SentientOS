from __future__ import annotations

from sentientos.goal_graph import Goal, GoalGraph
from sentientos.risk_budget import RiskBudget
from sentientos.work_allocator import allocate_goals


def _budget() -> RiskBudget:
    return RiskBudget(router_k_max=3, router_m_max=3)


def test_mode_gating_in_recovery_blocks_feature_goals() -> None:
    graph = GoalGraph(
        schema_version=1,
        goals=(
            Goal("integrity_fix", "fix", 1.0, 1, (), "rule", 1, 1, ("integrity",), True),
            Goal("new_feature", "feat", 5.0, 10, (), "rule", 1, 1, ("feature",), True),
        ),
    )
    decision = allocate_goals(graph=graph, budget=_budget(), operating_mode="recovery", integrity_pressure_level=0, quarantine_active=False, posture="balanced")
    assert "integrity_fix" in decision.selected
    assert any(item.goal_id == "new_feature" and item.reason == "mode_blocked" for item in decision.deferred)


def test_quarantine_blocks_non_remediation_integrity() -> None:
    graph = GoalGraph(
        schema_version=1,
        goals=(
            Goal("maint", "maint", 2.0, 2, (), "rule", 1, 1, ("maintenance",), True),
            Goal("remediate", "rem", 1.0, 1, (), "rule", 1, 1, ("remediation",), True),
        ),
    )
    decision = allocate_goals(graph=graph, budget=_budget(), operating_mode="normal", integrity_pressure_level=0, quarantine_active=True, posture="balanced")
    assert "remediate" in decision.selected
    assert any(item.goal_id == "maint" and item.reason == "quarantine_blocked" for item in decision.deferred)


def test_budget_enforcement_and_deterministic_tie_break() -> None:
    graph = GoalGraph(
        schema_version=1,
        goals=(
            Goal("b_goal", "b", 1.0, 1, (), "rule", 2, 1, ("integrity",), True),
            Goal("a_goal", "a", 1.0, 1, (), "rule", 2, 1, ("integrity",), True),
        ),
    )
    decision = allocate_goals(graph=graph, budget=RiskBudget(router_k_max=2, router_m_max=3), operating_mode="normal", integrity_pressure_level=0, quarantine_active=False, posture="balanced")
    assert decision.selected == ("a_goal",)
    assert any(item.goal_id == "b_goal" and item.reason == "budget_exceeded" for item in decision.deferred)


def test_posture_multiplier_promotes_feature_under_velocity() -> None:
    graph = GoalGraph(
        schema_version=1,
        goals=(
            Goal("feature_goal", "feat", 1.0, 1, (), "rule", 1, 1, ("feature",), True),
            Goal("integrity_goal", "int", 1.0, 1, (), "rule", 1, 1, ("integrity",), True),
        ),
    )
    decision = allocate_goals(graph=graph, budget=RiskBudget(router_k_max=1, router_m_max=3), operating_mode="normal", integrity_pressure_level=0, quarantine_active=False, posture="velocity")
    assert decision.selected == ("feature_goal",)
