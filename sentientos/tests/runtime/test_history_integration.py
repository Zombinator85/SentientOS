import pytest

from sentientos.runtime.core_loop import CoreLoop


pytestmark = pytest.mark.no_legacy_skip


def test_history_summary_present_and_updates():
    loop = CoreLoop()

    first = loop.run_cycle({"errors": 0.1, "plan": {"complexity": 1}})
    summary_one = first["innerworld_history_summary"]

    second = loop.run_cycle({"errors": 0.1, "plan": {"complexity": 1}})
    summary_two = second["innerworld_history_summary"]

    assert summary_one["count"] == 1
    assert summary_two["count"] == 2
    assert isinstance(summary_one["qualia_trends"], dict)
    assert isinstance(summary_two["qualia_trends"], dict)


def test_history_summary_deterministic_and_excludes_simulations():
    loop = CoreLoop()

    loop.run_cycle({"errors": 0.2})
    loop.run_cycle({"errors": 0.2})
    before_simulation = loop.innerworld.get_history_summary()

    loop.innerworld.run_simulation({"plan": {}, "context": {}, "inputs": {}})
    after_simulation = loop.innerworld.get_history_summary()

    other_loop = CoreLoop()
    other_loop.run_cycle({"errors": 0.2})
    deterministic_summary = other_loop.run_cycle({"errors": 0.2})["innerworld_history_summary"]

    assert before_simulation == after_simulation
    assert deterministic_summary == before_simulation
