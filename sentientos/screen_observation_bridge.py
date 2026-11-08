"""Authenticated, bounded transport for opt-in Windows game-screen OCR.

Frames remain on the capture host. Only bounded OCR text and an optional local
visual summary are sent. This adapter uses the existing bridge transport and
does not capture, retain, or authorize screen access itself.
"""
from __future__ import annotations

import math
import hashlib
import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .gaming_companion_bridge import (
    CompanionBridgeError,
    VerifiedBridgeMessage,
    encode_message,
)
from .gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
)

SCREEN_OBSERVATION_SCHEMA = "sentientos.game_screen_observation:v6"
SCREEN_OBSERVATION_FAILURE_SCHEMA = "sentientos.game_screen_observation_failure:v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z")
_FAILURE_CODE = re.compile(r"(?:screen|game_screen)_[a-z0-9_]{1,80}\Z")
_FIELDS = frozenset({
    "schema_version", "modality", "text", "text_status", "captured_at", "backend",
    "capture_digest", "process_name_digest", "consent_id_digest",
    "capture_scope", "raw_frame_retained", "text_truncated",
    "text_change_kind", "previous_text_digest",
    "visual_change_kind", "visual_change_score", "component_statuses",
    "component_failure_codes",
})
_MAX_DRAIN = 32


