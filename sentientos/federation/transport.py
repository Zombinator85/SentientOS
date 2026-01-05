"""Minimal, explicit transport primitives for federation artifacts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, is_dataclass
import base64
import hashlib
import json
import threading
from typing import Callable, Mapping, MutableMapping, Optional, Sequence

from sentientos.federation.handshake_semantics import (
    CompatibilityExplanation,
    CompatibilityResult,
    HandshakeDecision,
    HandshakeRecord,
    SemanticAttestation,
    evaluate_compatibility,
)


def _stable_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _encode_payload(payload: object) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, (bytearray, memoryview)):
        return bytes(payload)
    if hasattr(payload, "to_dict"):
        payload = getattr(payload, "to_dict")()
    if is_dataclass(payload):
        payload = asdict(payload)
    if isinstance(payload, Mapping):
        return _stable_json(dict(payload)).encode("utf-8")
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return json.dumps(list(payload), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decode_payload(payload: bytes) -> object | None:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


class OpaqueTransportPayload:
    __slots__ = ("_payload", "_tag", "_checksum")

    def __init__(self, payload: object, *, tag: str = "opaque") -> None:
        self._payload = _encode_payload(payload)
        self._tag = tag
        self._checksum: Optional[str] = None

    @property
    def tag(self) -> str:
        return self._tag

    @property
    def length(self) -> int:
        return len(self._payload)

    def checksum(self) -> str:
        if self._checksum is None:
            digest = hashlib.sha256(self._payload).hexdigest()
            self._checksum = digest
        return self._checksum

    def decode(self, context: str) -> bytes:
        if not isinstance(context, str) or not context.strip():
            raise ValueError("decode context must be a non-empty string")
        return bytes(self._payload)

    def __repr__(self) -> str:
        short_checksum = self.checksum()[:12]
        return f"OpaqueTransportPayload(len={self.length}, tag={self._tag!r}, checksum={short_checksum})"

    def __str__(self) -> str:
        raise TypeError("OpaqueTransportPayload cannot be stringified; call .decode(context)")

    def __eq__(self, _other: object) -> bool:
        raise TypeError("OpaqueTransportPayload does not support equality checks")

    def __hash__(self) -> int:
        raise TypeError("OpaqueTransportPayload is not hashable")

    def __bytes__(self) -> bytes:
        raise TypeError("OpaqueTransportPayload does not expose raw bytes; call .decode(context)")


@dataclass(frozen=True)
class FederationEnvelope:
    envelope_id: str
    payload_type: str
    payload: OpaqueTransportPayload = field(compare=False, hash=False)
    sender_node_id: str
    protocol_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.payload, OpaqueTransportPayload):
            raise TypeError("payload must be wrapped in OpaqueTransportPayload")

    def to_dict(self) -> MutableMapping[str, object]:
        payload_bytes = self.payload.decode("federation-envelope:serialize")
        return {
            "envelope_id": self.envelope_id,
            "payload_type": self.payload_type,
            "payload": base64.b64encode(payload_bytes).decode("utf-8"),
            "sender_node_id": self.sender_node_id,
            "protocol_version": self.protocol_version,
        }

    def serialize(self) -> str:
        return _stable_json(self.to_dict())


class FederationTransport(ABC):
    @abstractmethod
    def send(self, envelope: FederationEnvelope, destination: object) -> None:
        raise NotImplementedError

    @abstractmethod
    def receive(self, envelope: FederationEnvelope) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class TransportEvent:
    action: str
    envelope: FederationEnvelope


class LocalLoopbackTransport(FederationTransport):
    """In-memory loopback transport for tests and simulation."""

    def __init__(self, *, on_receive: Optional[Callable[[FederationEnvelope], None]] = None) -> None:
        self._inbox: list[FederationEnvelope] = []
        self._events: list[TransportEvent] = []
        self._lock = threading.Lock()
        self._on_receive = on_receive

    @property
    def inbox(self) -> Sequence[FederationEnvelope]:
        with self._lock:
            return tuple(self._inbox)

    @property
    def events(self) -> Sequence[TransportEvent]:
        with self._lock:
            return tuple(self._events)

    def send(self, envelope: FederationEnvelope, destination: object) -> None:
        self._record_event("send", envelope)
        if isinstance(destination, FederationTransport):
            destination.receive(envelope)

    def receive(self, envelope: FederationEnvelope) -> None:
        self._record_event("receive", envelope)
        with self._lock:
            self._inbox.append(envelope)
        if self._on_receive is not None:
            self._on_receive(envelope)

    def _record_event(self, action: str, envelope: FederationEnvelope) -> None:
        with self._lock:
            self._events.append(TransportEvent(action=action, envelope=envelope))


def extract_semantic_attestation(
    envelope: FederationEnvelope,
) -> Optional[SemanticAttestation]:
    if envelope.payload_type != "semantic_attestation":
        return None
    payload = _decode_payload(envelope.payload.decode("federation-envelope:semantic-attestation"))
    if isinstance(payload, Mapping):
        declared = payload.get("declared_capabilities")
        declared_caps = tuple(declared) if declared is not None else None
        return SemanticAttestation(
            node_id=str(payload["node_id"]),
            ontology_hash=str(payload["ontology_hash"]),
            policy_hash=str(payload["policy_hash"]),
            invariant_catalog_hash=str(payload["invariant_catalog_hash"]),
            failure_taxonomy_hash=str(payload["failure_taxonomy_hash"]),
            declared_capabilities=declared_caps,
        )
    return None


def extract_handshake_record(envelope: FederationEnvelope) -> Optional[HandshakeRecord]:
    if envelope.payload_type != "handshake_record":
        return None
    payload = _decode_payload(envelope.payload.decode("federation-envelope:handshake-record"))
    if isinstance(payload, Mapping):
        attestation_payload = payload["attestation"]
        if isinstance(attestation_payload, Mapping):
            declared_caps = attestation_payload.get("declared_capabilities")
            attestation = SemanticAttestation(
                node_id=str(attestation_payload["node_id"]),
                ontology_hash=str(attestation_payload["ontology_hash"]),
                policy_hash=str(attestation_payload["policy_hash"]),
                invariant_catalog_hash=str(attestation_payload["invariant_catalog_hash"]),
                failure_taxonomy_hash=str(attestation_payload["failure_taxonomy_hash"]),
                declared_capabilities=tuple(declared_caps)
                if declared_caps is not None
                else None,
            )
        else:
            attestation = attestation_payload
        compatibility = payload["compatibility"]
        if isinstance(compatibility, str):
            compatibility = CompatibilityResult(compatibility)
        decision = payload["decision"]
        if isinstance(decision, str):
            decision = HandshakeDecision(decision)
        return HandshakeRecord(
            remote_node_id=str(payload["remote_node_id"]),
            attestation=attestation,
            compatibility=compatibility,
            decision=decision,
        )
    return None


def explicitly_evaluate_compatibility(
    local: SemanticAttestation,
    envelope: FederationEnvelope,
) -> Optional[tuple[CompatibilityResult, CompatibilityExplanation]]:
    attestation = extract_semantic_attestation(envelope)
    if attestation is None:
        return None
    return evaluate_compatibility(local, attestation)


def store_handshake_record(
    envelope: FederationEnvelope,
    storage: MutableMapping[str, HandshakeRecord],
) -> bool:
    record = extract_handshake_record(envelope)
    if record is None:
        return False
    storage[record.remote_node_id] = record
    return True
