"""Authenticated, bounded transport for opt-in Windows game-screen OCR.

Frames and OCR remain on the capture host. Only a bounded OCR observation is
sent. This adapter uses the existing bridge transport and does not capture,
retain, or authorize screen access itself.
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

SCREEN_OBSERVATION_SCHEMA = "sentientos.game_screen_observation:v4"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z")
_FIELDS = frozenset({
    "schema_version", "modality", "text", "text_status", "captured_at", "backend",
    "capture_digest", "process_name_digest", "consent_id_digest",
    "capture_scope", "raw_frame_retained", "text_truncated",
    "text_change_kind", "previous_text_digest",
    "visual_change_kind", "visual_change_score",
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
    if set(payload) not in (_FIELDS, _FIELDS | {"capture_request_id"}):
        raise ScreenObservationBridgeError("screen_observation_shape_invalid")
    request_id = payload.get("capture_request_id")
    text_status = payload.get("text_status")
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
    """Publish one OCR result from the existing consented Windows screen owner."""

    def __init__(self, *, observe: Callable[[], Mapping[str, Any] | None],
                 client: CompanionBridgeLoopbackClient, source_id: str,
                 session_id: str, generation_id: str, source_key: bytes) -> None:
        if not callable(observe):
            raise ScreenObservationBridgeError("screen_observation_source_required")
        if not isinstance(client, CompanionBridgeLoopbackClient):
            raise ScreenObservationBridgeError("bridge_loopback_client_required")
        if not isinstance(source_key, bytes) or len(source_key) < 32:
            raise ScreenObservationBridgeError("bridge_key_too_short")
        self._observe = observe
        self._client = client
        self._source_id = source_id
        self._session_id = session_id
        self._generation_id = generation_id
        self._source_key = bytes(source_key)
        self._sequence = 0

    def publish_once(self, *, capture_request_id: str | None = None
                     ) -> VerifiedBridgeMessage | None:
        """Publish one OCR result, optionally bound to one explicit chat request."""
        if capture_request_id is not None and _REQUEST_ID.fullmatch(capture_request_id) is None:
            raise ScreenObservationBridgeError("screen_observation_request_id_invalid")
        observation = self._observe()
        if observation is None:
            return None
        payload = dict(observation)
        payload["schema_version"] = SCREEN_OBSERVATION_SCHEMA
        if capture_request_id is not None:
            payload["capture_request_id"] = capture_request_id
        payload = _observation_payload(payload)
        encoded = encode_message(kind="observation", source_id=self._source_id,
            session_id=self._session_id, generation_id=self._generation_id,
            sequence=self._sequence + 1, payload=payload, key=self._source_key,
            created_at=payload["captured_at"])
        self._sequence += 1
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
            if (message.kind != "observation" or message.source_id != self._source_id
                    or message.generation_id != self._generation_id):
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

    def __call__(self, capture_request_id: str) -> VerifiedBridgeMessage:
        if not isinstance(capture_request_id, str) or _REQUEST_ID.fullmatch(capture_request_id) is None:
            raise ScreenObservationBridgeError("screen_observation_request_id_invalid")
        with self._lock:
            self._sequence += 1
            encoded = encode_message(kind="screen_capture_request",
                source_id=self._source_id, session_id=self._session_id,
                generation_id=self._generation_id, sequence=self._sequence,
                payload={"capture_request_id": capture_request_id},
                key=self._source_key)
        return self._client.send(encoded)


class RequestDrivenScreenObservation:
    """Capture only after a chat request explicitly opts in to screen observation."""

    def __init__(self, *, request_sender: ScreenCaptureRequestSender,
                 provider: BridgeScreenObservationProvider,
                 timeout_seconds: float = 12.0) -> None:
        if not isinstance(request_sender, ScreenCaptureRequestSender):
            raise ScreenObservationBridgeError("screen_capture_request_sender_required")
        if not isinstance(provider, BridgeScreenObservationProvider):
            raise ScreenObservationBridgeError("screen_observation_provider_required")
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(float(timeout_seconds))
                or not 0 < timeout_seconds <= 30):
            raise ScreenObservationBridgeError("screen_observation_wait_timeout_invalid")
        self._sender = request_sender
        self._provider = provider
        self._timeout = float(timeout_seconds)
        self._lock = threading.Lock()
        self._closed = False
        self._last_text: str | None = None
        self._last_sampled_monotonic = 0.0

    def __call__(self) -> Mapping[str, object]:
        with self._lock:
            if self._closed:
                raise ScreenObservationBridgeError("screen_observation_unavailable")
            request_id = uuid.uuid4().hex
            self._sender(request_id)
            observed = dict(self._provider.wait_for_request(
                request_id, timeout_seconds=self._timeout))
            current_text = observed.get("text")
            now = time.monotonic()
            if (isinstance(self._last_text, str) and isinstance(current_text, str)
                    and now - self._last_sampled_monotonic <= 30.0
                    and self._last_text != current_text):
                from .perception.screen_text_delta import build_ocr_text_line_delta
                observed["text_delta"] = build_ocr_text_line_delta(
                    self._last_text, current_text)
            self._last_text = current_text if isinstance(current_text, str) else None
            self._last_sampled_monotonic = now
            return observed

    def close(self) -> None:
        with self._lock:
            self._closed = True


__all__ = [
    "BridgeScreenObservationProvider", "RequestDrivenScreenObservation",
    "SCREEN_OBSERVATION_SCHEMA", "ScreenCaptureRequestSender",
    "ScreenObservationBridgeError", "WindowsScreenObservationBridgePublisher",
]
