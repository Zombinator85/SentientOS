from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pytest

from inner_narrator import generate_reflection, run_cycle, validate_reflection, write_introspection_entry
from sentientos.glow import self_state


@pytest.fixture(autouse=True)
def sentientos_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    return tmp_path


def test_generate_reflection_deterministic(tmp_path: Path) -> None:
    self_model = self_state.load()
    pulse_snapshot = {"cycle": 1, "events": [{"type": "heartbeat"}], "focus": "runtime"}

    first = generate_reflection(pulse_snapshot, self_model)
    second = generate_reflection(pulse_snapshot, self_model)

    assert first == second
    reflection_text = first[0]
    assert reflection_text.count(".") <= 3


def test_run_cycle_updates_self_model(tmp_path: Path) -> None:
    pulse_snapshot: Dict[str, object] = {
        "cycle": 2,
        "events": [{"type": "attention"}, {"type": "cache"}],
        "attention": {"target": "memory", "context": "cache refresh"},
    }
    starting_model = self_state.load()

    reflection = run_cycle(pulse_snapshot, starting_model)

    stored = self_state.load()
    assert stored["last_reflection_summary"] == reflection
    assert stored["last_focus"] == "memory"
    assert stored["attention_level"] == "elevated"
    assert stored["mood"] in {"stable", "curious", "uncertain"}
    assert stored["novelty_score"] == starting_model["novelty_score"]

    log_path = Path(tmp_path) / "glow" / "introspection.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().splitlines()[-1])
    assert entry["reflection"] == reflection
    assert entry["cycle"] == 2


def test_validate_reflection_guards() -> None:
    with pytest.raises(ValueError):
        validate_reflection("Please modify configuration now")
    with pytest.raises(ValueError):
        validate_reflection("External user influence detected")


def test_write_introspection_entry_privacy(tmp_path: Path) -> None:
    reflection = "System cycle stable; noticed runtime. Internal interpretation steady; mood stable."
    path = write_introspection_entry(reflection, focus="runtime", mood="stable", cycle=3)

    assert path.parent.name == "glow"
    data = json.loads(path.read_text().splitlines()[-1])
    assert data["focus"] == "runtime"
    assert data["mood"] == "stable"
    assert data["cycle"] == 3
