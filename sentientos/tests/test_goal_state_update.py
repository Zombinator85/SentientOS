from __future__ import annotations

from sentientos.goal_executor import update_goal_state_from_run
from sentientos.goal_graph import Goal, GoalGraph
from sentientos.work_plan import TaskRun, WorkPlanRun


def test_goal_state_transitions_deterministic() -> None:
    graph = GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 1, (), "task:forge_apply", 1, 1, ("integrity",), True),))
    run = WorkPlanRun(
        schema_version=1,
        run_id="r1",
        plan_id="p1",
        created_at="2026-01-01T00:00:00Z",
        status="ok",
        operating_mode="normal",
        quarantine_active=False,
        task_runs=(
            TaskRun("t1", "g1", "forge_apply", "success", None, "a", "b", 1, ("x",), True),
        ),
        reason_stack=(),
    )
    updated = update_goal_state_from_run(graph, {}, run, blocked_threshold=2)
    assert updated["g1"].status == "completed"
    assert updated["g1"].progress == 1.0


def test_goal_state_becomes_blocked_after_repeated_failures() -> None:
    graph = GoalGraph(schema_version=1, goals=(Goal("g1", "d", 1.0, 1, (), "task:forge_apply", 1, 1, ("integrity",), True),))
    run = WorkPlanRun(
        schema_version=1,
        run_id="r1",
        plan_id="p1",
        created_at="2026-01-01T00:00:00Z",
        status="failed",
        operating_mode="normal",
        quarantine_active=False,
        task_runs=(TaskRun("t1", "g1", "forge_apply", "failed", "same", "a", "b", 1, (), True),),
        reason_stack=("same",),
    )
    first = update_goal_state_from_run(graph, {}, run, blocked_threshold=2)
    second = update_goal_state_from_run(graph, first, run, blocked_threshold=2)
    assert second["g1"].status == "blocked"
