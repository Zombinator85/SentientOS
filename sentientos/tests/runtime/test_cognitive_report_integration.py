import copy

import pytest

from sentientos.runtime import CoreLoop

pytestmark = pytest.mark.no_legacy_skip


def test_cognitive_report_exposed_and_integrated():
    loop = CoreLoop()
    state = {"plan": {"action": "observe"}, "progress": 0.1, "errors": 0}

    output = loop.run_cycle(state)

    cognitive_report = output["cognitive_report"]
    assert cognitive_report
    assert cognitive_report["recent_cycle"]["ethics"] == output["innerworld"]["ethics"]
    assert cognitive_report["trend_analysis"] == output["innerworld_reflection"]["trend_summary"]
    assert cognitive_report["diagnostics"]["history_size"] == output["innerworld_history_summary"]["count"]


def test_cognitive_report_is_deterministic_across_runs():
    state = {"plan": {"action": "observe"}, "progress": 0.2, "errors": 1}

    first_loop = CoreLoop()
    second_loop = CoreLoop()

    first_report = copy.deepcopy(first_loop.run_cycle(state)["cognitive_report"])
    second_report = copy.deepcopy(second_loop.run_cycle(state)["cognitive_report"])

    assert first_report == second_report


def test_simulation_cycles_do_not_include_cognitive_report():
    loop = CoreLoop()
    simulation = loop.innerworld.run_simulation({"plan": {"action": "simulate"}})

    assert "cognitive_report" not in simulation["report"]
