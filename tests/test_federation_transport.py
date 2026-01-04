import copy
import json

import pytest

from sentientos.federation.handshake_semantics import (
    CompatibilityResult,
    HandshakeDecision,
    HandshakeRecord,
    SemanticAttestation,
)
from sentientos.federation.transport import (
    FederationEnvelope,
    LocalLoopbackTransport,
    explicitly_evaluate_compatibility,
)


def _sample_attestation(node_id: str) -> SemanticAttestation:
    return SemanticAttestation(
        node_id=node_id,
        ontology_hash="onto",
        policy_hash="policy",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
        declared_capabilities=("write", "read"),
    )


def test_envelope_serialization_is_deterministic() -> None:
    payload = {"b": 2, "a": 1}
    envelope = FederationEnvelope(
        envelope_id="env-1",
        payload_type="semantic_attestation",
        payload=payload,
        sender_node_id="node-a",
        protocol_version="v0",
    )
    first = envelope.serialize()
    second = envelope.serialize()
    assert first == second
    assert json.loads(first) == json.loads(second)


def test_transport_does_not_mutate_payloads() -> None:
    payload = {"capabilities": ["read", "write"], "meta": {"x": 1}}
    payload_snapshot = copy.deepcopy(payload)
    sender = LocalLoopbackTransport()
    receiver = LocalLoopbackTransport()
    envelope = FederationEnvelope(
        envelope_id="env-2",
        payload_type="semantic_attestation",
        payload=payload,
        sender_node_id="node-a",
        protocol_version="v0",
    )
    sender.send(envelope, receiver)
    assert payload == payload_snapshot
    assert receiver.inbox[0].payload == payload_snapshot


def test_no_implicit_compatibility_evaluation(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _record(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "sentientos.federation.transport.evaluate_compatibility", _record
    )
    transport = LocalLoopbackTransport()
    envelope = FederationEnvelope(
        envelope_id="env-3",
        payload_type="semantic_attestation",
        payload=_sample_attestation("node-a"),
        sender_node_id="node-a",
        protocol_version="v0",
    )
    transport.receive(envelope)
    assert called is False


def test_loopback_transport_delivers_exactly_once() -> None:
    sender = LocalLoopbackTransport()
    receiver = LocalLoopbackTransport()
    envelope = FederationEnvelope(
        envelope_id="env-4",
        payload_type="semantic_attestation",
        payload=_sample_attestation("node-a"),
        sender_node_id="node-a",
        protocol_version="v0",
    )
    sender.send(envelope, receiver)
    assert len(receiver.inbox) == 1
    assert receiver.inbox[0] is envelope


def test_receive_causes_no_automatic_action() -> None:
    transport = LocalLoopbackTransport()
    handshake = HandshakeRecord(
        remote_node_id="node-b",
        attestation=_sample_attestation("node-b"),
        compatibility=CompatibilityResult.COMPATIBLE,
        decision=HandshakeDecision.ACCEPT,
    )
    envelope = FederationEnvelope(
        envelope_id="env-5",
        payload_type="handshake_record",
        payload=handshake,
        sender_node_id="node-b",
        protocol_version="v0",
    )
    transport.receive(envelope)
    assert transport.inbox == (envelope,)


def test_explicit_compatibility_evaluation_is_opt_in() -> None:
    local = _sample_attestation("node-local")
    remote = _sample_attestation("node-remote")
    envelope = FederationEnvelope(
        envelope_id="env-6",
        payload_type="semantic_attestation",
        payload=remote,
        sender_node_id="node-remote",
        protocol_version="v0",
    )
    result = explicitly_evaluate_compatibility(local, envelope)
    assert result is not None
    assert result[0] is CompatibilityResult.COMPATIBLE
