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
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol, Sequence, cast

from .gaming_companion_bridge import CompanionBridgeError, VerifiedBridgeMessage, encode_message
from .windows_game_performance import GamePerformanceObservation, WindowsGamePerformanceObserver

_SCHEMA = "sentientos.game_performance_observation:v2"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_AGE_SECONDS = 10.0


class _PerformanceReceiver(Protocol):
    def receive(self, timeout: float | None = None) -> VerifiedBridgeMessage: ...


class _PerformanceSender(Protocol):
    def send(self, message: bytes) -> VerifiedBridgeMessage: ...


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
    source_observed_at: str | None = None
    process_name_digest: str | None = None


class WindowsGamePerformanceBridgePublisher:
    """Publish one observed Windows sample; uncertain sends are never replayed."""

    def __init__(self, *, observer: WindowsGamePerformanceObserver,
                 client: _PerformanceSender, source_id: str,
                 session_id: str, generation_id: str, source_key: bytes,
                 process_id: int, clock: Callable[[], str] | None = None) -> None:
        if type(observer) is not WindowsGamePerformanceObserver:
            raise CompanionBridgeError("game_performance_observer_required")
        if not callable(getattr(client, "send", None)):
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

    def publish_once(self, *, process_id: int | None = None) -> VerifiedBridgeMessage:
        with self._lock:
            selected_process_id = self._process_id if process_id is None else process_id
            if type(selected_process_id) is not int or selected_process_id < 1:
                raise CompanionBridgeError("game_process_id_invalid")
            observation = self._observer.observe(selected_process_id)
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
                 max_age_seconds: float = _MAX_AGE_SECONDS,
                 source_clock_offset_seconds: float = 0.0) -> None:
        if not callable(getattr(receiver, "receive", None)):
            raise CompanionBridgeError("game_performance_receiver_required")
        if not callable(generation_provider):
            raise CompanionBridgeError("game_performance_generation_provider_required")
        if (isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float))
                or not math.isfinite(float(max_age_seconds)) or not 0 < max_age_seconds <= 30):
            raise CompanionBridgeError("game_performance_ttl_invalid")
        if (isinstance(source_clock_offset_seconds, bool)
                or not isinstance(source_clock_offset_seconds, (int, float))
                or not math.isfinite(float(source_clock_offset_seconds))
                or abs(float(source_clock_offset_seconds)) > 30.0):
            raise CompanionBridgeError("game_performance_clock_offset_invalid")
        self._receiver, self._source_id, self._generation = receiver, source_id, generation_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_age = float(max_age_seconds)
        self._source_clock_offset = float(source_clock_offset_seconds)

    def receive_once(self, *, timeout: float | None = 0) -> VerifiedGamePerformanceObservation:
        message = self._receiver.receive(timeout=timeout)
        if (type(message) is not VerifiedBridgeMessage or message.kind != "observation"
                or message.source_id != self._source_id
                or message.generation_id != self._generation()):
            raise CompanionBridgeError("game_performance_transport_identity_invalid")
        payload = message.payload
        required = {
            "schema_version", "status", "observed_at", "process_id_digest",
            "process_name_digest",
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
        process_name_digest = payload.get("process_name_digest")
        if (process_name_digest is not None
                and (not isinstance(process_name_digest, str)
                     or _SHA256.fullmatch(process_name_digest) is None)):
            raise CompanionBridgeError("game_performance_process_name_digest_invalid")
        observed_at = payload.get("observed_at")
        try:
            stamp = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise CompanionBridgeError("game_performance_timestamp_invalid") from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise CompanionBridgeError("game_performance_timestamp_timezone_required")
        received_at = self._clock()
        if (not isinstance(received_at, datetime) or received_at.tzinfo is None
                or received_at.utcoffset() is None):
            raise CompanionBridgeError("game_performance_core_clock_invalid")
        received_at = received_at.astimezone(timezone.utc)
        source_observed_at = stamp.astimezone(timezone.utc)
        normalized_observed_at = (source_observed_at - timedelta(
            seconds=self._source_clock_offset))
        age = (received_at - normalized_observed_at).total_seconds()
        if age < 0 or age > self._max_age:
            raise CompanionBridgeError("game_performance_observation_stale")
        p95 = payload.get("frame_time_p95_ms")
        cpu = payload.get("process_cpu_percent")
        rss = payload.get("process_rss_bytes")
        hitches = payload.get("hitch_count_over_50ms")
        for value, name, low, high in ((p95, "frame_p95", 0.0, 10_000.0),
                                       (cpu, "process_cpu", 0.0, 10_000.0)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or (float(value) < low if name == "process_cpu" else float(value) <= low)
                    or float(value) > high):
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
            message.sequence, message.message_id, payload_digest,
            normalized_observed_at.isoformat(),
            process_digest, float(p95) if p95 is not None else None, hitches,
            float(cpu) if cpu is not None else None, rss, status,
            source_observed_at.isoformat(), process_name_digest)


