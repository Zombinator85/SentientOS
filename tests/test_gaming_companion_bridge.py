from __future__ import annotations

from datetime import datetime
import json

import pytest

from sentientos.gaming_companion_bridge import (
    CompanionBridgeError,
    CompanionBridgeReceiver,
    encode_message,
    read_frame,
    send_frame,
)

pytestmark = pytest.mark.no_legacy_skip

KEY = b"test-only-bridge-key-material-32-bytes!!"
STAMP = "2026-11-02T00:00:00+00:00"
NOW = datetime.fromisoformat(STAMP).timestamp()


class ByteStream:
    """In-memory framing adapter; this sandbox denies socketpair writes."""

    def __init__(self, initial=b"", *, closed=False):
        self.buffer = bytearray(initial)
        self.closed = closed

    def sendall(self, value):
        self.buffer.extend(value)

    def recv(self, size):
        if not self.buffer:
            return b""
        value = bytes(self.buffer[:size])
        del self.buffer[:size]
        return value


def receiver(*, generation="win-observer-run-1", key=KEY):
    return CompanionBridgeReceiver(
        source_keys={"windows-observer": key},
        expected_generations={"windows-observer": generation},
        clock=lambda: NOW,
    )


def message(*, sequence=1, generation="win-observer-run-1", kind="observation",
            payload=None, admission=None, key=KEY, created_at=STAMP):
    return encode_message(
        kind=kind,
        source_id="windows-observer",
        session_id="companion-session-1",
        generation_id=generation,
        sequence=sequence,
        payload=payload or {"game_foreground": True, "process_name_digest": "a" * 64},
        admission=admission,
        key=key,
        created_at=created_at,
    )


def test_authenticated_windows_observation_round_trips_in_memory_frame_adapter():
    encoded = message()
    stream = ByteStream()
    send_frame(stream, encoded)
    decoded = receiver().accept(read_frame(stream))

    assert decoded.kind == "observation"
    assert decoded.source_id == "windows-observer"
    assert decoded.generation_id == "win-observer-run-1"
    assert decoded.sequence == 1
    assert decoded.payload["game_foreground"] is True
    assert len(decoded.message_id) == 64


def test_avatar_command_requires_and_preserves_admission_binding():
    admission = {"receipt_id": "avatar-admission-7", "semantic_digest": "b" * 64}
    encoded = message(kind="avatar_command", payload={
        "output_mode": "chat_response_visual_only", "phrase": "hello", "motion": "nod",
    }, admission=admission)

    accepted = receiver().accept(encoded)

    assert accepted.kind == "avatar_command"
    assert accepted.admission == admission


def test_avatar_command_without_admission_is_rejected_before_transport():
    with pytest.raises(CompanionBridgeError, match="avatar_command_admission_required"):
        message(kind="avatar_command", payload={"output_mode": "chat_response_visual_only"})


def test_avatar_command_rejects_fields_outside_visual_output_scope():
    admission = {"receipt_id": "avatar-admission-7", "semantic_digest": "b" * 64}
    with pytest.raises(CompanionBridgeError, match="avatar_command_field_unsupported"):
        message(kind="avatar_command", payload={
            "output_mode": "chat_response_visual_only", "shell_command": "start-process",
        }, admission=admission)


@pytest.mark.parametrize("encoded,reason", [
    (message(key=b"different-key-material-32-bytes-long!"), "bridge_authentication_failed"),
    (message(generation="old-run"), "bridge_generation_stale"),
    (message(created_at="2020-01-01T00:00:00+00:00"), "bridge_message_stale"),
])
def test_source_generation_authentication_and_freshness_fail_closed(encoded, reason):
    with pytest.raises(CompanionBridgeError, match=reason):
        receiver().accept(encoded)


def test_tampered_payload_is_rejected():
    envelope = json.loads(message())
    envelope["payload"]["game_foreground"] = False
    encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()

    with pytest.raises(CompanionBridgeError, match="bridge_payload_digest_mismatch"):
        receiver().accept(encoded)


def test_noncanonical_json_is_rejected():
    with pytest.raises(CompanionBridgeError, match="bridge_envelope_noncanonical"):
        receiver().accept(message() + b" ")


def test_duplicate_and_out_of_order_sequences_are_rejected():
    instance = receiver()
    instance.accept(message(sequence=2))

    with pytest.raises(CompanionBridgeError, match="bridge_replay_or_out_of_order"):
        instance.accept(message(sequence=2))
    with pytest.raises(CompanionBridgeError, match="bridge_replay_or_out_of_order"):
        instance.accept(message(sequence=1))


def test_frame_reader_rejects_oversized_and_truncated_frames():
    with pytest.raises(CompanionBridgeError, match="bridge_frame_size_invalid"):
        read_frame(ByteStream((16 * 1024 + 1).to_bytes(4, "big")))

    with pytest.raises(CompanionBridgeError, match="bridge_frame_truncated"):
        read_frame(ByteStream((5).to_bytes(4, "big") + b"{}"))


def test_receiver_requires_explicit_key_and_generation_pairing():
    with pytest.raises(CompanionBridgeError, match="bridge_expected_generations_mismatch"):
        CompanionBridgeReceiver(source_keys={"windows-observer": KEY}, expected_generations={})
    with pytest.raises(CompanionBridgeError, match="bridge_key_too_short"):
        CompanionBridgeReceiver(source_keys={"windows-observer": b"short"},
                                expected_generations={"windows-observer": "run-1"})


def test_screen_capture_request_requires_exact_bounded_request_id():
    encoded = message(kind="screen_capture_request",
        payload={"capture_request_id": "0123456789abcdef0123456789abcdef"},
        admission=None)
    accepted = receiver().accept(encoded)
    assert accepted.kind == "screen_capture_request"

    with pytest.raises(CompanionBridgeError, match="screen_capture_request_invalid"):
        message(kind="screen_capture_request",
            payload={"capture_request_id": "too-short"}, admission=None)
