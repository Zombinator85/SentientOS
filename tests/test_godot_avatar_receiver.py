from __future__ import annotations

import io
import json
import socket
import sys

import pytest

from godot_avatar_receiver import (
    MAX_STATE_FILE_BYTES,
    MAX_VISEME_CUES,
    AvatarStateForwarder,
    available_loopback_udp_port,
)

pytestmark = pytest.mark.no_legacy_skip


def test_available_loopback_udp_port_is_bindable():
    port = available_loopback_udp_port()

    assert 1 <= port <= 65535
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(("127.0.0.1", port))


def _state(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "mood": "calm",
        "intensity": 0.5,
        "expression": "rest",
        "motion": "idle",
        "current_phrase": "Hello",
        "viseme_timeline": [{"time": 0.0, "duration": 0.1, "viseme": "A"}],
        "metadata": {"not_used_by_renderer": "large internal data must not cross the bridge"},
    }
    value.update(overrides)
    return value


def test_forwarder_emits_bounded_renderer_fields_only(tmp_path):
    state_path = tmp_path / "avatar_state.json"
    state_path.write_text(json.dumps(_state(intensity=4.0)), encoding="utf-8")

    payload = AvatarStateForwarder(state_path)._read_state()

    assert payload is not None
    assert payload["intensity"] == 1.0
    assert payload["viseme_timeline"] == [{"time": 0.0, "duration": 0.1, "viseme": "A"}]
    assert "metadata" not in payload


def test_forwarder_sends_unicode_phrase_without_logging_conversation_text(
    tmp_path, monkeypatch
) -> None:
    state_path = tmp_path / "avatar_state.json"
    state_path.write_text(json.dumps(_state(current_phrase="Cronos \U0001f3ae")), encoding="utf-8")
    forwarder = AvatarStateForwarder(state_path)
    payload = forwarder._read_state()
    assert payload is not None

    output = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(output, encoding="cp1252", errors="strict"))

    class CapturingSocket:
        message: bytes | None = None

        def sendto(self, message: bytes, _address: object) -> None:
            self.message = message

    sock = CapturingSocket()
    forwarder._send(sock, payload)
    assert sock.message is not None
    forwarded = json.loads(sock.message.decode("utf-8"))
    assert forwarded["current_phrase"] == "Cronos \U0001f3ae"
    logged = output.getvalue().decode("cp1252")
    assert "phrase_present=True" in logged
    assert "phrase_chars=8" in logged
    assert "Cronos" not in logged


def test_forwarder_preserves_only_chat_command_correlation_for_renderer_report(tmp_path):
    state_path = tmp_path / "avatar_state.json"
    state_path.write_text(json.dumps(_state(metadata={
        "session_id": "session-1", "turn_id": "turn-2", "output_digest": "a" * 64,
        "output_mode": "chat_response_visual_only", "workload_mode": "gaming",
        "approval_grant_digest": "private-governance-field", "extra": "discarded",
    })), encoding="utf-8")

    payload = AvatarStateForwarder(state_path)._read_state()

    assert payload is not None
    assert payload["metadata"] == {
        "session_id": "session-1", "turn_id": "turn-2", "output_digest": "a" * 64,
        "output_mode": "chat_response_visual_only",
    }
    assert payload["workload_mode"] == "gaming"


@pytest.mark.parametrize("workload_mode", ["normal", "gaming"])
def test_forwarder_exposes_only_closed_workload_mode_for_renderer(tmp_path, workload_mode):
    state_path = tmp_path / "avatar_state.json"
    state_path.write_text(json.dumps(_state(metadata={"workload_mode": workload_mode,
        "secret_internal_field": "must not cross"})), encoding="utf-8")

    payload = AvatarStateForwarder(state_path)._read_state()

    assert payload is not None
    assert payload["workload_mode"] == workload_mode
    assert "metadata" not in payload
    assert "secret_internal_field" not in payload


@pytest.mark.parametrize("workload_mode", ["realtime", {"mode": "gaming"}, ["gaming"]])
def test_forwarder_drops_unknown_workload_mode(tmp_path, workload_mode):
    state_path = tmp_path / "avatar_state.json"
    state_path.write_text(json.dumps(_state(metadata={"workload_mode": workload_mode})), encoding="utf-8")

    payload = AvatarStateForwarder(state_path)._read_state()

    assert payload is not None
    assert "workload_mode" not in payload


def test_forwarder_rejects_non_object_and_oversized_state(tmp_path):
    state_path = tmp_path / "avatar_state.json"
    forwarder = AvatarStateForwarder(state_path)

    state_path.write_text("[]", encoding="utf-8")
    assert forwarder._read_state() is None

    state_path.write_bytes(b" " * (MAX_STATE_FILE_BYTES + 1))
    assert forwarder._read_state() is None


def test_forwarder_rejects_invalid_or_unbounded_viseme_data(tmp_path):
    state_path = tmp_path / "avatar_state.json"
    forwarder = AvatarStateForwarder(state_path)

    state_path.write_text(json.dumps(_state(viseme_timeline=[{"time": "nan"}])), encoding="utf-8")
    assert forwarder._read_state() is None

    state_path.write_text(json.dumps(_state(viseme_timeline=[{}] * (MAX_VISEME_CUES + 1))), encoding="utf-8")
    assert forwarder._read_state() is None


def test_forwarder_rejects_non_finite_and_oversized_text(tmp_path):
    state_path = tmp_path / "avatar_state.json"
    forwarder = AvatarStateForwarder(state_path)

    state_path.write_text(json.dumps(_state(intensity=float("nan"))), encoding="utf-8")
    assert forwarder._read_state() is None

    state_path.write_text(json.dumps(_state(current_phrase="x" * 4096)), encoding="utf-8")
    assert forwarder._read_state() is None

    state_path.write_text(
        json.dumps(_state(timestamp=float("inf"))), encoding="utf-8"
    )
    assert forwarder._read_state() is None
