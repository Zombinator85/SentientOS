"""Stage-1 narrative-goal gating for the Consciousness Layer.

This module remains entirely passive and deterministic. Future orchestration
layers will provide real narrative goals and satisfaction criteria; for now, we
expose placeholder hooks that act as gate predicates only. No scheduling or
side effects are introduced here.
"""


def current_narrative_goal() -> str:
    """Return the current narrative goal placeholder."""

    return "PLACEHOLDER_GOAL"


def narrative_goal_satisfied(goal: str) -> bool:
    """Return whether the provided goal matches the placeholder goal."""

    return goal == "PLACEHOLDER_GOAL"
