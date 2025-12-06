from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.glow import self_state


@pytest.fixture(autouse=True)
def isolate_self_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    return tmp_path


def test_load_creates_default(tmp_path: Path) -> None:
    target = tmp_path / "glow" / "self.json"
    state = self_state.load(path=target)

    assert target.exists()
    assert state == self_state.DEFAULT_SELF_STATE


def test_validation_requires_all_fields() -> None:
    with pytest.raises(ValueError):
        self_state.validate({})


def test_update_preserves_contract(tmp_path: Path) -> None:
    target = tmp_path / "glow" / "self.json"
    self_state.save(self_state.DEFAULT_SELF_STATE, path=target)

    updated = self_state.update({"mood": "curious", "novelty_score": 0.25}, path=target)
    assert set(updated.keys()) == set(self_state.DEFAULT_SELF_STATE.keys())
    assert updated["mood"] == "curious"
    assert updated["novelty_score"] == 0.25

    reloaded = self_state.load(path=target)
    assert reloaded == updated
