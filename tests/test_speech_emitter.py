import json
from pathlib import Path

import pytest

from avatar_state import AvatarStateEmitter
from speech_emitter import DEFAULT_VISEME_DURATION, SpeechEmitter


def _base_state() -> dict[str, object]:
    return {"mood": "joy", "intensity": 0.7, "expression": "smile", "motion": "wave"}


def test_speech_emitter_tracks_phrase_and_speaking(tmp_path: Path) -> None:
    target = tmp_path / "avatar_state.json"
    speech = SpeechEmitter(AvatarStateEmitter(target), base_state=_base_state())

    payload = speech.emit_phrase("Hello there")
    written = json.loads(target.read_text())

    assert written["current_phrase"] == "Hello there"
    assert written["is_speaking"] is True
    assert written["viseme_timeline"] == []
    assert written["viseme_events"] == []
    assert payload["expression"] == "smile"

    idle = speech.emit_idle()
    written_idle = json.loads(target.read_text())

    assert written_idle["is_speaking"] is False
    assert written_idle["current_phrase"] == ""
    assert written_idle["viseme_timeline"] == []
    assert written_idle["viseme_events"] == []
    assert idle["motion"] == "wave"


def test_speech_emitter_extracts_rhubarb_visemes(tmp_path: Path) -> None:
    cues = {
        "mouthCues": [
            {"start": 0.0, "end": 0.12, "value": "A"},
            {"start": 0.12, "end": 0.32, "value": "B"},
        ]
    }
    viseme_file = tmp_path / "cues.json"
    viseme_file.write_text(json.dumps(cues), encoding="utf-8")

    target = tmp_path / "avatar_state.json"
    speech = SpeechEmitter(AvatarStateEmitter(target), base_state=_base_state())
    payload = speech.emit_phrase("Testing visemes", visemes=viseme_file)

    timeline = payload["viseme_timeline"]
    assert len(timeline) == 2
    assert timeline[0]["viseme"] == "A"
    assert timeline[0]["time"] == pytest.approx(0.0)
    assert timeline[0]["duration"] == pytest.approx(0.12, rel=1e-3)
    assert timeline[1]["viseme"] == "B"
    assert timeline[1]["time"] == pytest.approx(0.12, rel=1e-3)
    assert timeline[1]["duration"] == pytest.approx(0.20, rel=1e-3)

    written = json.loads(target.read_text())
    assert written["viseme_events"] == timeline


def test_speech_emitter_json_conformance_local_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_MODE", "LOCAL_OWNER")
    target = tmp_path / "avatar_state.json"
    speech = SpeechEmitter(AvatarStateEmitter(target), base_state=_base_state())

    payload = speech.emit_phrase("Owner phrase", visemes=[{"time": 0.0, "viseme": "X"}])
    written = json.loads(target.read_text())

    assert written["local_owner"] is True
    assert written["is_speaking"] is True
    assert isinstance(written["viseme_timeline"], list)
    assert written["viseme_timeline"][0]["viseme"] == "X"
    assert written["viseme_timeline"][0]["duration"] == pytest.approx(DEFAULT_VISEME_DURATION)
    assert payload["mode"] == "LOCAL_OWNER"
