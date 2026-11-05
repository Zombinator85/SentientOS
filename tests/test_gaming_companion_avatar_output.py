from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.no_legacy_skip

from avatar_state import AvatarStateEmitter
from godot_avatar_receiver import AvatarStateForwarder
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
from control_plane.task_admission import AdmissionResponse
from tests.test_gaming_companion_tls_transport import _certificate_bundle
from sentientos.chat_avatar_output import ChatAvatarOutputController


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


class _AvatarAdmission:
    def __call__(self, **request):
        record = AuthorizationRecord.create(
            request_type=request["request_type"], requester_id=str(request["requester_id"]),
            intent_hash=str(request["intent_hash"]), context_hash=str(request["context_hash"]),
            policy_version=str(request["policy_version"]), decision=Decision.ALLOW,
            reason=ReasonCode.OK, metadata=request.get("metadata"))
        return AdmissionResponse(Decision.ALLOW, ReasonCode.OK, record)


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


def test_remote_avatar_emitter_uses_authorized_chat_session_and_closes_phrase():
    key = b"r" * 32
    receiver = CompanionBridgeReceiver(source_keys={"sentientos-core": key},
        expected_generations={"sentientos-core": "core-generation-1"})
    client = _Client(receiver)
    sender = MutualTLSAvatarCommandSender(client=client, source_id="sentientos-core",
        session_id=None, generation_id="core-generation-1", source_key=key,
        admission_receipt_builder=lambda _authorization: {
            "receipt_id": "remote-admission", "semantic_digest": "f" * 64})
    output = ChatAvatarOutputController(BridgeChatAvatarOutputEmitter(sender),
        admission_provider=_AvatarAdmission())
    try:
        assert output.set_enabled("actual-chat-session", True)["enabled"] is True
        result = output.publish_response(session_id="actual-chat-session", turn_id="turn-7",
            text="Hello from the governed chat owner", output_digest="a" * 64,
            workload_mode="gaming")
        assert result["status"] == "emitted"
        response_message = client.sent[-1]
        assert response_message.session_id == "actual-chat-session"
        assert response_message.payload["workload_mode"] == "gaming"
        timing = output.publish_speech_timing({"session_id": "actual-chat-session",
            "turn_id": "turn-7", "event": "speech_interrupted"})
        assert timing["status"] == "emitted"
        assert client.sent[-1].session_id == "actual-chat-session"
        assert client.sent[-1].payload["speech_timing"]["event"] == "speech_interrupted"
    finally:
        output.close()
        sender.close()
    assert client.sent[-1].session_id == "actual-chat-session"
    assert client.sent[-1].payload["phrase"] == ""


