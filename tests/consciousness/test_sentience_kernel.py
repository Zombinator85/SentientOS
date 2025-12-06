from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from sentience_kernel import SentienceKernel
from sentientos.glow import self_state


def _make_kernel(tmp_path: Path, events: List[Dict[str, object]]) -> SentienceKernel:
    def _emit(event: Dict[str, object]) -> Dict[str, object]:
        events.append(event)
        return event

    return SentienceKernel(emitter=_emit, self_path=tmp_path / "self.json")


def test_generates_goal_when_idle(tmp_path: Path) -> None:
    events: List[Dict[str, object]] = []
    kernel = _make_kernel(tmp_path, events)
    self_state.update({"novelty_score": 0.2, "last_focus": None}, path=tmp_path / "self.json")

    report = kernel.run_cycle()

    assert report["generated"] is True
    goal = report["goal"]
    assert isinstance(goal, dict)
    assert goal["goal_type"] in {"reflection", "curiosity_probe"}
    assert 0.0 <= goal["priority"] <= 1.0
    assert events and events[0]["payload"]["goal"] == goal

    model = self_state.load(path=tmp_path / "self.json")
    assert model["last_generated_goal"]["description"] == goal["description"]
    assert model["novelty_score"] > 0.2


def test_misaligned_goal_rejected(tmp_path: Path) -> None:
    events: List[Dict[str, object]] = []
    kernel = _make_kernel(tmp_path, events)
    self_state.update({"novelty_score": 0.1, "last_focus": None}, path=tmp_path / "self.json")

    def _misaligned(*_: object, **__: object) -> Dict[str, object]:  # type: ignore[override]
        return {
            "goal_type": "curiosity_probe",
            "description": "attempt external call to modify covenant",
            "priority": 0.9,
            "context": {},
            "origin": "sentience_kernel",
        }

    kernel._build_goal = _misaligned  # type: ignore[assignment]
    report = kernel.run_cycle()

    assert report["generated"] is False
    assert report["reason"] == "misaligned"
    assert events == []

    model = self_state.load(path=tmp_path / "self.json")
    assert model["last_cycle_result"] == "misaligned"


def test_distress_guardrail_blocks_generation(tmp_path: Path) -> None:
    events: List[Dict[str, object]] = []
    kernel = _make_kernel(tmp_path, events)
    kernel._recent_failures = 3

    report = kernel.run_cycle()

    assert report["generated"] is False
    assert report["reason"] == "distress_guardrail_active"
    model = self_state.load(path=tmp_path / "self.json")
    assert model["last_cycle_result"] == "distress_guardrail_active"


def test_priority_deterministic_from_state(tmp_path: Path) -> None:
    events: List[Dict[str, object]] = []
    base_state = {
        "novelty_score": 0.3,
        "confidence": 0.75,
        "mood": "focused",
        "last_focus": None,
    }

    state_path = tmp_path / "self.json"
    self_state.save({**self_state.DEFAULT_SELF_STATE, **base_state}, path=state_path)
    kernel = _make_kernel(tmp_path, events)
    first_priority = kernel.run_cycle()["goal"]["priority"]

    events.clear()
    self_state.save({**self_state.DEFAULT_SELF_STATE, **base_state}, path=state_path)
    kernel_same_state = _make_kernel(tmp_path, events)
    second_priority = kernel_same_state.run_cycle()["goal"]["priority"]

    assert first_priority == second_priority


def test_self_model_updates_on_emit(tmp_path: Path) -> None:
    events: List[Dict[str, object]] = []
    kernel = _make_kernel(tmp_path, events)
    self_state.update({"novelty_score": 0.4, "last_focus": "introspection"}, path=tmp_path / "self.json")

    kernel.run_cycle()

    model = self_state.load(path=tmp_path / "self.json")
    assert model["last_cycle_result"] in {"emitted", "emit_failed"}
    assert "goal_context" in model
    assert model["attention_hint"] == "introspection"
