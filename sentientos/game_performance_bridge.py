"""Authenticated transport for bounded Windows game-performance samples.

The edge samples frame pacing and one explicitly selected process. The core
accepts only fresh, authenticated observations and exposes their provenance;
this module grants no inference or host-actuation authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol, cast

from .gaming_companion_bridge import CompanionBridgeError, VerifiedBridgeMessage, encode_message
from .gaming_companion_bridge_runtime import CompanionBridgeLoopbackClient
from .windows_game_performance import GamePerformanceObservation, WindowsGamePerformanceObserver

_SCHEMA = "sentientos.game_performance_observation:v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_AGE_SECONDS = 10.0


class _PerformanceReceiver(Protocol):
    def receive(self, timeout: float | None = None) -> VerifiedBridgeMessage: ...


@dataclass(frozen=True, slots=True)
class VerifiedGamePerformanceObservation:
    """A shape-checked sample whose transport envelope passed bridge HMAC checks."""

    source_id: str
    generation_id: str
    sequence: int
    message_id: str
    payload_digest: str
    observed_at: str
    process_id_digest: str
    frame_time_p95_ms: float | None
    hitch_count_over_50ms: int | None
    process_cpu_percent: float | None
    process_rss_bytes: int | None
    status: str


class WindowsGamePerformanceBridgePublisher:
    """Publish one observed Windows sample; uncertain sends are never replayed."""

    def __init__(self, *, observer: WindowsGamePerformanceObserver,
                 client: CompanionBridgeLoopbackClient, source_id: str,
                 session_id: str, generation_id: str, source_key: bytes,
                 process_id: int, clock: Callable[[], str] | None = None) -> None:
        if type(observer) is not WindowsGamePerformanceObserver:
            raise CompanionBridgeError("game_performance_observer_required")
        if not isinstance(client, CompanionBridgeLoopbackClient):
            raise CompanionBridgeError("bridge_client_required")
        if not isinstance(source_key, bytes) or len(source_key) < 32:
            raise CompanionBridgeError("bridge_key_too_short")
        if type(process_id) is not int or process_id < 1:
            raise CompanionBridgeError("game_process_id_invalid")
        self._observer, self._client = observer, client
        self._source_id, self._session_id = source_id, session_id
        self._generation_id, self._key = generation_id, bytes(source_key)
        self._process_id, self._sequence = process_id, 0
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self._lock = threading.Lock()

    def publish_once(self) -> VerifiedBridgeMessage:
        with self._lock:
            observation = self._observer.observe(self._process_id)
            if type(observation) is not GamePerformanceObservation:
                raise CompanionBridgeError("game_performance_observation_invalid")
            self._sequence += 1
            encoded = encode_message(kind="observation", source_id=self._source_id,
                session_id=self._session_id, generation_id=self._generation_id,
                sequence=self._sequence, payload=observation.to_dict(), key=self._key,
                created_at=observation.observed_at or self._clock())
            return self._client.send(encoded)


class GamePerformanceBridgeDetector:
    """Consume fresh Windows performance reports from one expected bridge source."""

    def __init__(self, *, receiver: _PerformanceReceiver, source_id: str,
                 generation_provider: Callable[[], str | None],
                 clock: Callable[[], datetime] | None = None,
                 max_age_seconds: float = _MAX_AGE_SECONDS) -> None:
        if not callable(getattr(receiver, "receive", None)):
            raise CompanionBridgeError("game_performance_receiver_required")
        if not callable(generation_provider):
            raise CompanionBridgeError("game_performance_generation_provider_required")
        if (isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float))
                or not math.isfinite(float(max_age_seconds)) or not 0 < max_age_seconds <= 30):
            raise CompanionBridgeError("game_performance_ttl_invalid")
        self._receiver, self._source_id, self._generation = receiver, source_id, generation_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_age = float(max_age_seconds)

    def receive_once(self, *, timeout: float | None = 0) -> VerifiedGamePerformanceObservation:
        message = self._receiver.receive(timeout=timeout)
        if (type(message) is not VerifiedBridgeMessage or message.kind != "observation"
                or message.source_id != self._source_id
                or message.generation_id != self._generation()):
            raise CompanionBridgeError("game_performance_transport_identity_invalid")
        payload = message.payload
        required = {
            "schema_version", "status", "observed_at", "process_id_digest",
            "process_cpu_percent", "process_rss_bytes", "frame_time_source",
            "frame_time_sample_count", "frame_time_p50_ms", "frame_time_p95_ms",
            "frame_time_p99_ms", "hitch_count_over_50ms", "frame_time_digest",
            "unsupported_reasons",
        }
        if set(payload) != required:
            raise CompanionBridgeError("game_performance_payload_shape_invalid")
        if payload.get("schema_version") != _SCHEMA:
            raise CompanionBridgeError("game_performance_schema_invalid")
        process_digest = payload.get("process_id_digest")
        if not isinstance(process_digest, str) or _SHA256.fullmatch(process_digest) is None:
            raise CompanionBridgeError("game_performance_process_digest_invalid")
        observed_at = payload.get("observed_at")
        try:
            stamp = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise CompanionBridgeError("game_performance_timestamp_invalid") from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise CompanionBridgeError("game_performance_timestamp_timezone_required")
        age = (self._clock() - stamp.astimezone(timezone.utc)).total_seconds()
        if age < 0 or age > self._max_age:
            raise CompanionBridgeError("game_performance_observation_stale")
        p95 = payload.get("frame_time_p95_ms")
        cpu = payload.get("process_cpu_percent")
        rss = payload.get("process_rss_bytes")
        hitches = payload.get("hitch_count_over_50ms")
        for value, name, low, high in ((p95, "frame_p95", 0.0, 10_000.0),
                                       (cpu, "process_cpu", 0.0, 10_000.0)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(float(value)) or not low < float(value) <= high):
                raise CompanionBridgeError("game_performance_" + name + "_invalid")
        if rss is not None and (type(rss) is not int or not 0 <= rss <= 2**63 - 1):
            raise CompanionBridgeError("game_performance_process_rss_invalid")
        if hitches is not None and (type(hitches) is not int or not 0 <= hitches <= 100_000):
            raise CompanionBridgeError("game_performance_hitch_count_invalid")
        sample_count = payload.get("frame_time_sample_count")
        if type(sample_count) is not int or not 0 <= sample_count <= 100_000:
            raise CompanionBridgeError("game_performance_sample_count_invalid")
        frame_digest = payload.get("frame_time_digest")
        if frame_digest is not None and (not isinstance(frame_digest, str)
                or _SHA256.fullmatch(frame_digest) is None):
            raise CompanionBridgeError("game_performance_frame_digest_invalid")
        frame_values = (payload.get("frame_time_p50_ms"), p95,
                        payload.get("frame_time_p99_ms"), hitches)
        if (sample_count == 0 and (frame_digest is not None or any(value is not None for value in frame_values))
                or sample_count > 0 and (frame_digest is None or any(value is None for value in frame_values))):
            raise CompanionBridgeError("game_performance_frame_sample_inconsistent")
        p50, p99 = payload.get("frame_time_p50_ms"), payload.get("frame_time_p99_ms")
        if sample_count > 0:
            percentiles = (p50, p95, p99)
            if (any(isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(float(value)) or not 0 < value <= 10_000
                    for value in percentiles)
                    or not float(cast(float, p50)) <= float(cast(float, p95))
                    <= float(cast(float, p99))):
                raise CompanionBridgeError("game_performance_percentiles_invalid")
        if payload.get("frame_time_source") not in {
                "unsupported", "unavailable", "configured_presentmon_provider", "presentmon_csv"}:
            raise CompanionBridgeError("game_performance_frame_source_invalid")
        reasons = payload.get("unsupported_reasons")
        if (not isinstance(reasons, (list, tuple)) or len(reasons) > 32
                or any(not isinstance(reason, str) or len(reason) > 128 for reason in reasons)):
            raise CompanionBridgeError("game_performance_unsupported_reasons_invalid")
        status = payload.get("status")
        if status not in {"available", "partial", "unavailable", "unsupported_platform"}:
            raise CompanionBridgeError("game_performance_status_invalid")
        payload_digest = hashlib.sha256(json.dumps(dict(payload), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        return VerifiedGamePerformanceObservation(message.source_id, message.generation_id,
            message.sequence, message.message_id, payload_digest, stamp.isoformat(),
            process_digest, float(p95) if p95 is not None else None, hitches,
            float(cpu) if cpu is not None else None, rss, status)


__all__ = ["GamePerformanceBridgeDetector", "VerifiedGamePerformanceObservation",
           "WindowsGamePerformanceBridgePublisher"]