def test_remote_avatar_emitter_rejects_session_metadata_outside_authorization():
    key = b"s" * 32
    receiver = CompanionBridgeReceiver(source_keys={"sentientos-core": key},
        expected_generations={"sentientos-core": "core-generation-1"})
    sender = MutualTLSAvatarCommandSender(client=_Client(receiver),
        source_id="sentientos-core", session_id=None,
        generation_id="core-generation-1", source_key=key,
        admission_receipt_builder=lambda _authorization: {
            "receipt_id": "remote-admission", "semantic_digest": "f" * 64})
    emitter = BridgeChatAvatarOutputEmitter(sender)
    authorized_for = AuthorizationRecord.create(
        request_type=RequestType.AVATAR_EMISSION, requester_id="bridge",
        intent_hash="a" * 64, context_hash="b" * 64, policy_version="test",
        decision=Decision.ALLOW, reason=ReasonCode.OK,
        metadata={"session_id": "authorized-session"})
    try:
        with pytest.raises(CompanionBridgeError,
                           match="avatar_command_session_authorization_mismatch"):
            emitter.emit_display_text("cross-session", authorization=authorized_for,
                metadata={"session_id": "other-session", "turn_id": "turn-1",
                    "output_digest": "c" * 64})
    finally:
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
    state_queue = WindowsGodotAvatarStateQueue(
        state_emitter=AvatarStateEmitter(tmp_path / "avatar_state.json"))
    dispatcher = WindowsEdgeAvatarCommandDispatchOwner(runtime=runtime,
        receipt_verifier=lambda receipt_id, digest, _message:
            (receipt_id, digest) == (receipt["receipt_id"], receipt["semantic_digest"]),
        renderer_sink=state_queue.enqueue)
    try:
        emitter = BridgeChatAvatarOutputEmitter(sender)
        result = emitter.emit_phrase("Hello over mTLS",
            authorization=_authorization(),
            metadata={"session_id": "session-1", "turn_id": "turn-2",
                "workload_mode": "gaming",
                "output_digest": "c" * 64, "speech_timing": {
                    "schema": "sentientos.local_speech_timing:v1",
                    "event": "word_started", "session_id": "session-1",
                    "turn_id": "turn-2", "timing_quality": "backend_word_start",
                    "word_index": 1, "char_start": 0, "char_length": 5}})
        message = runtime.receive(timeout=1.0)
        assert result["status"] == "sent"
        assert message.kind == "avatar_command"
        assert dispatcher.dispatch_one(message) is True
        import json
        state = json.loads((tmp_path / "avatar_state.json").read_text(encoding="utf-8"))
        assert state["current_phrase"] == "Hello over mTLS"
        assert state["metadata"]["speech_timing"]["event"] == "word_started"
        assert state["metadata"]["speech_timing"]["char_start"] == 0
        assert state["metadata"]["session_id"] == "session-1"
        assert state["metadata"]["output_mode"] == "chat_response_visual_only"
        assert state["workload_mode"] == "gaming"
        forwarded = AvatarStateForwarder(tmp_path / "avatar_state.json")._read_state()
        assert forwarded is not None
        assert forwarded["workload_mode"] == "gaming"
        assert forwarded["metadata"] == {
            "session_id": "session-1", "turn_id": "turn-2",
            "output_digest": "c" * 64,
            "output_mode": "chat_response_visual_only",
        }
        assert dispatcher.status().renderer_effect_proven is False
    finally:
        sender.close()
        runtime.close()


def test_speech_timing_on_reverse_route_is_closed_and_bound_to_command_session_turn():
    key = b"k" * 32
    payload = {"output_mode": "chat_response_visual_only", "phrase": "hello",
        "expression": "rest", "motion": "nod", "mood": "calm",
        "intensity": 0.25, "output_digest": "a" * 64, "turn_id": "turn-1",
        "speech_timing": {"schema": "sentientos.local_speech_timing:v1",
            "event": "speech_started", "session_id": "other-session",
            "turn_id": "turn-1", "timing_quality": "controller_boundary"}}
    with pytest.raises(CompanionBridgeError,
                       match="avatar_command_speech_timing_binding_invalid"):
        encode_message(kind="avatar_command", source_id="sentientos-core",
            session_id="session-1", generation_id="core-generation-1", sequence=1,
            payload=payload, key=key,
            admission={"receipt_id": "admission-1", "semantic_digest": "b" * 64})


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


def test_dispatch_rejects_reused_admission_receipt_without_second_queue_delivery():
    message, admission = verified_command()
    replay = replace(message, message_id="replayed-message", sequence=2)
    verified = []
    delivered = []
    owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(),
        receipt_verifier=lambda receipt_id, digest, _message:
            verified.append(receipt_id) is None
            and (receipt_id, digest) ==
                (admission["receipt_id"], admission["semantic_digest"]),
        renderer_sink=lambda payload, _message:
            delivered.append(dict(payload)) is None)

    assert owner.dispatch_one(message) is True
    assert owner.dispatch_one(replay) is False
    assert verified == [admission["receipt_id"]]
    assert delivered == [dict(message.payload)]
    assert owner.status().last_failure == "avatar_command_admission_receipt_replayed"


def test_dispatch_fails_closed_when_admission_receipt_window_is_full():
    message, admission = verified_command()
    later_admission = {**admission, "receipt_id": "admission-2"}
    later_message = replace(message, message_id="second-message", sequence=2,
                            admission=later_admission)
    verified = []
    delivered = []
    owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(),
        receipt_verifier=lambda receipt_id, _digest, _message:
            verified.append(receipt_id) is None,
        renderer_sink=lambda payload, _message:
            delivered.append(dict(payload)) is None,
        max_consumed_receipts=1)

    assert owner.dispatch_one(message) is True
    assert owner.dispatch_one(later_message) is False
    assert verified == [admission["receipt_id"]]
    assert delivered == [dict(message.payload)]
    assert owner.status().last_failure == "avatar_command_receipt_window_exhausted"


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