class GamePerformanceAdmissionRuntime:
    """Continuously forward verified observations to the control-plane owner."""

    def __init__(self, *, detector: GamePerformanceBridgeDetector,
                 admission_owner: object, receive_timeout_seconds: float = 0.5) -> None:
        if type(detector) is not GamePerformanceBridgeDetector:
            raise CompanionBridgeError("game_performance_detector_required")
        observer = getattr(admission_owner, "observe_verified_game_performance", None)
        if not callable(observer):
            raise CompanionBridgeError("game_performance_admission_owner_required")
        if (isinstance(receive_timeout_seconds, bool)
                or not isinstance(receive_timeout_seconds, (int, float))
                or not math.isfinite(float(receive_timeout_seconds))
                or not 0.05 <= receive_timeout_seconds <= 5.0):
            raise CompanionBridgeError("game_performance_receive_timeout_invalid")
        self._detector = detector
        self._observe = cast(Callable[[VerifiedGamePerformanceObservation], bool], observer)
        self._receive_timeout = float(receive_timeout_seconds)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._accepted = 0
        self._rejected = 0
        self._failures = 0
        self._last_observed_at: str | None = None
        self._last_failure_code: str | None = None

    def receive_once(self, *, timeout: float | None = 0.0) -> bool:
        """Verify and forward one observation; return the owner's acceptance."""
        observation = self._detector.receive_once(timeout=timeout)
        accepted = bool(self._observe(observation))
        with self._lock:
            if accepted:
                self._accepted += 1
                self._last_observed_at = observation.observed_at
                self._last_failure_code = None
            else:
                self._rejected += 1
        return accepted

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                raise CompanionBridgeError("game_performance_runtime_already_started")
            self._stop.clear()
            self._thread = threading.Thread(target=self._run,
                name="sentientos-game-performance-admission", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.receive_once(timeout=self._receive_timeout)
            except CompanionBridgeError as exc:
                reason = str(exc.args[0]) if exc.args else "game_performance_bridge_error"
                with self._lock:
                    if reason != "bridge_receive_timeout":
                        self._failures += 1
                        self._last_failure_code = reason[:128]
            except Exception as exc:
                with self._lock:
                    self._failures += 1
                    self._last_failure_code = type(exc).__name__

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": bool(self._thread is not None
                    and self._thread.is_alive() and not self._stop.is_set()),
                "accepted_observations": self._accepted,
                "rejected_observations": self._rejected,
                "transport_failures": self._failures,
                "last_observed_at": self._last_observed_at,
                "last_failure_code": self._last_failure_code,
                "effect_authority": False,
            }

    def close(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
        if thread is None:
            return
        if thread is not threading.current_thread():
            thread.join(timeout=5.0 + self._receive_timeout)
        if thread.is_alive():
            raise CompanionBridgeError("game_performance_runtime_shutdown_timeout")
        with self._lock:
            self._thread = None


class WindowsGamePerformanceObservationPump:
    """Sample an explicitly allowlisted running game without controlling it."""

    def __init__(self, *, publisher: WindowsGamePerformanceBridgePublisher,
                 process_names: Sequence[str], interval_seconds: float = 1.0,
                 process_selector: Callable[[Sequence[str]], int | None] | None = None
                 ) -> None:
        if not callable(getattr(publisher, "publish_once", None)):
            raise CompanionBridgeError("game_performance_publisher_required")
        from .foreground_game_detection import normalize_game_process_names
        try:
            self._process_names = normalize_game_process_names(tuple(process_names))
        except (TypeError, ValueError) as exc:
            raise CompanionBridgeError("game_performance_process_allowlist_invalid") from exc
        if (isinstance(interval_seconds, bool)
                or not isinstance(interval_seconds, (int, float))
                or not math.isfinite(float(interval_seconds))
                or not 0.1 <= interval_seconds <= 60.0):
            raise CompanionBridgeError("game_performance_pump_interval_invalid")
        self._publisher = publisher
        self._interval = float(interval_seconds)
        self._selector = process_selector
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._attempts = 0
        self._published = 0
        self._no_game = 0
        self._failures = 0
        self._last_observed_at: str | None = None
        self._last_failure_code: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                raise CompanionBridgeError("game_performance_pump_already_started")
            self._stop.clear()
            self._thread = threading.Thread(target=self._run,
                name="sentientos-game-performance-observer", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        from .windows_game_performance import allowlisted_game_process_id

        while not self._stop.is_set():
            with self._lock:
                self._attempts += 1
            try:
                process_id = (self._selector(self._process_names)
                    if self._selector is not None else
                    allowlisted_game_process_id(self._process_names))
                if process_id is None:
                    with self._lock:
                        self._no_game += 1
                else:
                    message = self._publisher.publish_once(process_id=process_id)
                    with self._lock:
                        self._published += 1
                        self._last_observed_at = message.created_at
                        self._last_failure_code = None
            except Exception as exc:
                reason = (str(exc.args[0]) if exc.args
                    and isinstance(exc.args[0], str) else type(exc).__name__)
                if not reason.replace("_", "").isalnum():
                    reason = type(exc).__name__
                with self._lock:
                    self._failures += 1
                    self._last_failure_code = reason[:128]
            self._stop.wait(self._interval)

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": bool(self._thread is not None
                    and self._thread.is_alive() and not self._stop.is_set()),
                "attempts": self._attempts,
                "published": self._published,
                "no_allowlisted_game": self._no_game,
                "failures": self._failures,
                "last_observed_at": self._last_observed_at,
                "last_failure_code": self._last_failure_code,
            }

    def close(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
        if thread is None:
            return
        if thread is not threading.current_thread():
            thread.join(timeout=5.0 + self._interval)
        if thread.is_alive():
            raise CompanionBridgeError("game_performance_pump_shutdown_timeout")
        with self._lock:
            self._thread = None


__all__ = ["GamePerformanceBridgeDetector", "VerifiedGamePerformanceObservation",
           "WindowsGamePerformanceBridgePublisher", "GamePerformanceAdmissionRuntime",
           "WindowsGamePerformanceObservationPump"]
