from __future__ import annotations

from datetime import datetime

import pytest

from sentientos.gaming_companion_bridge import (
    CompanionBridgeError,
    CompanionBridgeReceiver,
    encode_message,
)
from sentientos.gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
    CompanionBridgeTransportError,
    bridge_message_id,
)

pytestmark = pytest.mark.no_legacy_skip

KEY = b"windows-observer-test-key-material-32-bytes"
ACK_KEY = b"sentientos-core-test-key-material-32-bytes"
STAMP = "2026-11-02T00:00:00+00:00"
NOW = datetime.fromisoformat(STAMP)


def _message(sequence: int = 1, *, key: bytes = KEY) -> bytes:
    return encode_message(
        kind="observation", source_id="windows-observer", session_id="test-session",
        generation_id="observer-generation-1", sequence=sequence,
        payload={"game_foreground": True}, key=key, created_at=STAMP,
    )


def _receiver(source: str, generation: str, key: bytes) -> CompanionBridgeReceiver:
    return CompanionBridgeReceiver(source_keys={source: key},
        expected_generations={source: generation}, clock=lambda: NOW.timestamp())


def _runtime(*, queue_capacity: int = 2) -> CompanionBridgeLoopbackRuntime:
    return CompanionBridgeLoopbackRuntime(
        receiver=_receiver("windows-observer", "observer-generation-1", KEY),
        acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="core-generation-1",
        acknowledgment_key=ACK_KEY, queue_capacity=queue_capacity,
        socket_timeout_seconds=0.5, clock=lambda: NOW,
    )


def _client(port: int) -> CompanionBridgeLoopbackClient:
    return CompanionBridgeLoopbackClient(
        port=port,
        acknowledgment_receiver=_receiver("sentientos-core", "core-generation-1", ACK_KEY),
        timeout_seconds=0.5,
    )


def test_loopback_runtime_verifies_queues_and_authenticates_acknowledgment():
    runtime = _runtime()
    port = runtime.start()
    try:
        assert runtime.status().running is True
        acknowledgment = _client(port).send(_message())
        received = runtime.receive(timeout=0.5)

        assert acknowledgment.kind == "acknowledgment"
        assert acknowledgment.payload["disposition"] == "accepted"
        assert acknowledgment.payload["message_id"] == bridge_message_id(_message())
        assert received.kind == "observation"
        assert received.payload == {"game_foreground": True}
        assert runtime.status().accepted_messages == 1
    finally:
        runtime.close()
    assert runtime.status().running is False
    with pytest.raises(CompanionBridgeError, match="bridge_runtime_generation_rotation_required"):
        runtime.start()


def test_queue_backpressure_does_not_consume_sequence_and_explicit_reconnect_recovers():
    runtime = _runtime(queue_capacity=1)
    port = runtime.start()
    client = _client(port)
    try:
        client.send(_message(sequence=1))
        blocked = _message(sequence=2)
        with pytest.raises(CompanionBridgeTransportError) as caught:
            client.send(blocked)
        assert caught.value.code == "bridge_backpressure_rejected"
        assert caught.value.delivery_state == "not_accepted"
        assert runtime.status().accepted_messages == 1
        assert runtime.receive(timeout=0.5).sequence == 1

        # The same not-yet-accepted frame can be sent after queue capacity returns.
        assert client.send(blocked).payload["message_id"] == bridge_message_id(blocked)
        assert runtime.receive(timeout=0.5).sequence == 2
        assert runtime.status().accepted_messages == 2
        assert runtime.status().rejected_connections >= 1
    finally:
        runtime.close()


def test_authentication_failure_is_not_enqueued():
    runtime = _runtime()
    port = runtime.start()
    try:
        with pytest.raises(CompanionBridgeError):
            _client(port).send(_message(key=b"not-the-authorized-key-material-32-bytes"))
        assert runtime.status().accepted_messages == 0
        assert runtime.status().rejected_connections == 1
        with pytest.raises(CompanionBridgeError, match="bridge_receive_timeout"):
            runtime.receive(timeout=0.01)
    finally:
        runtime.close()


def test_runtime_rejects_non_loopback_and_unbounded_configuration():
    receiver = _receiver("windows-observer", "observer-generation-1", KEY)
    common = dict(receiver=receiver, acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="core-generation-1", acknowledgment_key=ACK_KEY)
    with pytest.raises(CompanionBridgeError, match="bridge_loopback_port_invalid"):
        CompanionBridgeLoopbackRuntime(**common, port=-1)
    with pytest.raises(CompanionBridgeError, match="bridge_queue_capacity_invalid"):
        CompanionBridgeLoopbackRuntime(**common, queue_capacity=0)
    with pytest.raises(CompanionBridgeError, match="bridge_socket_timeout_invalid"):
        CompanionBridgeLoopbackRuntime(**common, socket_timeout_seconds=float("nan"))


def test_message_id_rejects_noncanonical_or_unframed_data():
    with pytest.raises(CompanionBridgeError, match="bridge_envelope_size_invalid"):
        bridge_message_id(b"")
    with pytest.raises(CompanionBridgeError, match="bridge_envelope_noncanonical"):
        bridge_message_id(_message() + b" ")


def test_acknowledgment_disposition_is_closed_when_present():
    with pytest.raises(CompanionBridgeError, match="bridge_acknowledgment_disposition_invalid"):
        encode_message(kind="acknowledgment", source_id="sentientos-core",
            session_id="test-session", generation_id="core-generation-1", sequence=1,
            payload={"message_id": "a" * 64, "disposition": []}, key=ACK_KEY,
            created_at=STAMP)
