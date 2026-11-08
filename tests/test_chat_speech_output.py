from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from control_plane import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from control_plane.task_admission import AdmissionResponse
from sentientos.chat_speech_output import (
    ChatSpeechOutputController,
    LocalSystemSpeechPlayer,
    MAX_SPOKEN_CHARS,
    WindowsSapiLocalSpeechPlayer,
)

pytestmark = pytest.mark.no_legacy_skip


class AdmissionStub:
    def __init__(self, decisions: tuple[Decision, ...] = ()) -> None:
        self.decisions = iter(decisions)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> AdmissionResponse:
        call = dict(kwargs)
        self.calls.append(call)
        decision = next(self.decisions, Decision.ALLOW)
        reason = ReasonCode.OK if decision is Decision.ALLOW else ReasonCode.HUMAN_APPROVAL_REQUIRED
        record = AuthorizationRecord.create(
            request_type=call["request_type"], requester_id=str(call["requester_id"]),
            intent_hash=str(call["intent_hash"]), context_hash=str(call["context_hash"]),
            policy_version=str(call["policy_version"]), decision=decision, reason=reason,
            metadata=call.get("metadata"),
        )
        return AdmissionResponse(decision, reason, record)


class FakePlayer:
    def __init__(self, *, available: bool = True, hold: bool = False) -> None:
        self.is_available = available
        self.hold = hold
        self.started = threading.Event()
        self.release = threading.Event()
        self.spoken: list[str] = []
        self.stop_calls = 0

    def available(self) -> bool:
        return self.is_available

    def speak(self, text: str) -> bool:
        self.started.set()
        if self.hold:
            self.release.wait(timeout=1)
        self.spoken.append(text)
        return True

    def stop(self) -> None:
        self.stop_calls += 1
        self.release.set()


class TimedFakePlayer(FakePlayer):
    def speak_with_timing(self, text, event_sink, *, monotonic_clock=time.monotonic):
        self.started.set()
        event_sink({"event": "word_started", "word_index": 1, "char_start": 0,
                    "char_length": 5, "elapsed_seconds": 0.04,
                    "timing_quality": "backend_word_start"})
        if self.hold:
            self.release.wait(timeout=1)
        self.spoken.append(text)
        return True


def _enabled(controller: ChatSpeechOutputController, session: str = "session-1") -> None:
    assert controller.set_enabled(session, True)["enabled"] is True


def _await_status(controller: ChatSpeechOutputController, wanted: str) -> None:
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if controller.state("session-1")["playback_status"] == wanted:
            return
        time.sleep(0.005)
    raise AssertionError(f"speech playback did not reach {wanted}")


def test_speech_requires_session_grant_and_exact_turn_admission() -> None:
    player = FakePlayer()
    admission = AdmissionStub()
    output = ChatSpeechOutputController(admission_provider=admission, player=player)
    try:
        assert output.publish_response(session_id="session-1", turn_id="turn-1",
            text="hello", output_digest="a" * 64) == {"status": "disabled"}
        _enabled(output)
        result = output.publish_response(session_id="session-1", turn_id="turn-1",
            text="hello", output_digest="a" * 64)
        assert result == {"status": "queued", "text_truncated": False}
        assert player.started.wait(timeout=1)
        _await_status(output, "played")
        assert player.spoken == ["hello"]
        assert [call["request_type"] for call in admission.calls] == [
            RequestType.SPEECH_TTS, RequestType.SPEECH_TTS]
        assert admission.calls[0]["metadata"]["approval_method"] == "local_chat_ui"
        assert admission.calls[1]["metadata"]["source_turn_id"] == "turn-1"
        assert admission.calls[1]["intent_hash"] == "sha256:" + "a" * 64
    finally:
        output.close()


