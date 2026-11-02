"""Authenticated bounded message envelopes for a future Windows/WSL bridge.

This module validates transport messages only. It does not open sockets, grant
authority, execute commands, or turn renderer self-reports into independent
observations. Callers must provide the source key and the expected live source
generation through an independently configured channel.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import socket
import struct
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "sentientos.gaming_companion_bridge_envelope:v1"
MESSAGE_KINDS = frozenset({"observation", "avatar_command", "acknowledgment", "renderer_report", "consequence"})
AVATAR_COMMAND_FIELDS = frozenset({"output_mode", "phrase", "expression", "motion", "mood",
                                   "intensity", "workload_mode", "output_digest", "turn_id"})
MAX_ENVELOPE_BYTES = 16 * 1024
MAX_PAYLOAD_BYTES = 12 * 1024
MAX_CLOCK_SKEW_SECONDS = 30.0
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def send_frame(connection: socket.socket, encoded: bytes) -> None:
    """Write one bounded network-order length-prefixed envelope."""
    if not isinstance(encoded, bytes) or not encoded or len(encoded) > MAX_ENVELOPE_BYTES:
        raise CompanionBridgeError("bridge_envelope_size_invalid")
    connection.sendall(struct.pack("!I", len(encoded)) + encoded)


def read_frame(connection: socket.socket) -> bytes:
    """Read exactly one bounded frame, rejecting EOF and oversized lengths."""
    prefix = _recv_exact(connection, 4)
    size = struct.unpack("!I", prefix)[0]
    if size < 1 or size > MAX_ENVELOPE_BYTES:
        raise CompanionBridgeError("bridge_frame_size_invalid")
    return _recv_exact(connection, size)


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            raise CompanionBridgeError("bridge_frame_truncated")
        chunks.extend(chunk)
    return bytes(chunks)


class CompanionBridgeError(ValueError):
    """A malformed, unauthenticated, stale, or replayed bridge message."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise CompanionBridgeError("bridge_json_invalid") from exc


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise CompanionBridgeError(field + "_invalid")
    return value


