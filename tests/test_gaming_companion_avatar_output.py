from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.no_legacy_skip

from avatar_state import AvatarStateEmitter
from sentientos.gaming_companion_avatar_output import (
    BridgeChatAvatarOutputEmitter, WindowsEdgeAvatarCommandDispatchOwner,
    MutualTLSAvatarCommandSender, WindowsGodotAvatarStateQueue,
)
from sentientos.gaming_companion_bridge import (
    CompanionBridgeError, CompanionBridgeReceiver, VerifiedBridgeMessage,
    encode_message,
)
from sentientos.gaming_companion_tls_transport import CompanionBridgeMutualTLSClient
from sentientos.gaming_companion_tls_transport import CompanionBridgeMutualTLSRuntime
from control_plane import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from tests.test_gaming_companion_tls_transport import _certificate_bundle


class _Runtime:
    def receive(self, timeout=None):
        del timeout
        raise CompanionBridgeError("bridge_receive_timeout")


class _Client(CompanionBridgeMutualTLSClient):
    def __init__(self, receiver):
        self.receiver = receiver
        self.sent = []

    def send(self, encoded):
        message = self.receiver.accept(encoded)
        self.sent.append(message)
        return VerifiedBridgeMessage("ack-1", "acknowledgment", "sentientos-edge",
            message.session_id, "edge-generation-1", 1, message.created_at,
            {"message_id": message.message_id, "disposition": "accepted"}, None)


def _authorization():
    return AuthorizationRecord.create(request_type=RequestType.AVATAR_EMISSION,
        requester_id="bridge", intent_hash="a" * 64, context_hash="c" * 64,
        policy_version="test", decision=Decision.ALLOW, reason=ReasonCode.OK,
        metadata={"approved_by": "operator"})


def test_admitted_chat_output_crosses_signed_reverse_route_and_reaches_dispatcher():
    key = b"k" * 32
    receiver = CompanionBridgeReceiver(source_keys={"sentientos-core": key},
        expected_generations={"sentientos-core": "core-generation-1"})
    client = _Client(receiver)
    receipt = {"receipt_id": "admission-1", "semantic_digest": "b" * 64}
    sender = MutualTLSAvatarCommandSender(client=client, source_id="sentientos-core",
        session_id="session-1", generation_id="core-generation-1", source_key=key,
        admission_receipt_builder=lambda _authorization: receipt)
    emitter = BridgeChatAvatarOutputEmitter(sender)
    result = emitter.emit_display_text("Hello", authorization=_authorization(),
        metadata={"session_id": "session-1", "turn_id": "turn-1",
                  "output_digest": "a" * 64, "workload_mode": "gaming"})
    assert result == {"status": "sent", "acknowledgment_message_id": "ack-1",
                      "renderer_effect_proven": False}
    delivered = []
    dispatcher = WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(),
        receipt_verifier=lambda receipt_id, digest, _message:
            (receipt_id, digest) == (receipt["receipt_id"], receipt["semantic_digest"]),
        renderer_sink=lambda payload, _message: delivered.append(dict(payload)) is None)
    assert dispatcher.dispatch_one(client.sent[0]) is True
    assert delivered[0]["phrase"] == "Hello"
    assert delivered[0]["turn_id"] == "turn-1"
    assert delivered[0]["workload_mode"] == "gaming"
    assert dispatcher.status().renderer_effect_proven is False
    sender.close()


def test_admitted_chat_output_crosses_mutual_tls_into_edge_dispatcher(tmp_path):
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    source_key, acknowledgment_key = b"k" * 32, b"a" * 32
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1",
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={"sentientos-core": source_key},
            expected_generations={"sentientos-core": "core-generation-1"}),
        acknowledgment_source_id="sentientos-edge",
        acknowledgment_generation_id="edge-generation-1",
        acknowledgment_key=acknowledgment_key)
    port = runtime.start()
    acknowledgment_receiver = CompanionBridgeReceiver(
        source_keys={"sentientos-edge": acknowledgment_key},
        expected_generations={"sentientos-edge": "edge-generation-1"})
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=acknowledgment_receiver)
    receipt = {"receipt_id": "admission-1", "semantic_digest": "b" * 64}
    sender = MutualTLSAvatarCommandSender(client=client,
        source_id="sentientos-core", session_id="session-1",
        generation_id="core-generation-1", source_key=source_key,
        admission_receipt_builder=lambda _authorization: receipt)
    delivered = []
    dispatcher = WindowsEdgeAvatarCommandDispatchOwner(runtime=runtime,
        receipt_verifier=lambda receipt_id, digest, _message:
            (receipt_id, digest) == (receipt["receipt_id"], receipt["semantic_digest"]),
        renderer_sink=lambda payload, _message: delivered.append(dict(payload)) is None)
    try:
        emitter = BridgeChatAvatarOutputEmitter(sender)
        result = emitter.emit_display_text("Hello over mTLS",
            authorization=_authorization(),
            metadata={"turn_id": "turn-2", "output_digest": "c" * 64})
        message = runtime.receive(timeout=1.0)
        assert result["status"] == "sent"
        assert message.kind == "avatar_command"
        assert dispatcher.dispatch_one(message) is True
        assert delivered[0]["phrase"] == "Hello over mTLS"
        assert dispatcher.status().renderer_effect_proven is False
    finally:
        sender.close()
        runtime.close()