def test_speech_denial_unavailable_backend_and_invalid_digest_fail_closed() -> None:
    denied = ChatSpeechOutputController(
        admission_provider=AdmissionStub((Decision.DENY,)), player=FakePlayer())
    try:
        result = denied.set_enabled("session-1", True)
        assert result["enabled"] is False
        assert result["reason"] == ReasonCode.HUMAN_APPROVAL_REQUIRED.value
    finally:
        denied.close()

    unavailable = ChatSpeechOutputController(player=FakePlayer(available=False))
    try:
        assert unavailable.set_enabled("session-1", True)["reason"] == (
            "local_voice_backend_unavailable")
        with pytest.raises(ValueError, match="chat_speech_output_digest_invalid"):
            unavailable.publish_response(session_id="session-1", turn_id="turn-1",
                text="not spoken", output_digest="bad")
    finally:
        unavailable.close()


def test_speech_grant_is_session_scoped_revocable_and_expires() -> None:
    now = [10.0]
    player = FakePlayer(hold=True)
    output = ChatSpeechOutputController(player=player, monotonic_clock=lambda: now[0])
    try:
        _enabled(output)
        blocked = output.set_enabled("session-2", True)
        assert blocked["reason"] == "another_speech_session_is_active"
        output.publish_response(session_id="session-1", turn_id="turn-1",
            text="one", output_digest="b" * 64)
        assert player.started.wait(timeout=1)
        disabled = output.set_enabled("session-1", False)
        assert disabled["enabled"] is False
        assert player.stop_calls == 1
        assert output.state("session-1")["enabled"] is False
        player.hold = False
        _enabled(output, "session-3")
        now[0] += output.GRANT_SECONDS
        assert output.state("session-3")["enabled"] is False
        assert output.publish_response(session_id="session-3", turn_id="turn-2",
            text="expired", output_digest="c" * 64)["status"] == "disabled"
    finally:
        output.close()


def test_interrupt_stops_active_voice_and_preserves_turn_scoped_truthful_status() -> None:
    player = FakePlayer(hold=True)
    output = ChatSpeechOutputController(player=player)
    try:
        _enabled(output)
        assert output.publish_response(session_id="session-1", turn_id="turn-speaking",
            text="still speaking", output_digest="9" * 64)["status"] == "queued"
        assert player.started.wait(timeout=1)
        interrupted = output.interrupt("session-1")
        assert interrupted == {"status": "interrupted"}
        assert player.stop_calls == 1
        deadline = time.monotonic() + 1
        while output.state("session-1")["active_turn_id"] is not None and time.monotonic() < deadline:
            time.sleep(0.005)
        assert output.state("session-1")["playback_status"] == "interrupted"
        assert output.state("session-1")["last_played_turn_id"] is None
        # Playback state from one conversation is never exposed to another.
        assert output.state("session-2")["last_played_turn_id"] is None
        assert output.interrupt("session-1") == {"status": "idle"}
    finally:
        player.release.set()
        output.close()


def test_speech_is_bounded_and_does_not_build_a_backlog() -> None:
    player = FakePlayer(hold=True)
    output = ChatSpeechOutputController(player=player)
    try:
        _enabled(output)
        long_text = "x" * (MAX_SPOKEN_CHARS + 20)
        first = output.publish_response(session_id="session-1", turn_id="turn-1",
            text=long_text, output_digest="d" * 64)
        assert first == {"status": "queued", "text_truncated": True}
        assert player.started.wait(timeout=1)
        second = output.publish_response(session_id="session-1", turn_id="turn-2",
            text="pending", output_digest="e" * 64)
        third = output.publish_response(session_id="session-1", turn_id="turn-3",
            text="too many", output_digest="f" * 64)
        assert second["status"] == "queued"
        assert third == {"status": "speaker_busy"}
        assert output.state("session-1")["playback_status"] == "speaker_busy"
        output.set_enabled("session-1", False)
    finally:
        player.release.set()
        output.close()
    assert player.spoken[0] == "x" * MAX_SPOKEN_CHARS
    assert "pending" not in player.spoken


