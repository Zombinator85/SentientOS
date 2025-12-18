from copy import deepcopy

import pytest

from sentientos.memory.memory_pressure_governor import MemoryPressureGovernor


pytestmark = pytest.mark.no_legacy_skip


def test_memory_pressure_governor_scores_without_side_effects():
    governor = MemoryPressureGovernor(context_budget_bytes=1000, archive_capacity_per_cycle=10.0, ledger_growth_capacity=5.0)

    pruner_output = {"totals": {"bytes": 500}}
    archive_rate = 5.0
    ledger_velocity = 2.5

    original_pruner = deepcopy(pruner_output)
    advisory = governor.evaluate(pruner_output, archive_rate, ledger_velocity)

    expected_pressure = 0.5 * 0.5 + 0.25 * 0.5 + 0.25 * 0.5
    assert advisory["pressure"] == round(expected_pressure, 3)
    assert advisory["advisory"].slow_down is False
    assert pruner_output == original_pruner


def test_memory_pressure_governor_triggers_slowdown():
    governor = MemoryPressureGovernor(context_budget_bytes=1000, archive_capacity_per_cycle=5.0, ledger_growth_capacity=2.0)

    pruner_output = {"totals": {"bytes": 900}}
    archive_rate = 6.0
    ledger_velocity = 3.0

    advisory = governor.evaluate(pruner_output, archive_rate, ledger_velocity)

    assert advisory["advisory"].slow_down is True
    assert advisory["advisory"].archive_aggressiveness <= 1.0
