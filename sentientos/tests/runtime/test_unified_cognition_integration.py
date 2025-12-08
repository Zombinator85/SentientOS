from copy import deepcopy

from sentientos.innerworld import InnerWorldOrchestrator


def _base_input():
    return {"plan": {"steps": 1}, "errors": 0.1, "progress": 0.8, "novelty": 0.2}


def test_integration_reports_new_subsystems():
    orchestrator = InnerWorldOrchestrator()
    report = orchestrator.run_cycle(_base_input())

    assert "workspace_spotlight" in report
    assert "inner_dialogue" in report
    assert "value_drift" in report
    assert "autobiography" in report

    assert isinstance(report["workspace_spotlight"], dict)
    assert isinstance(report["inner_dialogue"], list)
    assert isinstance(report["autobiography"], list)
    assert report["value_drift"]["signals"]["history_length"] >= 1


def test_simulation_cycle_skips_new_features():
    orchestrator = InnerWorldOrchestrator()
    sim_report = orchestrator.run_cycle(_base_input(), simulation=True)

    assert "workspace_spotlight" not in sim_report
    assert "inner_dialogue" not in sim_report
    assert "autobiography" not in sim_report
    assert "value_drift" not in sim_report


def test_deterministic_across_runs():
    orchestrator_one = InnerWorldOrchestrator()
    orchestrator_two = InnerWorldOrchestrator()

    first = orchestrator_one.run_cycle(_base_input())
    second = orchestrator_two.run_cycle(_base_input())

    for key in ("workspace_spotlight", "inner_dialogue", "value_drift"):
        assert first[key] == second[key]

    assert len(first["autobiography"]) == len(second["autobiography"])
    assert deepcopy(first["inner_dialogue"]) == first["inner_dialogue"]
