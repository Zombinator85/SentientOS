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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "sentientos.gaming_companion_bridge_envelope:v1"
MESSAGE_KINDS = frozenset({
    "observation", "avatar_command", "acknowledgment", "renderer_report",
    "consequence", "screen_capture_request", "screen_observation_failure",
    "avatar_consequence_request",
})
SCREEN_CAPTURE_REQUEST_FIELDS = frozenset({"capture_request_id"})
CONSEQUENCE_OBSERVATION_SCHEMA = "sentientos.bridge_consequence_observation:v1"
CONSEQUENCE_OBSERVATION_SCHEMA_V2 = "sentientos.bridge_consequence_observation:v2"
CONSEQUENCE_OBSERVATION_FIELDS = frozenset({
    "schema_version", "expectation_id", "expectation_digest", "handoff_id",
    "handoff_digest", "renderer_report_id", "renderer_report_digest",
    "correlation_id", "body_generation", "observed", "observed_at",
    "confidence", "quality",
})
AVATAR_CONSEQUENCE_REQUEST_SCHEMA = "sentientos.avatar_consequence_measurement_request:v1"
AVATAR_CONSEQUENCE_REQUEST_FIELDS = frozenset({
    "schema_version", "capture_request_id", "expectation_id", "expectation_digest",
    "handoff_id", "handoff_digest", "renderer_report_id", "renderer_report_digest",
    "correlation_id", "body_generation",
})
CONSEQUENCE_CAPTURE_PROVENANCE_FIELDS = frozenset({
    "schema_version", "capture_digest", "process_name_digest", "consent_id_digest",
    "capture_scope", "raw_frame_retained",
})
CONSEQUENCE_CAPTURE_SEQUENCE_PROVENANCE_FIELDS = frozenset(
    CONSEQUENCE_CAPTURE_PROVENANCE_FIELDS | {
        "capture_sequence_digest", "sample_capture_digests",
        "sample_captured_at", "sample_offsets_seconds",
    })
AVATAR_COMMAND_FIELDS = frozenset({"output_mode", "phrase", "expression", "motion", "mood",
                                   "intensity", "workload_mode", "output_digest", "turn_id",
                                   "speech_timing", "consequence_expectation_id",
                                   "consequence_expectation_digest", "consequence_handoff_id",
                                   "consequence_handoff_digest", "consequence_correlation_id"})
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


