from __future__ import annotations

import json
from pathlib import Path

import pytest

from avatar_state import AvatarState, AvatarStateEmitter, resolve_mode


def test_avatar_state_emitter_writes_expected_payload(tmp_path: Path) -> None:
    target = tmp_path / "avatar_state.json"
    emitter = AvatarStateEmitter(target)

    payload = emitter.emit(AvatarState(mood="joy", intensity=0.8, expression="smile", motion="wave"))

    written = json.loads(target.read_text())
    assert written == payload
    assert written["mood"] == "joy"
    assert written["expression"] == "smile"
    assert written["motion"] == "wave"
    assert written["local_owner"] is False
    assert written["speaking"] is False
    assert written["phrase"]["text"] == ""
    assert written["phrase"]["viseme_count"] == 0
    assert 0.0 <= written["intensity"] <= 1.0
    assert "timestamp" in written


def test_avatar_state_emitter_clamps_and_respects_local_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "avatar_state.json"
    emitter = AvatarStateEmitter(target)

    monkeypatch.setenv("SENTIENTOS_MODE", "LOCAL_OWNER")
    payload = emitter.emit(
        {
            "mood": "calm",
            "intensity": 2.4,
            "expression": "rest",
            "motion": "idle",
            "metadata": {"source": "test"},
        }
    )

    written = json.loads(target.read_text())
    assert written["intensity"] == 1.0
    assert written["local_owner"] is True
    assert written["mode"] == "LOCAL_OWNER"
    assert written["metadata"] == {"source": "test"}


def test_resolve_mode_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTIENTOS_MODE", raising=False)
    assert resolve_mode() is not None
