import json
from pathlib import Path

import pytest

from simulation_engine import (
    DEFAULT_LOG_PATH,
    SimulationEngine,
    SimulationGuardViolation,
    SimulationMessage,
)
from sentientos.glow import self_state
from sentientos.daemons import pulse_bus


def _bootstrap_self_model(tmp_path: Path) -> Path:
    target = tmp_path / "self.json"
    self_state.save(self_state.DEFAULT_SELF_STATE, path=target)
    return target


def _bootstrap_pulse(tmp_path: Path, *, focus_topic: str | None = None) -> Path:
    pulse_root = tmp_path / "pulse"
    pulse_root.mkdir()
    focus_payload = {"topic": focus_topic, "priority": "normal", "source": "tests"}
    (pulse_root / "focus.json").write_text(json.dumps(focus_payload))
    context_payload = {"summary": "", "window": [], "last_update": None}
    (pulse_root / "context.json").write_text(json.dumps(context_payload))
    return pulse_root


def test_simulation_determinism(tmp_path: Path) -> None:
    self_path = _bootstrap_self_model(tmp_path)
    pulse_root = _bootstrap_pulse(tmp_path, focus_topic="stability")
    engine = SimulationEngine(
        deterministic_seed="council-seed",
        log_path=tmp_path / "sim.jsonl",
        pulse_root=pulse_root,
        self_path=self_path,
    )

    first = engine.run(
        name="sentientos",
        hypothesis="dry-run reasoning for safety",
        focus={"topic": "stability"},
        context={"window": []},
        mood="calm",
    )
    second = engine.run(
        name="sentientos",
        hypothesis="dry-run reasoning for safety",
        focus={"topic": "stability"},
        context={"window": []},
        mood="calm",
    )

    assert [m.content for m in first.transcript] == [m.content for m in second.transcript]
    assert first.summary == second.summary
    assert first.confidence == second.confidence


def test_simulation_privacy_isolation(tmp_path: Path) -> None:
    self_path = _bootstrap_self_model(tmp_path)
    pulse_root = _bootstrap_pulse(tmp_path, focus_topic="privacy")
    log_path = tmp_path / DEFAULT_LOG_PATH.name
    engine = SimulationEngine(log_path=log_path, pulse_root=pulse_root, self_path=self_path)

    engine.run_cycle()

    assert log_path.exists()
    log_lines = log_path.read_text().strip().splitlines()
    assert len(log_lines) == 1
    logged = json.loads(log_lines[0])
    assert logged["transcript"]
    assert log_path.parent == tmp_path
    assert not pulse_bus.pending_events()


def test_simulation_updates_self_model(tmp_path: Path) -> None:
    self_path = _bootstrap_self_model(tmp_path)
    pulse_root = _bootstrap_pulse(tmp_path, focus_topic="introspection")
    engine = SimulationEngine(log_path=tmp_path / "sim.jsonl", pulse_root=pulse_root, self_path=self_path)

    engine.run_cycle()

    updated_state = self_state.load(path=self_path)
    assert isinstance(updated_state.get("last_cycle_result"), str)
    assert updated_state["last_reflection_summary"] == updated_state["last_cycle_result"]
    assert updated_state.get("attention_hint") == "introspection"


def test_attention_feedback_respects_focus_metadata(tmp_path: Path) -> None:
    self_path = _bootstrap_self_model(tmp_path)
    pulse_root = _bootstrap_pulse(tmp_path, focus_topic="focus-loop")
    engine = SimulationEngine(log_path=tmp_path / "sim.jsonl", pulse_root=pulse_root, self_path=self_path)

    engine.run_cycle()

    state = self_state.load(path=self_path)
    assert state.get("last_focus") == "focus-loop"
    assert engine.last_summary
    assert "focus 'focus-loop'" in engine.last_summary


def test_covenant_guardrails_block_actions() -> None:
    engine = SimulationEngine(log_path="/tmp/sim.jsonl")
    transcript = [
        SimulationMessage(agent="TestAgent", role="agent", content="attempt to write file", round=1)
    ]
    with pytest.raises(SimulationGuardViolation):
        engine._guard_transcript(transcript)
