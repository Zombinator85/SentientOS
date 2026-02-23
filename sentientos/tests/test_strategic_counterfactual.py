from __future__ import annotations

from sentientos.goal_graph import Goal, GoalGraph
from sentientos.strategic_adaptation import Adjustment, _allocation_diff, _compute_allocation_for_snapshot, apply_adjustments_to_goal_graph


def _graph() -> GoalGraph:
    return GoalGraph(
        schema_version=1,
        goals=(
            Goal("g1", "integrity", 0.7, 10, (), "check_integrity_baseline_ok", 1, 0, ("integrity",), True),
            Goal("g2", "feature a", 0.5, 7, (), "check_forge_last_run_ok", 1, 1, ("feature",), True),
            Goal("g3", "feature b", 0.4, 6, (), "check_forge_last_run_ok", 1, 1, ("feature",), True),
            Goal("g4", "expensive", 0.9, 9, (), "check_forge_last_run_ok", 2, 1, ("feature",), True),
        ),
    )


def _snapshot() -> dict[str, object]:
    return {
        "posture": "balanced",
        "pressure_level": 0,
        "operating_mode": "normal",
        "quarantine_active": False,
        "risk_budget_summary": {
            "router_k_max": 2,
            "router_m_max": 2,
            "allow_escalation": True,
            "allow_automerge": True,
            "allow_publish": True,
            "forge_max_files_changed": 10,
            "forge_max_runs_per_hour": 1,
            "forge_max_runs_per_day": 2,
        },
    }


def test_counterfactual_diff_reports_add_remove_reorder() -> None:
    base = _graph()
    current = _compute_allocation_for_snapshot(graph=base, snapshot=_snapshot())

    adjusted_add_remove = apply_adjustments_to_goal_graph(
        base,
        [
            Adjustment("g2", "enabled", True, False, "test", ()),
            Adjustment("g4", "weight", 0.9, 1.0, "test", ()),
        ],
    )
    proposed_add_remove = _compute_allocation_for_snapshot(graph=adjusted_add_remove, snapshot=_snapshot())
    add_remove_diff = _allocation_diff(current, proposed_add_remove)
    assert add_remove_diff["added_selected"] == ["g3"]
    assert "g2" in add_remove_diff["removed_selected"]

    adjusted_reorder = apply_adjustments_to_goal_graph(
        base,
        [
            Adjustment("g1", "priority", 10, 6, "test", ()),
            Adjustment("g2", "priority", 7, 11, "test", ()),
        ],
    )
    proposed_reorder = _compute_allocation_for_snapshot(graph=adjusted_reorder, snapshot=_snapshot())
    reorder_diff = _allocation_diff(current, proposed_reorder)
    reordered = reorder_diff["reordered"]
    assert isinstance(reordered, list)
    assert any(isinstance(item, dict) and item.get("goal_id") == "g1" for item in reordered)


def test_apply_adjustments_refuses_missing_dependencies_deterministically() -> None:
    base = GoalGraph(
        schema_version=1,
        goals=(
            Goal("g1", "integrity", 0.7, 10, ("missing",), "check_integrity_baseline_ok", 1, 0, ("integrity",), True),
        ),
    )
    try:
        apply_adjustments_to_goal_graph(base, ())
    except ValueError as exc:
        assert "goal_dependencies_missing:g1:missing" in str(exc)
    else:
        raise AssertionError("expected dependency validation failure")
