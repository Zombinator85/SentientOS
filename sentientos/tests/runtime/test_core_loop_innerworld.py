import pytest
from unittest.mock import MagicMock

from sentientos.runtime.core_loop import CoreLoop
from sentientos.runtime.interfaces import CycleOutput


pytestmark = pytest.mark.no_legacy_skip


def test_orchestrator_invoked_once_per_cycle():
    orchestrator = MagicMock()
    orchestrator.run_cycle.return_value = {
        "cycle_id": 1,
        "qualia": {},
        "identity": {},
        "metacog": [],
        "ethics": {},
        "timestamp": 1.0,
    }

    loop = CoreLoop(orchestrator)
    _ = loop.run_cycle({"signal": 1})

    orchestrator.run_cycle.assert_called_once()


def test_cycle_output_contains_innerworld_structure():
    loop = CoreLoop()

    result: CycleOutput = loop.run_cycle({"errors": 0})

    assert "innerworld" in result
    innerworld = result["innerworld"]
    assert "qualia" in innerworld
    assert "identity" in innerworld
    assert "metacog" in innerworld
    assert "ethics" in innerworld


def test_cycle_reports_are_deterministic():
    loop_a = CoreLoop()
    loop_b = CoreLoop()
    state = {"errors": 1, "plan": {"complexity": 2}}

    first = loop_a.run_cycle(state)["innerworld"]
    second = loop_b.run_cycle(state)["innerworld"]

    def normalize(report: dict) -> dict:
        sanitized = dict(report)
        sanitized.pop("cycle_id", None)
        sanitized.pop("timestamp", None)
        return sanitized

    assert normalize(first) == normalize(second)


def test_cycle_output_is_defensive_copy():
    loop = CoreLoop()
    result = loop.run_cycle({"progress": 0.5})

    initial_state = loop.innerworld.get_state()
    result["innerworld"]["qualia"]["confidence"] = -1
    result["cycle_state"]["progress"] = -99

    refreshed_state = loop.innerworld.get_state()
    assert refreshed_state["qualia"]["confidence"] == initial_state["qualia"]["confidence"]
    assert refreshed_state["identity_events"] == initial_state["identity_events"]
    assert result["cycle_state"]["progress"] == -99
