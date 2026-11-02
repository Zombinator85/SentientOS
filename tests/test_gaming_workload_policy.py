from __future__ import annotations

import pytest

from sentientos.gaming_workload_policy import GamingWorkloadPolicy
from sentientos.governed_local_model_invocation import LocalModelInvocationBudget

pytestmark = pytest.mark.no_legacy_skip


def test_normal_mode_preserves_the_requested_budget() -> None:
    requested = LocalModelInvocationBudget(max_input_chars=7000, max_output_chars=3000,
        max_new_tokens=256, timeout_seconds=24, max_calls_per_correlation=1)

    assert GamingWorkloadPolicy.constrain_budget("normal", requested) is requested


def test_gaming_mode_caps_each_turn_without_expanding_tighter_limits() -> None:
    requested = LocalModelInvocationBudget(max_input_chars=8000, max_output_chars=4000,
        max_new_tokens=512, timeout_seconds=30, max_calls_per_correlation=1)

    actual = GamingWorkloadPolicy.constrain_budget("gaming", requested)

    assert actual == LocalModelInvocationBudget(max_input_chars=4000, max_output_chars=1200,
        max_new_tokens=96, timeout_seconds=12, max_calls_per_correlation=1)


def test_gaming_mode_does_not_expand_an_already_tighter_budget() -> None:
    requested = LocalModelInvocationBudget(max_input_chars=1000, max_output_chars=500,
        max_new_tokens=32, timeout_seconds=5, max_calls_per_correlation=1)

    assert GamingWorkloadPolicy.constrain_budget("gaming", requested) == requested


def test_unknown_workload_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported_workload_mode"):
        GamingWorkloadPolicy.validate_mode("other")


def test_effective_mode_and_budget_are_recorded_in_invocation_lineage() -> None:
    requested = LocalModelInvocationBudget(max_new_tokens=512)

    budget, lineage = GamingWorkloadPolicy.apply_to_chat_invocation(
        "gaming", requested, {"serving_session_id": "session-1"})

    assert budget.max_new_tokens == 96
    assert lineage == {"serving_session_id": "session-1", "workload_mode": "gaming",
        "workload_evidence": {}}
