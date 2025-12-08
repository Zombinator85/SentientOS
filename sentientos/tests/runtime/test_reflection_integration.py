from copy import deepcopy

import pytest

from sentientos.runtime.core_loop import CoreLoop
from sentientos.innerworld.orchestrator import InnerWorldOrchestrator

pytestmark = pytest.mark.no_legacy_skip


def test_runtime_output_contains_reflection():
    loop = CoreLoop()

    result = loop.run_cycle({"errors": 0})

    assert "innerworld_reflection" in result
    assert isinstance(result["innerworld_reflection"], dict)


def test_reflection_changes_only_with_history():
    loop = CoreLoop()

    baseline = loop.innerworld.get_reflection_summary()
    repeat = loop.innerworld.get_reflection_summary()
    assert baseline == repeat

    loop.run_cycle({"progress": 0.1})

    updated = loop.innerworld.get_reflection_summary()
    assert baseline != updated


def test_reflection_deterministic_across_runs():
    state = {"errors": 1, "plan": {}}
    loop_a = CoreLoop()
    loop_b = CoreLoop()

    first = loop_a.run_cycle(deepcopy(state))["innerworld_reflection"]
    second = loop_b.run_cycle(deepcopy(state))["innerworld_reflection"]

    assert first == second


def test_simulation_cycles_do_not_affect_reflection():
    orchestrator = InnerWorldOrchestrator()
    baseline = orchestrator.get_reflection_summary()

    orchestrator.run_simulation({"plan": {}, "context": {}})

    after_simulation = orchestrator.get_reflection_summary()
    assert baseline == after_simulation
