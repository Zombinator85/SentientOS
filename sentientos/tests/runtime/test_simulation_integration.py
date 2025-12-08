import pytest

from sentientos.runtime.core_loop import CoreLoop


pytestmark = pytest.mark.no_legacy_skip


def test_simulation_result_included_in_cycle_output():
    loop = CoreLoop()

    result = loop.run_cycle({"errors": 0, "plan": {"complexity": 1}})

    assert "simulation" in result
    simulation = result["simulation"]
    assert simulation.get("simulated") is True
    assert simulation["report"]["cycle_id"] == -1
    assert simulation["report"].get("qualia") is not None


def test_simulation_does_not_mutate_runtime_state():
    loop = CoreLoop()
    before_cycle = loop.innerworld.get_state()

    output = loop.run_cycle({"errors": 0.2, "plan": {"complexity": 1}})
    after_cycle = loop.innerworld.get_state()
    cycle_counter = getattr(loop.innerworld, "_cycle_counter", 0)

    output["simulation"]["report"]["identity"]["summary"] = "mutated"
    output["simulation"]["report"]["qualia"]["confidence"] = -3

    assert loop.innerworld.get_state() == after_cycle
    assert getattr(loop.innerworld, "_cycle_counter", 0) == cycle_counter
    assert before_cycle != after_cycle


def test_runtime_simulation_is_deterministic():
    loop_a = CoreLoop()
    loop_b = CoreLoop()
    state = {"errors": 0.1, "plan": {"complexity": 3}}

    sim_a = loop_a.run_cycle(state)["simulation"]
    sim_b = loop_b.run_cycle(state)["simulation"]

    assert sim_a == sim_b
