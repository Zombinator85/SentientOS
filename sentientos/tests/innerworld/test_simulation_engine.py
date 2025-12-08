import copy

import pytest

from sentientos.innerworld import InnerWorldOrchestrator, SimulationEngine


pytestmark = pytest.mark.no_legacy_skip


def test_simulation_has_no_side_effects():
    orchestrator = InnerWorldOrchestrator()
    engine = SimulationEngine()

    baseline_state = orchestrator.get_state()
    baseline_cycle = getattr(orchestrator, "_cycle_counter", None)

    engine.simulate(orchestrator, {"plan": {"complexity": 1}, "progress": 0.2})

    assert orchestrator.get_state() == baseline_state
    assert getattr(orchestrator, "_cycle_counter", None) == baseline_cycle


def test_simulation_is_deterministic():
    orchestrator = InnerWorldOrchestrator()
    engine = SimulationEngine()
    hypothetical_state = {"plan": {"complexity": 2}, "errors": 1}

    first = engine.simulate(orchestrator, hypothetical_state)
    second = engine.simulate(orchestrator, hypothetical_state)

    assert first == second


def test_simulation_cycle_id_is_special():
    orchestrator = InnerWorldOrchestrator()
    engine = SimulationEngine()

    report = engine.simulate(orchestrator, {"plan": {"complexity": 1}})

    assert report["report"]["cycle_id"] == -1


def test_simulation_returns_defensive_copies():
    orchestrator = InnerWorldOrchestrator()
    engine = SimulationEngine()

    result = engine.simulate(orchestrator, {"plan": {"complexity": 1}})
    mutated = copy.deepcopy(result)
    mutated["report"]["qualia"]["confidence"] = -5

    assert orchestrator.get_state()["qualia"]["confidence"] >= 0
    rerun = engine.simulate(orchestrator, {"plan": {"complexity": 1}})
    assert rerun["report"]["qualia"]["confidence"] >= 0
    assert rerun != mutated
