from __future__ import annotations

from pathlib import Path

from sentientos.goal_graph import Goal, GoalGraph, detect_dependency_cycles, goal_graph_hash, order_goals_deterministic, persist_goal_graph, load_goal_graph


def test_dependency_cycle_detection() -> None:
    graph = GoalGraph(
        schema_version=1,
        goals=(
            Goal("a", "A", 1.0, 1, ("b",), "rule:a", 1, 1, ("integrity",), True),
            Goal("b", "B", 1.0, 1, ("a",), "rule:b", 1, 1, ("integrity",), True),
        ),
    )
    cycles = detect_dependency_cycles(graph)
    assert cycles
    assert cycles[0] == ["a", "b"]


def test_deterministic_hash_stable_for_permuted_input(tmp_path: Path) -> None:
    goals_one = (
        Goal("goal_b", "B", 1.0, 1, (), "rule:b", 1, 1, ("feature",), True),
        Goal("goal_a", "A", 1.0, 1, (), "rule:a", 1, 1, ("integrity",), True),
    )
    goals_two = tuple(reversed(goals_one))
    hash_one = goal_graph_hash(GoalGraph(schema_version=1, goals=goals_one))
    hash_two = goal_graph_hash(GoalGraph(schema_version=1, goals=goals_two))
    assert hash_one == hash_two

    persist_goal_graph(tmp_path, GoalGraph(schema_version=1, goals=goals_two))
    loaded = load_goal_graph(tmp_path)
    assert [goal.goal_id for goal in loaded.goals] == [goal.goal_id for goal in order_goals_deterministic(list(goals_two))]