def _validate_message(kind: str, payload: Mapping[str, Any], admission: Mapping[str, str] | None,
                      session_id: str | None = None) -> None:
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
        speech_timing = payload.get("speech_timing")
        if speech_timing is not None:
            if not isinstance(speech_timing, Mapping):
                raise CompanionBridgeError("avatar_command_speech_timing_invalid")
            timing_fields = {"schema", "event", "session_id", "turn_id", "timing_quality"}
            event = speech_timing.get("event")
            if event not in {"speech_started", "word_started", "speech_finished",
                             "speech_interrupted", "speech_failed"}:
                raise CompanionBridgeError("avatar_command_speech_timing_invalid")
            if event == "word_started":
                timing_fields |= {"word_index", "char_start", "char_length"}
            timing_fields |= {name for name in ("elapsed_seconds", "started_at")
                              if name in speech_timing}
            if set(speech_timing) != timing_fields:
                raise CompanionBridgeError("avatar_command_speech_timing_invalid")
            if (speech_timing.get("schema") != "sentientos.local_speech_timing:v1"
                    or speech_timing.get("timing_quality") != (
                        "backend_word_start" if event == "word_started"
                        else "controller_boundary")):
                raise CompanionBridgeError("avatar_command_speech_timing_invalid")
            for field in ("session_id", "turn_id"):
                _identifier(speech_timing.get(field), "avatar_command_speech_timing_" + field)
            if (session_id is not None and speech_timing.get("session_id") != session_id
                    or speech_timing.get("turn_id") != payload.get("turn_id")):
                raise CompanionBridgeError("avatar_command_speech_timing_binding_invalid")
            for field, maximum in (("elapsed_seconds", 3600.0),
                                   ("started_at", float("inf"))):
                if field in speech_timing:
                    value = speech_timing[field]
                    try:
                        valid = (not isinstance(value, bool)
                            and isinstance(value, (int, float))
                            and math.isfinite(float(value))
                            and 0 <= float(value) <= maximum
                            and (field != "started_at" or float(value) > 0))
                    except (OverflowError, TypeError, ValueError):
                        valid = False
                    if not valid:
                        raise CompanionBridgeError("avatar_command_speech_timing_invalid")
            if event == "word_started":
                for field in ("word_index", "char_start", "char_length"):
                    if type(speech_timing.get(field)) is not int or speech_timing[field] < 0:
                        raise CompanionBridgeError("avatar_command_speech_timing_invalid")
        output_digest = payload.get("output_digest")
        if output_digest is not None and (
                not isinstance(output_digest, str) or _SHA256.fullmatch(output_digest) is None):
            raise CompanionBridgeError("avatar_command_field_invalid:output_digest")
        if payload.get("turn_id") is not None:
            _identifier(payload["turn_id"], "avatar_command_turn_id")
        lineage_fields = {"consequence_expectation_id", "consequence_expectation_digest",
            "consequence_handoff_id", "consequence_handoff_digest",
            "consequence_correlation_id"}
        present_lineage = set(payload) & lineage_fields
        if present_lineage and present_lineage != lineage_fields:
            raise CompanionBridgeError("avatar_command_consequence_lineage_incomplete")
        if present_lineage:
            for field in ("consequence_expectation_id", "consequence_handoff_id",
                          "consequence_correlation_id"):
                _identifier(payload[field], "avatar_command_" + field)
            for field in ("consequence_expectation_digest", "consequence_handoff_digest"):
                if re.fullmatch(r"sha256:[0-9a-f]{64}", str(payload[field])) is None:
                    raise CompanionBridgeError("avatar_command_consequence_digest_invalid")
    elif kind == "screen_capture_request":
        if admission is not None:
            raise CompanionBridgeError("bridge_admission_unexpected")
        question = payload.get("question")
        if (set(payload) not in (
                    SCREEN_CAPTURE_REQUEST_FIELDS,
                    SCREEN_CAPTURE_REQUEST_FIELDS | {"question"})
                or not isinstance(payload.get("capture_request_id"), str)
                or re.fullmatch(r"[0-9a-f]{32}", payload["capture_request_id"]) is None
                or (question is not None and (
                    not isinstance(question, str) or not question.strip()
                    or len(question) > 2048))):
            raise CompanionBridgeError("screen_capture_request_invalid")
    elif kind == "avatar_consequence_request":
        if admission is not None or set(payload) != AVATAR_CONSEQUENCE_REQUEST_FIELDS:
            raise CompanionBridgeError("avatar_consequence_request_shape_invalid")
        if (payload.get("schema_version") != AVATAR_CONSEQUENCE_REQUEST_SCHEMA
                or not isinstance(payload.get("capture_request_id"), str)
                or re.fullmatch(r"[0-9a-f]{32}", payload["capture_request_id"]) is None):
            raise CompanionBridgeError("avatar_consequence_request_identity_invalid")
        for field in ("expectation_id", "handoff_id", "correlation_id"):
            _identifier(payload.get(field), "avatar_consequence_" + field)
        for field in ("expectation_digest", "handoff_digest"):
            value = payload.get(field)
            if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                raise CompanionBridgeError("avatar_consequence_request_digest_invalid")
        report_id, report_digest = (payload.get("renderer_report_id"),
                                    payload.get("renderer_report_digest"))
        if ((report_id is None) != (report_digest is None)
                or (report_id is not None and (not isinstance(report_id, str)
                    or _IDENTIFIER.fullmatch(report_id) is None))
                or (report_digest is not None and (not isinstance(report_digest, str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", report_digest) is None))):
            raise CompanionBridgeError("avatar_consequence_request_renderer_binding_invalid")
        generation = payload.get("body_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise CompanionBridgeError("avatar_consequence_request_generation_invalid")
    elif kind == "consequence":
        if admission is not None:
            raise CompanionBridgeError("bridge_admission_unexpected")
        schema = payload.get("schema_version")
        if schema == CONSEQUENCE_OBSERVATION_SCHEMA:
            if set(payload) != CONSEQUENCE_OBSERVATION_FIELDS:
                raise CompanionBridgeError("consequence_observation_shape_invalid")
        elif schema == CONSEQUENCE_OBSERVATION_SCHEMA_V2:
            if set(payload) != CONSEQUENCE_OBSERVATION_FIELDS | {
                    "capture_request_id", "capture_provenance"}:
                raise CompanionBridgeError("consequence_observation_shape_invalid")
            if (not isinstance(payload.get("capture_request_id"), str)
                    or re.fullmatch(r"[0-9a-f]{32}", payload["capture_request_id"]) is None):
                raise CompanionBridgeError("consequence_observation_capture_request_invalid")
            provenance = payload.get("capture_provenance")
            if (not isinstance(provenance, Mapping)
                    or provenance.get("capture_scope") != "allowlisted_foreground_game_client_area"
                    or provenance.get("raw_frame_retained") is not False):
                raise CompanionBridgeError("consequence_observation_capture_provenance_invalid")
            for field in ("capture_digest", "process_name_digest", "consent_id_digest"):
                if (not isinstance(provenance.get(field), str)
                        or _SHA256.fullmatch(provenance[field]) is None):
                    raise CompanionBridgeError("consequence_observation_capture_provenance_invalid")
            if (set(provenance) == CONSEQUENCE_CAPTURE_PROVENANCE_FIELDS
                    and provenance.get("schema_version") == "sentientos.screen_capture_provenance:v1"):
                pass
            elif (set(provenance) == CONSEQUENCE_CAPTURE_SEQUENCE_PROVENANCE_FIELDS
                    and provenance.get("schema_version") == "sentientos.screen_capture_provenance:v2"):
                digests = provenance.get("sample_capture_digests")
                timestamps = provenance.get("sample_captured_at")
                offsets = provenance.get("sample_offsets_seconds")
                sequence_digest = provenance.get("capture_sequence_digest")
                if (not isinstance(digests, list) or not 3 <= len(digests) <= 5
                        or not isinstance(timestamps, list) or len(timestamps) != len(digests)
                        or not isinstance(offsets, list) or len(offsets) != len(digests)
                        or any(not isinstance(value, str) or _SHA256.fullmatch(value) is None
                               for value in digests)
                        or any(not isinstance(value, str) or not value or len(value) > 64
                               for value in timestamps)
                        or any(isinstance(value, bool) or not isinstance(value, (int, float))
                               or not math.isfinite(float(value)) or float(value) < 0
                               for value in offsets)
                        or any(float(right) - float(left) < 0.35
                               or float(right) - float(left) > 2.0
                               for left, right in zip(offsets, offsets[1:]))
                        or float(offsets[-1]) - float(offsets[0]) > 5.0
                        or not isinstance(sequence_digest, str)
                        or _SHA256.fullmatch(sequence_digest) is None
                        or provenance.get("capture_digest") != digests[-1]):
                    raise CompanionBridgeError("consequence_observation_capture_provenance_invalid")
                parsed_times = []
                try:
                    parsed_times = [datetime.fromisoformat(value.replace("Z", "+00:00"))
                                    for value in timestamps]
                except ValueError as exc:
                    raise CompanionBridgeError(
                        "consequence_observation_capture_provenance_invalid") from exc
                if (any(value.tzinfo is None or value.utcoffset() is None
                        for value in parsed_times)
                        or any(right <= left for left, right in zip(
                            parsed_times, parsed_times[1:]))):
                    raise CompanionBridgeError("consequence_observation_capture_provenance_invalid")
                sequence_binding = {
                    "sample_capture_digests": digests,
                    "sample_captured_at": timestamps,
                    "sample_offsets_seconds": offsets,
                    "process_name_digest": provenance["process_name_digest"],
                    "consent_id_digest": provenance["consent_id_digest"],
                    "capture_scope": provenance["capture_scope"],
                }
                expected_sequence_digest = hashlib.sha256(json.dumps(
                    sequence_binding, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True).encode("utf-8")).hexdigest()
                if sequence_digest != expected_sequence_digest:
                    raise CompanionBridgeError(
                        "consequence_observation_capture_provenance_invalid")
            else:
                raise CompanionBridgeError("consequence_observation_capture_provenance_invalid")
        else:
            raise CompanionBridgeError("consequence_observation_shape_invalid")
        for field in ("expectation_id", "handoff_id", "correlation_id"):
            _identifier(payload.get(field), "consequence_" + field)
        for field in ("expectation_digest", "handoff_digest"):
            value = payload.get(field)
            if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                raise CompanionBridgeError("consequence_observation_digest_invalid")
        report_id = payload.get("renderer_report_id")
        report_digest = payload.get("renderer_report_digest")
        if ((report_id is None) != (report_digest is None)
                or (report_id is not None
                    and (not isinstance(report_id, str)
                        or _IDENTIFIER.fullmatch(report_id) is None))
                or (report_digest is not None
                    and (not isinstance(report_digest, str)
                        or re.fullmatch(r"sha256:[0-9a-f]{64}", report_digest) is None))):
            raise CompanionBridgeError("consequence_observation_renderer_binding_invalid")
        generation = payload.get("body_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise CompanionBridgeError("consequence_observation_generation_invalid")
        observed = payload.get("observed")
        if (not isinstance(observed, Mapping) or not observed or len(observed) > 32
                or any(not isinstance(key, str) or not key or len(key) > 128
                    for key in observed)):
            raise CompanionBridgeError("consequence_observation_values_invalid")
        try:
            if len(_canonical(observed)) > 8 * 1024:
                raise CompanionBridgeError("consequence_observation_values_exceeded")
        except CompanionBridgeError:
            raise
        if (not isinstance(payload.get("confidence"), str)
                or payload.get("confidence") not in {"high", "medium", "low", "unknown"}):
            raise CompanionBridgeError("consequence_observation_confidence_invalid")
        if (not isinstance(payload.get("quality"), str)
                or payload.get("quality") not in {"usable", "partial", "unusable", "unknown"}):
            raise CompanionBridgeError("consequence_observation_quality_invalid")
        _timestamp(payload.get("observed_at"))
    elif admission is not None:
        raise CompanionBridgeError("bridge_admission_unexpected")
    if kind == "acknowledgment":
        try:
            _identifier(payload.get("message_id"), "bridge_acknowledgment_reference")
        except CompanionBridgeError as exc:
            raise CompanionBridgeError("bridge_acknowledgment_reference_required") from exc
        disposition = payload.get("disposition")
        if disposition is not None and (
                not isinstance(disposition, str)
                or disposition not in {"accepted", "rejected_backpressure"}):
            raise CompanionBridgeError("bridge_acknowledgment_disposition_invalid")


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
    _validate_message(kind, payload, admission, session_id=session_id)
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
    signed_envelope: bytes = field(default=b"", repr=False, compare=False)


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

    @property
    def expected_generations(self) -> Mapping[str, str]:
        """Expose configured source generation identities without source keys."""
        return dict(self._generations)

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
        _validate_message(kind, payload, admission, session_id=session_id)
        cursor = (source_id, session_id, generation_id)
        with self._sequence_lock:
            if sequence <= self._high_water.get(cursor, 0):
                raise CompanionBridgeError("bridge_replay_or_out_of_order")
            self._high_water[cursor] = sequence
        message_id = hashlib.sha256(_canonical(body)).hexdigest()
        return VerifiedBridgeMessage(message_id, kind, source_id, session_id,
            generation_id, sequence, stamp, dict(payload), dict(admission) if admission else None,
            encoded)