def _timestamp(value: Any) -> tuple[str, float]:
    if not isinstance(value, str):
        raise CompanionBridgeError("bridge_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CompanionBridgeError("bridge_timestamp_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CompanionBridgeError("bridge_timestamp_timezone_required")
    return parsed.astimezone(timezone.utc).isoformat(), parsed.timestamp()


def _key_bytes(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise CompanionBridgeError("bridge_key_too_short")
    return key


def _validate_message(kind: str, payload: Mapping[str, Any], admission: Mapping[str, str] | None) -> None:
    if not isinstance(kind, str) or kind not in MESSAGE_KINDS:
        raise CompanionBridgeError("bridge_message_kind_unsupported")
    if not isinstance(payload, Mapping):
        raise CompanionBridgeError("bridge_payload_object_required")
    if kind == "avatar_command":
        if not isinstance(admission, Mapping):
            raise CompanionBridgeError("avatar_command_admission_required")
        if (set(admission) != {"receipt_id", "semantic_digest"}
                or _IDENTIFIER.fullmatch(str(admission.get("receipt_id", ""))) is None
                or _SHA256.fullmatch(str(admission.get("semantic_digest", ""))) is None):
            raise CompanionBridgeError("avatar_command_admission_invalid")
        if payload.get("output_mode") != "chat_response_visual_only":
            raise CompanionBridgeError("avatar_command_scope_invalid")
        if set(payload) - AVATAR_COMMAND_FIELDS:
            raise CompanionBridgeError("avatar_command_field_unsupported")
        phrase = payload.get("phrase", "")
        if not isinstance(phrase, str) or len(phrase) > 2048:
            raise CompanionBridgeError("avatar_command_phrase_invalid")
        for field in ("expression", "motion", "mood"):
            value = payload.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > 128):
                raise CompanionBridgeError("avatar_command_field_invalid:" + field)
        intensity = payload.get("intensity")
        if intensity is not None:
            try:
                valid_intensity = (not isinstance(intensity, bool)
                    and isinstance(intensity, (int, float))
                    and math.isfinite(float(intensity)) and 0 <= intensity <= 1)
            except (OverflowError, TypeError, ValueError):
                valid_intensity = False
            if not valid_intensity:
                raise CompanionBridgeError("avatar_command_field_invalid:intensity")
        workload_mode = payload.get("workload_mode")
        if workload_mode is not None and (
                not isinstance(workload_mode, str) or workload_mode not in {"normal", "gaming"}):
            raise CompanionBridgeError("avatar_command_field_invalid:workload_mode")
        output_digest = payload.get("output_digest")
        if output_digest is not None and (
                not isinstance(output_digest, str) or _SHA256.fullmatch(output_digest) is None):
            raise CompanionBridgeError("avatar_command_field_invalid:output_digest")
        if payload.get("turn_id") is not None:
            _identifier(payload["turn_id"], "avatar_command_turn_id")
    elif admission is not None:
        raise CompanionBridgeError("bridge_admission_unexpected")
    if kind == "acknowledgment":
        try:
            _identifier(payload.get("message_id"), "bridge_acknowledgment_reference")
        except CompanionBridgeError as exc:
            raise CompanionBridgeError("bridge_acknowledgment_reference_required") from exc


def encode_message(*, kind: str, source_id: str, session_id: str,
                   generation_id: str, sequence: int, payload: Mapping[str, Any],
                   key: bytes, created_at: str | None = None,
                   admission: Mapping[str, str] | None = None) -> bytes:
    """Create an HMAC-bound envelope; the key is supplied, never persisted here."""
    _key_bytes(key)
    source_id = _identifier(source_id, "bridge_source_id")
    session_id = _identifier(session_id, "bridge_session_id")
    generation_id = _identifier(generation_id, "bridge_generation_id")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise CompanionBridgeError("bridge_sequence_invalid")
    stamp, _ = _timestamp(created_at or datetime.now(timezone.utc).isoformat())
    _validate_message(kind, payload, admission)
    payload_bytes = _canonical(payload)
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        raise CompanionBridgeError("bridge_payload_size_exceeded")
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "source_id": source_id,
        "session_id": session_id,
        "generation_id": generation_id,
        "sequence": sequence,
        "created_at": stamp,
        "payload": dict(payload),
        "payload_digest": hashlib.sha256(payload_bytes).hexdigest(),
        "admission": dict(admission) if admission is not None else None,
    }
    body_bytes = _canonical(body)
    envelope = {**body, "signature": hmac.new(key, body_bytes, hashlib.sha256).hexdigest()}
    encoded = _canonical(envelope)
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise CompanionBridgeError("bridge_envelope_size_exceeded")
    return encoded


@dataclass(frozen=True, slots=True)
class VerifiedBridgeMessage:
    message_id: str
    kind: str
    source_id: str
    session_id: str
    generation_id: str
    sequence: int
    created_at: str
    payload: Mapping[str, Any]
    admission: Mapping[str, str] | None


