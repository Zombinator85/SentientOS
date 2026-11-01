from __future__ import annotations

from types import MappingProxyType
from typing import Dict

import pytest

from sentientos.consciousness.integration import run_consciousness_cycle
from sentientos.daemons import pulse_bus

pytestmark = pytest.mark.no_legacy_skip


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
    assert first["simulation_output"]["summary"] == "stable"
    assert first["simulation_output"]["transcript"] == ["safe"]


def test_no_pulse_bus_activity_without_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def _capture_publish(payload: Dict[str, object]) -> None:
        captured.append("publish")

    monkeypatch.setattr(pulse_bus, "publish", _capture_publish)

    result = run_consciousness_cycle({})

    assert result["pulse_updates"] is None
    assert result["self_model_updates"] is None
    assert result["introspection_output"] is None
    assert result["simulation_output"] is None
    assert "cognitive_state_snapshot" in result
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
    assert result["simulation_output"]["summary"] == "stable"
    assert result["simulation_output"]["transcript"] == ["safe"]
    assert simulation.cycles == 1


def test_integration_copies_mapping_outputs() -> None:
    class MappingArbitrator:
        def run_cycle(self) -> None:
            return None

        def telemetry_snapshot(self):
            return MappingProxyType({"focus": "stable"})

    class MappingKernel:
        def run_cycle(self):
            return MappingProxyType({"generated": False})

    result = run_consciousness_cycle(
        {"arbitrator": MappingArbitrator(), "kernel": MappingKernel()}
    )
    assert result["pulse_updates"] == {"focus": "stable"}
    assert result["self_model_updates"] == {"generated": False}


def test_integration_rejects_invalid_optional_paths_and_snapshots() -> None:
    with pytest.raises(TypeError, match="pressure_snapshot_path"):
        run_consciousness_cycle(
            {"include_pressure_snapshot": True, "pressure_snapshot_path": object()}
        )

    with pytest.raises(TypeError, match="pulse_snapshot must be a mapping"):
        run_consciousness_cycle(
            {"inner_narrator": lambda *_args, **_kwargs: "unused", "pulse_snapshot": "invalid"}
        )
