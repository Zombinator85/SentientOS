from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from control_plane import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from sentientos.gaming_companion_avatar_output import (
    BridgeChatAvatarOutputEmitter,
    MutualTLSAvatarCommandSender,
    WindowsEdgeAvatarCommandDispatchOwner,
)
from sentientos.gaming_companion_bridge import CompanionBridgeReceiver, encode_message
from sentientos.gaming_companion_tls_transport import (
    CompanionBridgeMutualTLSClient,
    CompanionBridgeMutualTLSRuntime,
)
from tests.test_gaming_companion_tls_transport import _certificate_bundle

pytestmark = pytest.mark.no_legacy_skip


def test_windows_edge_and_wsl_core_exchange_observations_and_governed_avatar_output(
        tmp_path: Path) -> None:
    """Exercise both real mTLS directions and receipt-gated edge dispatch."""
    server_context, client_context, peer_certificate_digest = _certificate_bundle(tmp_path)
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding

    server_certificate = x509.load_pem_x509_certificate((tmp_path / "server.pem").read_bytes())
    server_pin = hashlib.sha256(server_certificate.public_bytes(Encoding.DER)).hexdigest()

    observation_key = b"windows-edge-observation-key-material-32-bytes"
    core_ack_key = b"wsl-core-observation-ack-key-material-32-bytes"
    avatar_key = b"wsl-core-avatar-output-key-material-32-bytes"
    edge_ack_key = b"windows-edge-avatar-ack-key-material-32-bytes"

    core = CompanionBridgeMutualTLSRuntime(
        bind_address="127.0.0.1", port=0, tls_context=server_context,
        expected_peer_certificate_sha256=peer_certificate_digest,
        receiver=CompanionBridgeReceiver(
            source_keys={"windows-edge": observation_key},
            expected_generations={"windows-edge": "edge-observation-generation-1"}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="core-observation-generation-1",
        acknowledgment_key=core_ack_key,
    )
    edge = CompanionBridgeMutualTLSRuntime(
        bind_address="127.0.0.1", port=0, tls_context=server_context,
        expected_peer_certificate_sha256=peer_certificate_digest,
        receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": avatar_key},
            expected_generations={"wsl-core": "core-avatar-generation-1"}),
        acknowledgment_source_id="windows-edge",
        acknowledgment_generation_id="edge-avatar-generation-1",
        acknowledgment_key=edge_ack_key,
    )

    delivered: list[dict[str, object]] = []
    admission = {"receipt_id": "operator-admission-fixture",
        "semantic_digest": "a" * 64}
    dispatcher = WindowsEdgeAvatarCommandDispatchOwner(
        runtime=edge,
        receipt_verifier=lambda receipt_id, digest, _message:
            (receipt_id, digest) == (admission["receipt_id"], admission["semantic_digest"]),
        renderer_sink=lambda payload, _message: delivered.append(dict(payload)) is None,
        poll_interval_seconds=0.05,
    )

    core_port = core.start()
    edge_port = edge.start()
    observation_client = CompanionBridgeMutualTLSClient(
        address="127.0.0.1", port=core_port, server_hostname="127.0.0.1",
        tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": core_ack_key},
            expected_generations={"wsl-core": "core-observation-generation-1"}),
        expected_server_certificate_sha256=server_pin,
    )
    avatar_client = CompanionBridgeMutualTLSClient(
        address="127.0.0.1", port=edge_port, server_hostname="127.0.0.1",
        tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"windows-edge": edge_ack_key},
            expected_generations={"windows-edge": "edge-avatar-generation-1"}),
        expected_server_certificate_sha256=server_pin,
    )
    sender = MutualTLSAvatarCommandSender(
        client=avatar_client, source_id="wsl-core", session_id="chat-session-1",
        generation_id="core-avatar-generation-1", source_key=avatar_key,
        admission_receipt_builder=lambda _authorization: admission,
    )

    try:
        observation = encode_message(
            kind="observation", source_id="windows-edge",
            session_id="edge-session-1", generation_id="edge-observation-generation-1",
            sequence=1,
            payload={"schema_version": "sentientos.game_performance_observation:v1",
                "frame_time_p95_ms": 23.4, "process_cpu_percent": 17.0},
            key=observation_key,
        )
        observation_ack = observation_client.send(observation)
        received_observation = core.receive(timeout=1.0)
        assert observation_ack.payload["disposition"] == "accepted"
        assert received_observation.source_id == "windows-edge"
        assert received_observation.payload["frame_time_p95_ms"] == 23.4

        authorization = AuthorizationRecord.create(
            request_type=RequestType.AVATAR_EMISSION, requester_id="chat-session-1",
            intent_hash="b" * 64, context_hash="c" * 64, policy_version="fixture-v1",
            decision=Decision.ALLOW, reason=ReasonCode.OK,
            metadata={"session_id": "chat-session-1", "operator_approved": True},
        )
        result = BridgeChatAvatarOutputEmitter(sender).emit_display_text(
            "I see that frame pacing dipped; I can wait while you play.",
            authorization=authorization,
            metadata={"session_id": "chat-session-1", "turn_id": "turn-1",
                "output_digest": "d" * 64, "workload_mode": "gaming"},
        )
        received_command = edge.receive(timeout=1.0)
        assert result["status"] == "sent"
        assert received_command.source_id == "wsl-core"
        assert received_command.session_id == "chat-session-1"
        assert dispatcher.dispatch_one(received_command) is True
        assert delivered[0]["phrase"].startswith("I see that frame pacing dipped")
        assert delivered[0]["turn_id"] == "turn-1"
        assert dispatcher.status().renderer_effect_proven is False
    finally:
        sender.close()
        dispatcher.close()
        core.close()
        edge.close()