def verified_command(*, kind: str = "avatar_command"):
    key = b"k" * 32
    payload = {"output_mode": "chat_response_visual_only", "phrase": "Hello",
        "expression": "rest", "motion": "nod", "mood": "calm",
        "intensity": 0.25, "output_digest": "a" * 64, "turn_id": "turn-1"}
    admission = {"receipt_id": "admission-1", "semantic_digest": "b" * 64}
    envelope = encode_message(kind=kind, source_id="sentientos-core",
        session_id="session-1", generation_id="core-generation-1", sequence=1,
        payload=payload if kind == "avatar_command" else {"message_id": "prior-1"},
        key=key, created_at=datetime.now(timezone.utc).isoformat(),
        admission=admission if kind == "avatar_command" else None)
    receiver = CompanionBridgeReceiver(source_keys={"sentientos-core": key},
        expected_generations={"sentientos-core": "core-generation-1"})
    return receiver.accept(envelope), admission


def test_dispatch_requires_receipt_verification_before_renderer_queue():
    message, admission = verified_command()
    delivered = []
    owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(),
        receipt_verifier=lambda receipt, semantic, _message:
            (receipt, semantic) == (admission["receipt_id"], admission["semantic_digest"]),
        renderer_sink=lambda payload, _message: delivered.append(dict(payload)) is None)
    assert owner.dispatch_one(message) is True
    assert delivered == [dict(message.payload)]
    status = owner.status()
    assert (status.received, status.accepted, status.rejected) == (1, 1, 0)
    assert status.renderer_effect_proven is False


def test_dispatch_rejects_unverified_receipts_and_sink_denial_without_retry():
    message, _ = verified_command()
    calls = []
    owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(),
        receipt_verifier=lambda *_: False,
        renderer_sink=lambda *_: calls.append("sink") is None)
    assert owner.dispatch_one(message) is False
    assert calls == []
    assert owner.status().last_failure == "avatar_command_admission_unverified"
    assert owner.status().rejected == 1

    message, admission = verified_command()
    owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(),
        receipt_verifier=lambda *_: True, renderer_sink=lambda *_: False)
    assert owner.dispatch_one(message) is False
    assert owner.status().last_failure == "avatar_command_renderer_queue_rejected"
    assert owner.status().accepted == 0


def test_verified_command_updates_real_local_avatar_state_file_not_effect_claim(tmp_path):
    message, admission = verified_command()
    target = tmp_path / "avatar_state.json"
    state_queue = WindowsGodotAvatarStateQueue(
        state_emitter=AvatarStateEmitter(target))
    owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(),
        receipt_verifier=lambda receipt_id, semantic, _message:
            (receipt_id, semantic) == (admission["receipt_id"],
                                       admission["semantic_digest"]),
        renderer_sink=state_queue.enqueue)
    assert owner.dispatch_one(message) is True
    import json
    state = json.loads(target.read_text(encoding="utf-8"))
    assert state["current_phrase"] == "Hello"
    assert state["is_speaking"] is False
    assert state["viseme_timeline"] == []
    assert state["metadata"]["transport_message_id"] == message.message_id
    assert state["metadata"]["renderer_effect_proven"] is False
    assert state_queue.accepted_count == 1


def test_dispatch_rejects_non_command_message():
    message, _ = verified_command(kind="acknowledgment")
    owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(),
        receipt_verifier=lambda *_: True, renderer_sink=lambda *_: True)
    assert owner.dispatch_one(message) is False
    assert owner.status().last_failure == "avatar_command_message_required"


def test_dispatch_requires_authority_callbacks_and_bounded_poll_interval():
    with pytest.raises(CompanionBridgeError, match="avatar_command_authority_callbacks_required"):
        WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(), receipt_verifier=None,
            renderer_sink=lambda *_: True)
    with pytest.raises(CompanionBridgeError, match="avatar_command_poll_interval_invalid"):
        WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(), receipt_verifier=lambda *_: True,
            renderer_sink=lambda *_: True, poll_interval_seconds=0)
