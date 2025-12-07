from __future__ import annotations

from typing import Dict

import pytest

from sentientos.consciousness.integration import run_consciousness_cycle
from sentientos.daemons import pulse_bus


class StubArbitrator:
    def __init__(self) -> None:
        self.cycles: int = 0

    def run_cycle(self) -> None:
        self.cycles += 1

    def telemetry_snapshot(self) -> Dict[str, object]:
        return {"focus": "stub-focus", "cycles": self.cycles}


class StubKernel:
    def __init__(self) -> None:
        self.cycles: int = 0

    def run_cycle(self) -> Dict[str, object]:
        self.cycles += 1
        return {"generated": False, "cycles": self.cycles}


class StubSimulation:
    def __init__(self) -> None:
        self.cycles: int = 0
        self.last_summary = None
        self.last_transcript = ["safe"]
        self.private_log = "do-not-export"

    def run_cycle(self) -> None:
        self.cycles += 1
        self.last_summary = "stable"


@pytest.fixture(autouse=True)
def clear_pulse_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pulse_bus,
        "publish",
        lambda payload: (_ for _ in ()).throw(RuntimeError("publish should not be called")),
    )


def test_run_cycle_deterministic_with_stubs() -> None:
    def _build_context() -> Dict[str, object]:
        return {
            "arbitrator": StubArbitrator(),
            "kernel": StubKernel(),
            "inner_narrator": lambda pulse_snapshot, self_model, log_path=None: "introspection",  # noqa: E731
            "simulation_engine": StubSimulation(),
            "pulse_snapshot": {"cycle": 1},
            "self_model": {"identity": "tester"},
        }

    first = run_consciousness_cycle(_build_context())
    second = run_consciousness_cycle(_build_context())

    assert first == second
    assert first["pulse_updates"] == {"focus": "stub-focus", "cycles": 1}
    assert first["self_model_updates"] == {"generated": False, "cycles": 1}
    assert first["introspection_output"] == "introspection"
    assert first["simulation_output"] == {"summary": "stable", "transcript": ["safe"]}


def test_no_pulse_bus_activity_without_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def _capture_publish(payload: Dict[str, object]) -> None:
        captured.append("publish")

    monkeypatch.setattr(pulse_bus, "publish", _capture_publish)

    result = run_consciousness_cycle({})

    assert result == {
        "pulse_updates": None,
        "self_model_updates": None,
        "introspection_output": None,
        "simulation_output": None,
    }
    assert captured == []


def test_state_stable_between_calls() -> None:
    kernel = StubKernel()
    context = {"kernel": kernel}

    first = run_consciousness_cycle(context)
    second = run_consciousness_cycle({})

    assert first["self_model_updates"] == {"generated": False, "cycles": 1}
    assert second["self_model_updates"] is None
    assert kernel.cycles == 1


def test_introspection_and_simulation_privacy() -> None:
    simulation = StubSimulation()

    result = run_consciousness_cycle(
        {
            "inner_narrator": lambda *_args, **_kwargs: "private-reflection",  # noqa: E731
            "simulation_engine": simulation,
            "pulse_snapshot": {"cycle": 3},
            "self_model": {},
            "introspection_log_path": "should-not-leak.log",
        }
    )

    assert result["introspection_output"] == "private-reflection"
    assert "should-not-leak" not in str(result)
    assert result["simulation_output"] == {"summary": "stable", "transcript": ["safe"]}
    assert simulation.cycles == 1
