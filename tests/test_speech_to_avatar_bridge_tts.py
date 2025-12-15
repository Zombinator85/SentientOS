from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from avatar_state import AvatarStateEmitter
from control_plane import AuthorizationRecord, RequestType, admit_request
from speech_emitter import SpeechEmitter
from speech_log import get_recent_speech
from speech_to_avatar_bridge import SpeechToAvatarBridge


def _base_state() -> dict[str, Any]:
    return {"mood": "calm", "intensity": 0.5, "expression": "rest", "motion": "idle"}


def _tts_auth() -> AuthorizationRecord:
    return admit_request(
        request_type=RequestType.SPEECH_TTS,
        requester_id="narrator",
        intent_hash="tts",
        context_hash="ctx-speech",
        policy_version="v1-static",
        metadata={"approved_by": "reviewer"},
    ).record


class _StubTts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def play(self, phrase: str, *, voice: str | None = None) -> bool:  # pragma: no cover - trivial
        self.calls.append((phrase, voice))
        return True

    def is_available(self) -> bool:
        return True


def test_speak_text_invokes_tts_and_logs(tmp_path: Path) -> None:
    target = tmp_path / "avatar_state.json"
    speech_log = tmp_path / "speech_log.jsonl"
    bridge = SpeechToAvatarBridge(
        SpeechEmitter(AvatarStateEmitter(target), base_state=_base_state()),
        log_path=speech_log,
    )
    bridge.tts_player = _StubTts()

    payload = bridge.speak_text(
        "Testing TTS",
        visemes=[{"time": 0.0, "duration": 0.1, "viseme": "A"}],
        mode="REMOTE",
        authorization=_tts_auth(),
    )

    assert bridge.tts_player.calls == [("Testing TTS", None)]
    assert payload["speaking"] is True
    assert payload["phrase"]["text"] == "Testing TTS"
    assert payload["viseme_timeline"][0]["viseme"] == "A"

    final_state = json.loads(target.read_text())
    assert final_state["speaking"] is False

    log_entries = [json.loads(line) for line in speech_log.read_text().splitlines() if line.strip()]
    assert len(log_entries) == 2
    assert log_entries[0]["event"] == "start"
    assert log_entries[1]["event"] == "stop"
    assert log_entries[0]["text"] == "Testing TTS"


def test_speak_text_respects_muted_and_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "avatar_state.json"
    speech_log = tmp_path / "speech_log.jsonl"
    stub = _StubTts()

    bridge = SpeechToAvatarBridge(
        SpeechEmitter(AvatarStateEmitter(target), base_state=_base_state()),
        log_path=speech_log,
    )
    bridge.tts_player = stub

    bridge.speak_text("Muted payload", muted=True, authorization=_tts_auth())
    assert stub.calls == []

    written = json.loads(target.read_text())
    assert written["phrase"]["muted"] is True
    assert written["speaking"] is False

    monkeypatch.setenv("SENTIENTOS_MODE", "LOCAL_OWNER")
    target_owner = tmp_path / "avatar_state_owner.json"
    bridge_owner = SpeechToAvatarBridge(
        SpeechEmitter(AvatarStateEmitter(target_owner), base_state=_base_state()),
        log_path=speech_log,
    )
    owner_stub = _StubTts()
    bridge_owner.tts_player = owner_stub
    bridge_owner.speak_text("Owner muted", mode="LOCAL_OWNER", authorization=_tts_auth())

    assert owner_stub.calls == []
    owner_state = json.loads(target_owner.read_text())
    assert owner_state["phrase"]["muted"] is True
    assert owner_state["speaking"] is False


def test_speak_text_can_skip_avatar_forwarding(tmp_path: Path) -> None:
    speech_log = tmp_path / "speech_log.jsonl"
    bridge = SpeechToAvatarBridge(
        SpeechEmitter(AvatarStateEmitter(tmp_path / "unused.json"), base_state=_base_state()),
        log_path=speech_log,
    )
    bridge.forward_avatar = False
    stub = _StubTts()
    bridge.tts_player = stub

    payload = bridge.speak_text(
        "Logging only", visemes=[{"time": 0.0, "viseme": "X"}], authorization=_tts_auth()
    )

    assert payload["speaking"] is True
    assert stub.calls == [("Logging only", None)]

    recent = get_recent_speech(log_path=speech_log)
    assert recent is not None
    assert recent.get("text") == "Logging only"
