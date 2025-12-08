import pytest

from sentientos.innerworld.orchestrator import InnerWorldOrchestrator
from sentientos.runtime.core_loop import CoreLoop


pytestmark = pytest.mark.no_legacy_skip


def test_config_snapshot_surfaces_in_innerworld_report():
    orchestrator = InnerWorldOrchestrator()
    orchestrator.config["timestamp"] = "should_be_removed"

    report = orchestrator.run_cycle({"errors": 0})

    assert "config_snapshot" in report
    assert "timestamp" not in report["config_snapshot"]["config"]


def test_simulation_mode_skips_config_snapshot():
    orchestrator = InnerWorldOrchestrator()
    simulation_report = orchestrator.run_cycle({"errors": 0}, simulation=True)

    assert "config_snapshot" not in simulation_report


def test_core_loop_exposes_sanitized_snapshot():
    orchestrator = InnerWorldOrchestrator()
    orchestrator.config["counter_value"] = 99
    core_loop = CoreLoop(innerworld=orchestrator)

    result = core_loop.run_cycle({"errors": 0})

    assert "config_snapshot" in result
    assert "counter_value" not in result["config_snapshot"]["config"]


def test_digest_stability_with_sanitized_snapshot():
    orchestrator = InnerWorldOrchestrator()
    orchestrator.config["session_id"] = "volatile"

    first_snapshot = orchestrator.get_config_snapshot()
    orchestrator.config["session_id"] = "volatile-2"
    second_snapshot = orchestrator.get_config_snapshot()

    first_digest = orchestrator.federation_digest.compute_digest({}, first_snapshot["config"])
    second_digest = orchestrator.federation_digest.compute_digest({}, second_snapshot["config"])

    assert first_snapshot == second_snapshot
    assert first_digest["digest"] == second_digest["digest"]
