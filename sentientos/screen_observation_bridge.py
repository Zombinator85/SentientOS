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

SCREEN_OBSERVATION_SCHEMA = "sentientos.game_screen_observation:v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "schema_version", "modality", "text", "captured_at", "backend",
    "capture_digest", "process_name_digest", "consent_id_digest",
    "capture_scope", "raw_frame_retained", "text_truncated",
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
    if set(payload) != _FIELDS:
        raise ScreenObservationBridgeError("screen_observation_shape_invalid")
    if (payload.get("schema_version") != SCREEN_OBSERVATION_SCHEMA
            or payload.get("modality") != "screen"
            or not isinstance(payload.get("text"), str)
            or not payload["text"].strip() or len(payload["text"]) > 1200
            or payload.get("capture_scope") != "allowlisted_foreground_game_client_area"
            or payload.get("raw_frame_retained") is not False
            or type(payload.get("text_truncated")) is not bool
            or not isinstance(payload.get("backend"), str)
            or not payload["backend"] or len(payload["backend"]) > 64):
        raise ScreenObservationBridgeError("screen_observation_contract_invalid")
    _timestamp(payload.get("captured_at"))
    for field in ("capture_digest", "process_name_digest", "consent_id_digest"):
        value = payload.get(field)
        if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
            raise ScreenObservationBridgeError("screen_observation_digest_invalid")
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

    def publish_once(self) -> VerifiedBridgeMessage | None:
        """Send a fresh OCR result once; uncertain delivery is not retried."""
        observation = self._observe()
        if observation is None:
            return None
        payload = dict(observation)
        payload["schema_version"] = SCREEN_OBSERVATION_SCHEMA
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
        if (latest.kind != "observation" or latest.source_id != self._source_id
                or latest.generation_id != self._generation_id):
            raise ScreenObservationBridgeError("screen_observation_identity_invalid")
        payload = _observation_payload(latest.payload)
        now = self._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise ScreenObservationBridgeError("screen_observation_clock_invalid")
        age = (now.astimezone(timezone.utc) - _timestamp(payload["captured_at"])).total_seconds()
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


__all__ = [
    "BridgeScreenObservationProvider", "SCREEN_OBSERVATION_SCHEMA",
    "ScreenObservationBridgeError", "WindowsScreenObservationBridgePublisher",
]
