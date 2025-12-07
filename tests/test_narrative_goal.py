from sentientos.consciousness.narrative_goal import (
    current_narrative_goal,
    narrative_goal_satisfied,
)


def test_placeholder_goal_satisfied():
    goal = current_narrative_goal()

    assert narrative_goal_satisfied(goal) is True


def test_mismatched_goal_not_satisfied():
    assert narrative_goal_satisfied("DIFFERENT_GOAL") is False
