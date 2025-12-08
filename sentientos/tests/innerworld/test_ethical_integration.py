import copy

import pytest

from sentientos.innerworld import InnerWorldOrchestrator

pytestmark = pytest.mark.no_legacy_skip


def test_ethics_present_in_real_cycle():
    orchestrator = InnerWorldOrchestrator()

    report = orchestrator.run_cycle({"plan": {"complexity": 1}})

    assert "ethics" in report
    assert isinstance(report["ethics"], dict)


def test_ethics_evaluation_is_deterministic():
    orchestrator = InnerWorldOrchestrator()
    plan = {"action": "observe", "complexity": 2}
    context = {"plan": plan, "progress": 0.25}

    first = orchestrator.evaluate_ethics(plan, context)
    second = orchestrator.evaluate_ethics(plan, context)

    assert first == second


def test_ethics_does_not_mutate_plan_or_state(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    orchestrator = InnerWorldOrchestrator()
    plan = {"complexity": 3, "requires_hiding": False}
    plan_snapshot = copy.deepcopy(plan)
    baseline_state = orchestrator.get_state()
    baseline_cycle = getattr(orchestrator, "_cycle_counter", None)

    _ = orchestrator.evaluate_ethics(plan, {"note": "check"})

    assert plan == plan_snapshot
    assert orchestrator.get_state() == baseline_state
    assert getattr(orchestrator, "_cycle_counter", None) == baseline_cycle


def test_simulation_includes_ethics(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    orchestrator = InnerWorldOrchestrator()
    baseline_state = orchestrator.get_state()

    simulation = orchestrator.run_simulation({"plan": {"complexity": 2}, "progress": 0.2})

    assert "ethics" in simulation["report"]
    assert isinstance(simulation["report"]["ethics"], dict)
    assert orchestrator.get_state() == baseline_state