def test_dispatch_outcome_observer_records_rejection_without_response_text():
    message, _admission = verified_command()
    outcomes = []
    owner = WindowsEdgeAvatarCommandDispatchOwner(
        runtime=_Runtime(), receipt_verifier=lambda *_: True,
        renderer_sink=lambda *_: False,
        dispatch_outcome_observer=outcomes.append,
    )

    assert owner.dispatch_one(message) is False
    assert outcomes == [{
        "schema_version": "sentientos.avatar_dispatch_outcome:v1",
        "message_id": message.message_id,
        "session_id": "session-1",
        "kind": "avatar_command",
        "accepted": False,
        "renderer_effect_proven": False,
        "turn_id": "turn-1",
        "failure_code": "avatar_command_renderer_queue_rejected",
    }]
    assert "phrase" not in outcomes[0]


def test_dispatch_outcome_observer_records_success_without_claiming_render():
    message, admission = verified_command()
    outcomes = []
    owner = WindowsEdgeAvatarCommandDispatchOwner(
        runtime=_Runtime(),
        receipt_verifier=lambda receipt_id, digest, _message:
            (receipt_id, digest) == (admission["receipt_id"], admission["semantic_digest"]),
        renderer_sink=lambda *_: True,
        dispatch_outcome_observer=outcomes.append,
    )

    assert owner.dispatch_one(message) is True
    assert outcomes == [{
        "schema_version": "sentientos.avatar_dispatch_outcome:v1",
        "message_id": message.message_id,
        "session_id": "session-1",
        "kind": "avatar_command",
        "accepted": True,
        "renderer_effect_proven": False,
        "turn_id": "turn-1",
    }]


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

def test_uncertain_ack_retry_with_same_admission_reaches_renderer_once():
    message, admission = verified_command()
    bridge_receiver = CompanionBridgeReceiver(
        source_keys={"sentientos-core": b"k" * 32},
        expected_generations={"sentientos-core": "core-generation-1"})
    delivered = []
    owner = WindowsEdgeAvatarCommandDispatchOwner(runtime=_Runtime(),
        receipt_verifier=lambda receipt_id, digest, _message:
            (receipt_id, digest) ==
                (admission["receipt_id"], admission["semantic_digest"]),
        renderer_sink=lambda payload, _message:
            delivered.append(dict(payload)) is None)

    class _IndeterminateAckClient(CompanionBridgeMutualTLSClient):
        def __init__(self):
            self.dispatch_results = []

        def send(self, encoded):
            received = bridge_receiver.accept(encoded)
            self.dispatch_results.append(owner.dispatch_one(received))
            if len(self.dispatch_results) == 1:
                raise CompanionBridgeError("test_transport_ack_uncertain")
            return VerifiedBridgeMessage(
                "ack-" + str(len(self.dispatch_results)), "acknowledgment",
                "sentientos-edge", received.session_id, "edge-generation-1",
                len(self.dispatch_results), received.created_at,
                {"message_id": received.message_id, "disposition": "accepted"},
                None,
            )

    client = _IndeterminateAckClient()
    sender = MutualTLSAvatarCommandSender(
        client=client, source_id="sentientos-core", session_id="session-1",
        generation_id="core-generation-1", source_key=b"k" * 32,
        admission_receipt_builder=lambda _authorization: admission)
    try:
        with pytest.raises(CompanionBridgeError,
                           match="test_transport_ack_uncertain"):
            sender.send_command(message.payload, _authorization())
        acknowledgment = sender.send_command(message.payload, _authorization())
        assert acknowledgment.kind == "acknowledgment"
        assert client.dispatch_results == [True, False]
        assert len(delivered) == 1
        assert owner.status().last_failure == (
            "avatar_command_admission_receipt_replayed")
    finally:
        sender.close()


