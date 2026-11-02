"""Bind Windows foreground observations to SentientOS automatic workload mode."""
from __future__ import annotations

import hashlib
import math
import re
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol

from .foreground_game_detection import (
    ForegroundGameObservation,
    normalize_game_process_names,
)
from .gaming_companion_bridge import CompanionBridgeError, VerifiedBridgeMessage, encode_message
from .gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
)

_SCHEMA = "sentientos.foreground_game_observation:v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED_FAILURES = frozenset({
    "unsupported_platform", "observation_failed", "observation_unavailable",
    "process_name_invalid",
})
_MAX_DRAIN_PER_OBSERVE = 32
_MAX_OBSERVATION_TTL_SECONDS = 30.0


class ForegroundObservationSender(Protocol):
    def observe(self, process_names: tuple[str, ...] | list[str]) -> ForegroundGameObservation: ...


class WindowsForegroundBridgePublisher:
    """Publish one Windows foreground sample over the authenticated loopback client."""

    def __init__(self, *, detector: ForegroundObservationSender,
                 client: CompanionBridgeLoopbackClient, source_id: str,
                 session_id: str, generation_id: str, source_key: bytes) -> None:
        if not callable(getattr(detector, "observe", None)):
            raise CompanionBridgeError("foreground_detector_required")
        if not isinstance(client, CompanionBridgeLoopbackClient):
            raise CompanionBridgeError("bridge_loopback_client_required")
        if not isinstance(source_key, bytes) or len(source_key) < 32:
            raise CompanionBridgeError("bridge_key_too_short")
        # Validate all caller-supplied identity fields before the first sample.
        encode_message(kind="observation", source_id=source_id, session_id=session_id,
            generation_id=generation_id, sequence=1,
            payload={"schema_version": _SCHEMA, "status": "observation_unavailable",
                     "game_foreground": None, "process_name_digest": None,
                     "observed_at": "2000-01-01T00:00:00+00:00"},
            key=source_key, created_at="2000-01-01T00:00:00+00:00")
        self._detector = detector
        self._client = client
        self._source_id = source_id
        self._session_id = session_id
        self._generation_id = generation_id
        self._source_key = bytes(source_key)
        self._sequence = 0
        self._lock = threading.Lock()

    def publish_once(self, process_names: tuple[str, ...] | list[str]) -> VerifiedBridgeMessage:
        """Sample and send one explicitly allowlisted foreground observation."""
        with self._lock:
            observation = self._detector.observe(process_names)
            if type(observation) is not ForegroundGameObservation:
                raise CompanionBridgeError("foreground_observation_invalid")
            if observation.transport_provenance is not None:
                raise CompanionBridgeError("foreground_observation_not_local")
            payload = observation.to_dict()
            self._sequence += 1
            sequence = self._sequence
            encoded = encode_message(kind="observation", source_id=self._source_id,
                session_id=self._session_id, generation_id=self._generation_id,
                sequence=sequence, payload=payload, key=self._source_key,
                created_at=observation.observed_at)
            return self._client.send(encoded)