class ScreenObservationBridgeError(CompanionBridgeError):
    """Invalid, unavailable, or expired bridged screen observation."""


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ScreenObservationBridgeError("screen_observation_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScreenObservationBridgeError("screen_observation_timestamp_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ScreenObservationBridgeError("screen_observation_timestamp_invalid")
    return parsed.astimezone(timezone.utc)


def _observation_payload(observation: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(observation, Mapping):
        raise ScreenObservationBridgeError("screen_observation_invalid")
    payload = dict(observation)
    optional_fields = {"component_statuses", "component_failure_codes"}
    required_fields = _FIELDS - optional_fields
    allowed_shapes = tuple(
        required_fields | {field for index, field in enumerate(sorted(optional_fields))
                           if mask & (1 << index)} | request_fields
        for mask in range(1 << len(optional_fields))
        for request_fields in (set(), {"capture_request_id"})
    )
    if set(payload) not in allowed_shapes:
        raise ScreenObservationBridgeError("screen_observation_shape_invalid")
    request_id = payload.get("capture_request_id")
    text_status = payload.get("text_status")
    component_statuses = payload.get("component_statuses")
    if component_statuses is not None and (
            not isinstance(component_statuses, Mapping)
            or not component_statuses
            or set(component_statuses) - {"ocr", "vision"}
            or any(not isinstance(status, str)
                   or status not in {"available", "unavailable", "no_readable_text"}
                   for status in component_statuses.values())
            or (payload.get("backend") == "tesseract+local_vision"
                and set(component_statuses) != {"ocr", "vision"})):
        raise ScreenObservationBridgeError("screen_observation_component_status_invalid")
    component_failures = payload.get("component_failure_codes")
    if component_failures is not None and (
            not isinstance(component_failures, Mapping)
            or not component_failures
            or not isinstance(component_statuses, Mapping)
            or set(component_failures) - {"ocr", "vision"}
            or any(not isinstance(code, str) or _FAILURE_CODE.fullmatch(code) is None
                   or component_statuses.get(component) != "unavailable"
                   for component, code in component_failures.items())):
        raise ScreenObservationBridgeError("screen_observation_component_failure_invalid")
    if request_id is not None and (
            not isinstance(request_id, str) or _REQUEST_ID.fullmatch(request_id) is None):
        raise ScreenObservationBridgeError("screen_observation_request_id_invalid")
    if (payload.get("schema_version") != SCREEN_OBSERVATION_SCHEMA
            or payload.get("modality") != "screen"
            or not isinstance(payload.get("text"), str)
            or len(payload["text"]) > 1200
            or text_status not in ("available", "no_readable_text")
            or (text_status == "available" and not payload["text"].strip())
            or (text_status == "no_readable_text" and payload["text"] != "")
            or payload.get("capture_scope") != "allowlisted_foreground_game_client_area"
            or payload.get("raw_frame_retained") is not False
            or type(payload.get("text_truncated")) is not bool
            or not isinstance(payload.get("text_change_kind"), str)
            or payload["text_change_kind"] not in ("initial", "changed", "unchanged")
            or payload.get("visual_change_kind") not in ("initial", "changed", "stable", "unknown")
            or (payload.get("visual_change_score") is not None
                and (isinstance(payload.get("visual_change_score"), bool)
                     or not isinstance(payload.get("visual_change_score"), (int, float))
                     or not math.isfinite(float(payload["visual_change_score"]))
                     or not 0.0 <= float(payload["visual_change_score"]) <= 1.0))
            or not isinstance(payload.get("backend"), str)
            or not payload["backend"] or len(payload["backend"]) > 64):
        raise ScreenObservationBridgeError("screen_observation_contract_invalid")
    if ((payload["visual_change_kind"] == "initial"
            and payload["visual_change_score"] is not None)
            or (payload["visual_change_kind"] in ("changed", "stable")
                and payload["visual_change_score"] is None)):
        raise ScreenObservationBridgeError("screen_observation_visual_change_invalid")
    _timestamp(payload.get("captured_at"))
    for field in ("capture_digest", "process_name_digest", "consent_id_digest"):
        value = payload.get(field)
        if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
            raise ScreenObservationBridgeError("screen_observation_digest_invalid")
    previous_digest = payload.get("previous_text_digest")
    if payload["text_change_kind"] == "initial":
        if previous_digest is not None:
            raise ScreenObservationBridgeError("screen_observation_change_lineage_invalid")
    elif not isinstance(previous_digest, str) or _DIGEST.fullmatch(previous_digest) is None:
        raise ScreenObservationBridgeError("screen_observation_change_lineage_invalid")
    current_text_digest = hashlib.sha256(payload["text"].encode("utf-8")).hexdigest()
    if ((payload["text_change_kind"] == "unchanged")
            != (previous_digest == current_text_digest)):
        raise ScreenObservationBridgeError("screen_observation_change_lineage_invalid")
    return payload


class WindowsScreenObservationBridgePublisher:
    """Publish bounded screen results and correlated failures from the Windows edge."""

    def __init__(self, *, observe: Callable[[], Mapping[str, Any] | None],
                 client: CompanionBridgeLoopbackClient, source_id: str,
                 session_id: str, generation_id: str, source_key: bytes,
                 observe_question: Callable[[str], Mapping[str, Any] | None] | None = None
                 ) -> None:
        if not callable(observe):
            raise ScreenObservationBridgeError("screen_observation_source_required")
        if not isinstance(client, CompanionBridgeLoopbackClient):
            raise ScreenObservationBridgeError("bridge_loopback_client_required")
        if not isinstance(source_key, bytes) or len(source_key) < 32:
            raise ScreenObservationBridgeError("bridge_key_too_short")
        if observe_question is not None and not callable(observe_question):
            raise ScreenObservationBridgeError("screen_observation_source_required")
        self._observe = observe
        self._observe_question = observe_question
        self._client = client
        self._source_id = source_id
        self._session_id = session_id
        self._generation_id = generation_id
        self._source_key = bytes(source_key)
        self._sequence = 0
        self._lock = threading.Lock()

    def publish_once(self, *, capture_request_id: str | None = None,
                     question: str | None = None) -> VerifiedBridgeMessage | None:
        """Publish one result bound to an explicit request and optional user question."""
        if capture_request_id is not None and _REQUEST_ID.fullmatch(capture_request_id) is None:
            raise ScreenObservationBridgeError("screen_observation_request_id_invalid")
        if question is not None and (
                not isinstance(question, str) or not question.strip() or len(question) > 2048):
            raise ScreenObservationBridgeError("screen_observation_question_invalid")
        if question is not None and self._observe_question is not None:
            observation = self._observe_question(question)
        elif question is not None:
            raise ScreenObservationBridgeError("screen_observation_question_unavailable")
        else:
            observation = self._observe()
        if observation is None:
            return None
        payload = dict(observation)
        payload["schema_version"] = SCREEN_OBSERVATION_SCHEMA
        if capture_request_id is not None:
            payload["capture_request_id"] = capture_request_id
        payload = _observation_payload(payload)
        with self._lock:
            sequence = self._sequence + 1
            encoded = encode_message(kind="observation", source_id=self._source_id,
                session_id=self._session_id, generation_id=self._generation_id,
                sequence=sequence, payload=payload, key=self._source_key)
            self._sequence = sequence
            return self._client.send(encoded)

    def publish_request(self, capture_request_id: str,
                        question: str | None = None) -> bool:
        """Capture once and publish a failure code if that requested capture fails."""
        try:
            result = self.publish_once(
                capture_request_id=capture_request_id, question=question)
        except Exception as exc:
            candidate = exc.args[0] if exc.args else None
            failure_code = (
                candidate if isinstance(candidate, str)
                and _FAILURE_CODE.fullmatch(candidate) is not None
                else "screen_observation_failed")
            try:
                self.publish_failure(capture_request_id=capture_request_id,
                                     failure_code=failure_code)
            except Exception as publish_error:
                raise publish_error from exc
            raise
        if result is None:
            self.publish_failure(capture_request_id=capture_request_id,
                                 failure_code="screen_observation_unavailable")
            return False
        return True

    def publish_failure(self, *, capture_request_id: str,
                        failure_code: str) -> VerifiedBridgeMessage:
        """Return a safe, request-correlated capture failure without frame data."""
        if (not isinstance(capture_request_id, str)
                or _REQUEST_ID.fullmatch(capture_request_id) is None):
            raise ScreenObservationBridgeError("screen_observation_request_id_invalid")
        if not isinstance(failure_code, str) or _FAILURE_CODE.fullmatch(failure_code) is None:
            raise ScreenObservationBridgeError("screen_observation_failure_code_invalid")
        payload = {
            "schema_version": SCREEN_OBSERVATION_FAILURE_SCHEMA,
            "capture_request_id": capture_request_id,
            "failure_code": failure_code,
        }
        with self._lock:
            sequence = self._sequence + 1
            encoded = encode_message(kind="screen_observation_failure",
                source_id=self._source_id, session_id=self._session_id,
                generation_id=self._generation_id, sequence=sequence,
                payload=payload, key=self._source_key)
            self._sequence = sequence
            return self._client.send(encoded)


class BridgeScreenObservationProvider:
    """Consume one fresh verified OCR observation as a chat screen observer."""

    def __init__(self, *, runtime: CompanionBridgeLoopbackRuntime, source_id: str,
                 generation_id: str, clock: Callable[[], datetime] | None = None,
                 max_observation_age_seconds: float = 5.0) -> None:
        if not isinstance(runtime, CompanionBridgeLoopbackRuntime):
            raise ScreenObservationBridgeError("bridge_loopback_runtime_required")
        if (isinstance(max_observation_age_seconds, bool)
                or not isinstance(max_observation_age_seconds, (int, float))
                or not math.isfinite(float(max_observation_age_seconds))
                or not 0 < max_observation_age_seconds <= 30):
            raise ScreenObservationBridgeError("screen_observation_ttl_invalid")
        self._runtime = runtime
        self._source_id = source_id
        self._generation_id = generation_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_age = float(max_observation_age_seconds)

    def __call__(self) -> Mapping[str, object]:
        latest: VerifiedBridgeMessage | None = None
        for _ in range(_MAX_DRAIN):
            try:
                message = self._runtime.receive(timeout=0)
            except CompanionBridgeError as exc:
                if exc.args and exc.args[0] == "bridge_receive_timeout":
                    break
                raise ScreenObservationBridgeError("screen_observation_unavailable") from exc
            latest = message
        if latest is None:
            raise ScreenObservationBridgeError("screen_observation_unavailable")
        return self._verified_observation(latest)

    def wait_for_request(self, capture_request_id: str, *,
                         timeout_seconds: float = 12.0) -> Mapping[str, object]:
        if (not isinstance(capture_request_id, str)
                or _REQUEST_ID.fullmatch(capture_request_id) is None):
            raise ScreenObservationBridgeError("screen_observation_request_id_invalid")
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or not 0 < timeout_seconds <= 30):
            raise ScreenObservationBridgeError("screen_observation_wait_timeout_invalid")
        deadline = time.monotonic() + float(timeout_seconds)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ScreenObservationBridgeError("screen_observation_request_timeout")
            try:
                message = self._runtime.receive(timeout=remaining)
            except CompanionBridgeError as exc:
                if exc.args and exc.args[0] == "bridge_receive_timeout":
                    raise ScreenObservationBridgeError(
                        "screen_observation_request_timeout") from exc
                raise ScreenObservationBridgeError(
                    "screen_observation_unavailable") from exc
            if (message.source_id != self._source_id
                    or message.generation_id != self._generation_id):
                raise ScreenObservationBridgeError("screen_observation_identity_invalid")
            if message.kind == "screen_observation_failure":
                payload = message.payload
                if (set(payload) != {"schema_version", "capture_request_id", "failure_code"}
                        or payload.get("schema_version")
                            != SCREEN_OBSERVATION_FAILURE_SCHEMA
                        or not isinstance(payload.get("capture_request_id"), str)
                        or _REQUEST_ID.fullmatch(payload["capture_request_id"]) is None
                        or not isinstance(payload.get("failure_code"), str)
                        or _FAILURE_CODE.fullmatch(payload["failure_code"]) is None):
                    raise ScreenObservationBridgeError(
                        "screen_observation_failure_contract_invalid")
                if payload["capture_request_id"] != capture_request_id:
                    continue
                raise ScreenObservationBridgeError(payload["failure_code"])
            if message.kind != "observation":
                raise ScreenObservationBridgeError("screen_observation_identity_invalid")
            payload = _observation_payload(message.payload)
            if payload.get("capture_request_id") != capture_request_id:
                continue
            # This observation is bound to a newly generated request ID and
            # the wait above is bounded by monotonic time. Avoid comparing
            # Windows capture time against the WSL wall clock, which can be
            # skewed by more than the normal freshness window.
            return self._verified_observation(
                message, payload, require_wall_clock_freshness=False)

    def _verified_observation(self, latest: VerifiedBridgeMessage,
                              payload: Mapping[str, Any] | None = None, *,
                              require_wall_clock_freshness: bool = True
                              ) -> Mapping[str, object]:
        if (latest.kind != "observation" or latest.source_id != self._source_id
                or latest.generation_id != self._generation_id):
            raise ScreenObservationBridgeError("screen_observation_identity_invalid")
        payload = _observation_payload(latest.payload) if payload is None else dict(payload)
        if require_wall_clock_freshness:
            now = self._clock()
            if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
                raise ScreenObservationBridgeError("screen_observation_clock_invalid")
            age = (now.astimezone(timezone.utc)
                   - _timestamp(payload["captured_at"])).total_seconds()
            if age < -1 or age > self._max_age:
                raise ScreenObservationBridgeError("screen_observation_expired")
        return {
            **payload,
            "bridge_message_provenance": {
                "message_id": latest.message_id,
                "source_id": latest.source_id,
                "session_id": latest.session_id,
                "generation_id": latest.generation_id,
                "sequence": latest.sequence,
                "created_at": latest.created_at,
                "payload_digest": hashlib.sha256(json.dumps(
                    dict(latest.payload), sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest(),
            },
        }


class ScreenCaptureRequestSender:
    """Issue one authenticated capture request over the supervised mTLS edge."""

    def __init__(self, *, client: Any, source_id: str, session_id: str,
                 generation_id: str, source_key: bytes) -> None:
        if not callable(getattr(client, "send", None)):
            raise ScreenObservationBridgeError("screen_capture_request_client_required")
        if not isinstance(source_key, bytes) or len(source_key) < 32:
            raise ScreenObservationBridgeError("bridge_key_too_short")
        self._client = client
        self._source_id = source_id
        self._session_id = session_id
        self._generation_id = generation_id
        self._source_key = bytes(source_key)
        self._sequence = 0
        self._lock = threading.Lock()

    def __call__(self, capture_request_id: str,
                 question: str | None = None) -> VerifiedBridgeMessage:
        if not isinstance(capture_request_id, str) or _REQUEST_ID.fullmatch(capture_request_id) is None:
            raise ScreenObservationBridgeError("screen_observation_request_id_invalid")
        if question is not None and (
                not isinstance(question, str) or not question.strip() or len(question) > 2048):
            raise ScreenObservationBridgeError("screen_observation_question_invalid")
        payload = {"capture_request_id": capture_request_id}
        if question is not None:
            payload["question"] = question
        with self._lock:
            self._sequence += 1
            encoded = encode_message(kind="screen_capture_request",
                source_id=self._source_id, session_id=self._session_id,
                generation_id=self._generation_id, sequence=self._sequence,
                payload=payload, key=self._source_key)
        return self._client.send(encoded)


class RequestDrivenScreenObservation:
    """Capture only after a chat request explicitly opts in to screen observation."""

    def __init__(self, *, request_sender: ScreenCaptureRequestSender,
                 provider: BridgeScreenObservationProvider,
                 timeout_seconds: float = 12.0,
                 consent_expires_at: str | None = None,
                 foreground_wait_seconds: float = 0.0) -> None:
        if not isinstance(request_sender, ScreenCaptureRequestSender):
            raise ScreenObservationBridgeError("screen_capture_request_sender_required")
        if not isinstance(provider, BridgeScreenObservationProvider):
            raise ScreenObservationBridgeError("screen_observation_provider_required")
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or not 0 < timeout_seconds <= 30):
            raise ScreenObservationBridgeError("screen_observation_wait_timeout_invalid")
        if (isinstance(foreground_wait_seconds, bool)
                or not isinstance(foreground_wait_seconds, (int, float))
                or not math.isfinite(float(foreground_wait_seconds))
                or not 0 <= foreground_wait_seconds <= 10):
            raise ScreenObservationBridgeError(
                "screen_observation_foreground_wait_invalid")
        self._sender = request_sender
        self._provider = provider
        self._timeout = float(timeout_seconds)
        self._foreground_wait_seconds = float(foreground_wait_seconds)
        self._consent_expires_at: datetime | None = None
        if consent_expires_at is not None:
            try:
                parsed_expiry = datetime.fromisoformat(
                    consent_expires_at.replace("Z", "+00:00"))
            except (AttributeError, ValueError) as exc:
                raise ScreenObservationBridgeError(
                    "screen_observation_consent_expiry_invalid") from exc
            if parsed_expiry.tzinfo is None:
                raise ScreenObservationBridgeError(
                    "screen_observation_consent_expiry_invalid")
            self._consent_expires_at = parsed_expiry.astimezone(timezone.utc)
        self._lock = threading.Lock()
        self._closed = False
        self._last_text: str | None = None
        self._last_text_backend: str | None = None
        self._last_sampled_monotonic = 0.0

    def consent_status(self) -> dict[str, object]:
        'Return launch-scoped consent state without exposing capture credentials.'
        if self._consent_expires_at is None:
            return {"consent_status": "unknown",
                    "foreground_wait_seconds": self._foreground_wait_seconds}
        seconds_remaining = (
            self._consent_expires_at - datetime.now(timezone.utc)).total_seconds()
        return {
            "consent_status": "active" if seconds_remaining > 0 else "expired",
            "consent_expires_at": (self._consent_expires_at.isoformat()
                                    .replace("+00:00", "Z")),
            "consent_seconds_remaining": max(0, int(seconds_remaining)),
            "foreground_wait_seconds": self._foreground_wait_seconds,
        }

    def __call__(self, question: str | None = None) -> Mapping[str, object]:
        if question is not None and (
                not isinstance(question, str) or not question.strip() or len(question) > 2048):
            raise ScreenObservationBridgeError("screen_observation_question_invalid")
        with self._lock:
            if self._closed:
                raise ScreenObservationBridgeError("screen_observation_unavailable")
            request_id = uuid.uuid4().hex
            self._sender(request_id, question=question)
            capture_request_accepted = time.monotonic()
            observed = dict(self._provider.wait_for_request(
                request_id, timeout_seconds=self._timeout))
            capture_received = time.monotonic()
            observed["capture_freshness"] = {
                "schema_version": "sentientos.request_bound_capture_freshness:v1",
                "basis": "request_correlated_monotonic_upper_bound",
                "capture_request_id": request_id,
                "capture_age_upper_bound_ms": max(0, int(math.ceil(
                    (capture_received - capture_request_accepted) * 1000))),
                "freshness_window_ms": int(math.ceil(self._timeout * 1000)),
            }
            current_text = observed.get("text")
            now = time.monotonic()
            current_backend = observed.get("backend")
            if (current_backend != "tesseract+local_vision"
                    and current_backend == self._last_text_backend
                    and isinstance(self._last_text, str)
                    and isinstance(current_text, str)
                    and now - self._last_sampled_monotonic <= 30.0
                    and self._last_text != current_text):
                from .perception.screen_text_delta import build_ocr_text_line_delta
                observed["text_delta"] = build_ocr_text_line_delta(
                    self._last_text, current_text)
            self._last_text = current_text if isinstance(current_text, str) else None
            self._last_text_backend = (
                current_backend if isinstance(current_backend, str) else None)
            self._last_sampled_monotonic = now
            return observed

    def observe_question(self, question: str) -> Mapping[str, object]:
        """Capture this user's current screen to answer their local question."""
        return self(question)

    def close(self) -> None:
        with self._lock:
            self._closed = True


__all__ = [
    "BridgeScreenObservationProvider", "RequestDrivenScreenObservation",
    "SCREEN_OBSERVATION_FAILURE_SCHEMA", "SCREEN_OBSERVATION_SCHEMA",
    "ScreenCaptureRequestSender",
    "ScreenObservationBridgeError", "WindowsScreenObservationBridgePublisher",
]
