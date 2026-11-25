"""Canonical conditions and legal execution schedules for model replacement."""

CONDITION_ORDER = (
    "model_a_history_present", "model_a_history_withheld",
    "model_b_history_present", "model_b_history_withheld",
    "model_a_history_restored",
)

COUNTERBALANCED_CONDITION_ORDERS = (
    CONDITION_ORDER,
    (CONDITION_ORDER[0], CONDITION_ORDER[1], CONDITION_ORDER[3],
        CONDITION_ORDER[2], CONDITION_ORDER[4]),
    (CONDITION_ORDER[1], CONDITION_ORDER[0], CONDITION_ORDER[2],
        CONDITION_ORDER[3], CONDITION_ORDER[4]),
    (CONDITION_ORDER[1], CONDITION_ORDER[0], CONDITION_ORDER[3],
        CONDITION_ORDER[2], CONDITION_ORDER[4]),
)