class CompanionBridgeReceiver:
    """Verify messages against explicit source keys and current generations."""

    def __init__(self, *, source_keys: Mapping[str, bytes],
                 expected_generations: Mapping[str, str],
                 clock: Any = None, max_clock_skew_seconds: float = MAX_CLOCK_SKEW_SECONDS) -> None:
        if not isinstance(source_keys, Mapping) or not source_keys:
            raise CompanionBridgeError("bridge_source_keys_required")
        if not isinstance(expected_generations, Mapping) or set(source_keys) != set(expected_generations):
            raise CompanionBridgeError("bridge_expected_generations_mismatch")
        self._keys = {str(source): _key_bytes(key) for source, key in source_keys.items()}
        self._generations = {
            str(source): _identifier(generation, "bridge_generation_id")
            for source, generation in expected_generations.items()
        }
        try:
            valid_skew = (not isinstance(max_clock_skew_seconds, bool)
                and isinstance(max_clock_skew_seconds, (float, int))
                and math.isfinite(float(max_clock_skew_seconds)) and max_clock_skew_seconds > 0)
        except (OverflowError, TypeError, ValueError):
            valid_skew = False
        if not valid_skew:
            raise CompanionBridgeError("bridge_clock_skew_invalid")
        self._max_skew = float(max_clock_skew_seconds)
        self._clock = clock or (lambda: datetime.now(timezone.utc).timestamp())
        self._high_water: dict[tuple[str, str, str], int] = {}
        self._sequence_lock = threading.Lock()

    def accept(self, encoded: bytes) -> VerifiedBridgeMessage:
        if not isinstance(encoded, bytes) or not encoded or len(encoded) > MAX_ENVELOPE_BYTES:
            raise CompanionBridgeError("bridge_envelope_size_invalid")
        try:
            envelope = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise CompanionBridgeError("bridge_envelope_json_invalid") from exc
        if not isinstance(envelope, dict):
            raise CompanionBridgeError("bridge_envelope_object_required")
        if _canonical(envelope) != encoded:
            raise CompanionBridgeError("bridge_envelope_noncanonical")
        required = {"schema_version", "kind", "source_id", "session_id", "generation_id",
                    "sequence", "created_at", "payload", "payload_digest", "admission", "signature"}
        if set(envelope) != required or envelope.get("schema_version") != SCHEMA_VERSION:
            raise CompanionBridgeError("bridge_envelope_schema_invalid")
        source_id = _identifier(envelope["source_id"], "bridge_source_id")
        session_id = _identifier(envelope["session_id"], "bridge_session_id")
        generation_id = _identifier(envelope["generation_id"], "bridge_generation_id")
        key = self._keys.get(source_id)
        if key is None:
            raise CompanionBridgeError("bridge_source_untrusted")
        if self._generations[source_id] != generation_id:
            raise CompanionBridgeError("bridge_generation_stale")
        sequence = envelope["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise CompanionBridgeError("bridge_sequence_invalid")
        stamp, timestamp_seconds = _timestamp(envelope["created_at"])
        try:
            now = float(self._clock())
        except (TypeError, ValueError, OverflowError) as exc:
            raise CompanionBridgeError("bridge_receiver_clock_invalid") from exc
        if not math.isfinite(now):
            raise CompanionBridgeError("bridge_receiver_clock_invalid")
        if abs(now - timestamp_seconds) > self._max_skew:
            raise CompanionBridgeError("bridge_message_stale")
        payload = envelope["payload"]
        if not isinstance(payload, dict):
            raise CompanionBridgeError("bridge_payload_object_required")
        payload_bytes = _canonical(payload)
        if len(payload_bytes) > MAX_PAYLOAD_BYTES:
            raise CompanionBridgeError("bridge_payload_size_exceeded")
        payload_digest = hashlib.sha256(payload_bytes).hexdigest()
        if not hmac.compare_digest(str(envelope["payload_digest"]), payload_digest):
            raise CompanionBridgeError("bridge_payload_digest_mismatch")
        signature = envelope["signature"]
        if not isinstance(signature, str) or _SHA256.fullmatch(signature) is None:
            raise CompanionBridgeError("bridge_signature_invalid")
        body = {key_name: value for key_name, value in envelope.items() if key_name != "signature"}
        expected = hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise CompanionBridgeError("bridge_authentication_failed")
        admission = envelope["admission"]
        if admission is not None and not isinstance(admission, dict):
            raise CompanionBridgeError("bridge_admission_invalid")
        kind = envelope["kind"]
        _validate_message(kind, payload, admission)
        cursor = (source_id, session_id, generation_id)
        with self._sequence_lock:
            if sequence <= self._high_water.get(cursor, 0):
                raise CompanionBridgeError("bridge_replay_or_out_of_order")
            self._high_water[cursor] = sequence
        message_id = hashlib.sha256(_canonical(body)).hexdigest()
        return VerifiedBridgeMessage(message_id, kind, source_id, session_id,
            generation_id, sequence, stamp, dict(payload), dict(admission) if admission else None)