class BridgeForegroundGameDetector:
    """Consume verified Windows samples and fail conservatively when they expire."""

    def __init__(self, *, runtime: CompanionBridgeLoopbackRuntime, source_id: str,
                 generation_id: str, clock: Callable[[], datetime] | None = None,
                 max_observation_age_seconds: float = 5.0) -> None:
        if not isinstance(runtime, CompanionBridgeLoopbackRuntime):
            raise CompanionBridgeError("bridge_loopback_runtime_required")
        if (isinstance(max_observation_age_seconds, bool)
                or not isinstance(max_observation_age_seconds, (int, float))
                or not math.isfinite(float(max_observation_age_seconds))
                or max_observation_age_seconds <= 0
                or max_observation_age_seconds > _MAX_OBSERVATION_TTL_SECONDS):
            raise CompanionBridgeError("foreground_observation_ttl_invalid")
        self._runtime = runtime
        self._source_id = source_id
        self._generation_id = generation_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_age = float(max_observation_age_seconds)
        self._lock = threading.Lock()
        self._last: ForegroundGameObservation | None = None

    def close(self) -> None:
        """Stop the dedicated foreground-observation listener owned by this adapter."""
        self._runtime.close()

    def observe(self, process_names: tuple[str, ...] | list[str]) -> ForegroundGameObservation:
        allowed = normalize_game_process_names(process_names)
        allowed_digests = {hashlib.sha256(name.encode("utf-8")).hexdigest() for name in allowed}
        with self._lock:
            for _ in range(_MAX_DRAIN_PER_OBSERVE):
                try:
                    message = self._runtime.receive(timeout=0)
                except CompanionBridgeError as exc:
                    if exc.args and exc.args[0] == "bridge_receive_timeout":
                        break
                    self._last = None
                    return self._unavailable("bridge_observation_unavailable")
                parsed = self._parse(message, allowed_digests)
                if parsed is None:
                    self._last = None
                    return self._unavailable("bridge_observation_invalid")
                self._last = parsed
            if self._last is None:
                return self._unavailable("bridge_observation_unavailable")
            if not self._is_fresh(self._last.observed_at):
                self._last = None
                return self._unavailable("bridge_observation_expired")
            return self._last

    def _parse(self, message: VerifiedBridgeMessage,
               allowed_digests: set[str]) -> ForegroundGameObservation | None:
        if (message.kind != "observation" or message.source_id != self._source_id
                or message.generation_id != self._generation_id):
            return None
        payload = message.payload
        required = {"schema_version", "status", "game_foreground", "process_name_digest", "observed_at"}
        if set(payload) != required or payload.get("schema_version") != _SCHEMA:
            return None
        status = payload.get("status")
        observed_at = payload.get("observed_at")
        if not isinstance(observed_at, str):
            return None
        if not self._is_fresh(observed_at):
            return ForegroundGameObservation("bridge_observation_expired", None, None,
                                             observed_at)
        try:
            envelope_time = _parse_timestamp(message.created_at)
            sample_time = _parse_timestamp(observed_at)
        except ValueError:
            return None
        if abs((envelope_time - sample_time).total_seconds()) > 1.0:
            return None
        provenance = {
            "message_id": message.message_id,
            "source_id": message.source_id,
            "session_id": message.session_id,
            "generation_id": message.generation_id,
            "sequence": message.sequence,
            "envelope_created_at": message.created_at,
        }
        if status == "available":
            foreground = payload.get("game_foreground")
            digest = payload.get("process_name_digest")
            if (type(foreground) is not bool or not isinstance(digest, str)
                    or _DIGEST.fullmatch(digest) is None):
                return None
            # Recompute allowlist membership locally from the basename digest;
            # the sender's boolean cannot broaden the operator's process list.
            if foreground != (digest in allowed_digests):
                return None
            return ForegroundGameObservation("available", foreground, digest, observed_at,
                                             transport_provenance=provenance)
        if status not in _ALLOWED_FAILURES:
            return None
        if payload.get("game_foreground") is not None or payload.get("process_name_digest") is not None:
            return None
        return ForegroundGameObservation(str(status), None, None, observed_at,
                                         transport_provenance=provenance)

    def _is_fresh(self, value: str) -> bool:
        try:
            sample = _parse_timestamp(value)
            now = self._clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                return False
            age = (now.astimezone(timezone.utc) - sample).total_seconds()
            return -1.0 <= age <= self._max_age
        except (TypeError, ValueError, OverflowError):
            return False

    def _unavailable(self, status: str) -> ForegroundGameObservation:
        now = self._clock()
        stamp = now.astimezone(timezone.utc).isoformat() if isinstance(now, datetime) and now.tzinfo else ""
        return ForegroundGameObservation(status, None, None, stamp)

    def last_transport_provenance(self) -> Mapping[str, Any] | None:
        with self._lock:
            return (dict(self._last.transport_provenance)
                    if self._last is not None and self._last.transport_provenance is not None
                    else None)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("foreground_timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)