def test_speech_emits_controller_boundaries_and_backend_word_timing() -> None:
    player = TimedFakePlayer()
    events: list[dict[str, Any]] = []
    output = ChatSpeechOutputController(player=player, timing_event_sink=events.append)
    try:
        _enabled(output)
        output.publish_response(session_id="session-1", turn_id="turn-timed",
            text="hello world", output_digest="a" * 64)
        assert player.started.wait(timeout=1)
        _await_status(output, "played")
        deadline = time.monotonic() + 1
        while len(events) < 3 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert [event["event"] for event in events] == [
            "speech_started", "word_started", "speech_finished"]
        word_event = events[1]
        assert word_event["turn_id"] == "turn-timed"
        assert word_event["session_id"] == "session-1"
        assert word_event["char_start"] == 0
        assert word_event["timing_quality"] == "backend_word_start"
    finally:
        output.close()


def test_windows_sapi_player_sends_text_over_stdin_and_hides_voice_text_from_argv() -> None:
    class Process:
        returncode = 0

        def __init__(self, args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.received_text = None

        def communicate(self, *, input, timeout):
            self.received_text = input

    processes = []

    def make_process(args, **kwargs):
        process = Process(args, **kwargs)
        processes.append(process)
        return process

    player = WindowsSapiLocalSpeechPlayer(
        powershell_path="powershell.exe", process_factory=make_process)
    text = "Local voice: quote ' and semicolon; remain plain input."

    assert player.available() is True
    assert player.speak(text) is True
    assert processes[0].received_text == text
    assert text not in " ".join(processes[0].args)
    assert processes[0].kwargs["stdin"] is not None
    assert player.playback_failure_code() is None


def test_local_system_player_falls_through_to_available_local_backend() -> None:
    class FailingPlayer(FakePlayer):
        def speak(self, text: str) -> bool:
            self.started.set()
            return False

        def playback_failure_code(self) -> str:
            return "primary_backend_failed"

    primary = FailingPlayer()
    fallback = FakePlayer()
    player = LocalSystemSpeechPlayer(players=(primary, fallback))

    assert player.available() is True
    assert player.speak("fallback remains local") is True
    assert primary.started.is_set()
    assert fallback.spoken == ["fallback remains local"]
    assert player.playback_failure_code() is None


def test_playback_failure_code_is_available_in_session_state() -> None:
    class FailedPlayer(FakePlayer):
        def speak(self, text: str) -> bool:
            self.started.set()
            return False

        def playback_failure_code(self) -> str:
            return "windows_sapi_playback_failed"

    player = FailedPlayer()
    output = ChatSpeechOutputController(player=player)
    try:
        _enabled(output)
        output.publish_response(session_id="session-1", turn_id="turn-failed",
            text="failed local output", output_digest="b" * 64)
        assert player.started.wait(timeout=1)
        _await_status(output, "playback_failed")
        state = output.state("session-1")
        assert state["playback_failure_code"] == "windows_sapi_playback_failed"
        assert output.state("session-2")["playback_failure_code"] is None
    finally:
        output.close()


def test_slow_avatar_timing_sink_does_not_block_local_audio_playback() -> None:
    entered_sink = threading.Event()
    release_sink = threading.Event()
    player = TimedFakePlayer()

    def slow_sink(event: dict[str, Any]) -> None:
        if event["event"] == "speech_started":
            entered_sink.set()
            release_sink.wait(timeout=2)

    output = ChatSpeechOutputController(player=player, timing_event_sink=slow_sink)
    try:
        _enabled(output)
        output.publish_response(session_id="session-1", turn_id="turn-fast",
            text="hello", output_digest="b" * 64)
        assert entered_sink.wait(timeout=1)
        _await_status(output, "played")
        assert player.spoken == ["hello"]
    finally:
        release_sink.set()
        output.close()