def test_sqlite_receipt_replay_guard_survives_dispatcher_process_restart(tmp_path):
    import subprocess
    import sys

    from sentientos.gaming_companion_receipt_replay import (
        SQLiteAdmissionReceiptReplayGuard,
    )

    message, _admission = verified_command()
    replay = replace(message, message_id="after-restart", sequence=2)
    database = tmp_path / "receipt-replay.sqlite3"
    delivered = []
    first = WindowsEdgeAvatarCommandDispatchOwner(
        runtime=_Runtime(), receipt_verifier=lambda *_: True,
        renderer_sink=lambda payload, _message: delivered.append(dict(payload)) is None,
        receipt_replay_guard=SQLiteAdmissionReceiptReplayGuard(database),
    )
    assert first.dispatch_one(message) is True
    assert delivered == [dict(message.payload)]

    child = subprocess.run(
        [sys.executable, "-c", """
import sys
from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_receipt_replay import SQLiteAdmissionReceiptReplayGuard

guard = SQLiteAdmissionReceiptReplayGuard(sys.argv[1])
try:
    guard.preflight('admission-1')
except CompanionBridgeError as exc:
    print(exc.args[0])
    raise SystemExit(0 if exc.args[0] == 'avatar_command_admission_receipt_replayed' else 2)
raise SystemExit(1)
""", str(database)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert child.returncode == 0, child.stdout + child.stderr

    verifier_calls = []
    second = WindowsEdgeAvatarCommandDispatchOwner(
        runtime=_Runtime(),
        receipt_verifier=lambda *args: verifier_calls.append(args) is None,
        renderer_sink=lambda payload, _message: delivered.append(dict(payload)) is None,
        receipt_replay_guard=SQLiteAdmissionReceiptReplayGuard(database),
    )
    assert second.dispatch_one(replay) is False
    assert verifier_calls == []
    assert delivered == [dict(message.payload)]
    assert second.status().last_failure == "avatar_command_admission_receipt_replayed"


def test_sqlite_receipt_replay_guard_claim_is_atomic_across_processes(tmp_path):
    import subprocess
    import sys

    from sentientos.gaming_companion_receipt_replay import (
        SQLiteAdmissionReceiptReplayGuard,
    )

    database = tmp_path / "receipt-race.sqlite3"
    gate = tmp_path / "start-claims"
    SQLiteAdmissionReceiptReplayGuard(database)
    child = """
import sys
import time
from pathlib import Path
from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_receipt_replay import SQLiteAdmissionReceiptReplayGuard

deadline = time.monotonic() + 5
while not Path(sys.argv[2]).exists() and time.monotonic() < deadline:
    time.sleep(0.01)
if not Path(sys.argv[2]).exists():
    raise SystemExit(3)
try:
    SQLiteAdmissionReceiptReplayGuard(sys.argv[1]).consume('one-shared-receipt')
except CompanionBridgeError as exc:
    if exc.args[0] != 'avatar_command_admission_receipt_replayed':
        raise
    print('replayed')
else:
    print('accepted')
"""
    processes = []
    try:
        for _ in range(2):
            processes.append(subprocess.Popen(
                [sys.executable, "-c", child, str(database), str(gate)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ))
        gate.touch()
        outcomes = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stdout + stderr
            outcomes.append(stdout.strip())
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)

    assert sorted(outcomes) == ["accepted", "replayed"]


def test_sqlite_receipt_replay_guard_fails_closed_at_capacity(tmp_path):
    from sentientos.gaming_companion_bridge import CompanionBridgeError
    from sentientos.gaming_companion_receipt_replay import (
        SQLiteAdmissionReceiptReplayGuard,
    )

    guard = SQLiteAdmissionReceiptReplayGuard(
        tmp_path / "bounded-receipts.sqlite3", max_receipts=1)
    guard.consume("first")
    with pytest.raises(CompanionBridgeError,
                       match="avatar_command_receipt_window_exhausted"):
        guard.preflight("second")
    with pytest.raises(CompanionBridgeError,
                       match="avatar_command_receipt_window_exhausted"):
        guard.consume("second")


def test_dispatcher_routes_only_authenticated_additional_message_kinds():
    calls = []
    dispatcher = WindowsEdgeAvatarCommandDispatchOwner(
        runtime=_Runtime(), receipt_verifier=lambda *_: True,
        renderer_sink=lambda *_: True,
        additional_message_handlers={
            "screen_capture_request": lambda message:
                calls.append(message.payload["capture_request_id"]) is None})
    request = VerifiedBridgeMessage(
        "1" * 64, "screen_capture_request", "wsl-screen-request-dev",
        "wsl-screen-request-dev", "wsl-screen-request-dev-1", 1,
        datetime.now(timezone.utc).isoformat(),
        {"capture_request_id": "0123456789abcdef0123456789abcdef"}, None)
    assert dispatcher.dispatch_one(request) is True
    assert calls == ["0123456789abcdef0123456789abcdef"]
    assert dispatcher.status().accepted == 1
    assert dispatcher.status().rejected == 0
