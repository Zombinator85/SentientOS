"""Bind Windows foreground observations to SentientOS automatic workload mode."""
from __future__ import annotations

import hashlib
import math
import re
import threading
from dataclasses import dataclass
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
    CompanionBridgeTransportError,
)
from .game_performance_bridge import (
    GamePerformanceBridgeDetector, VerifiedGamePerformanceObservation,
)
from .gaming_companion_supervisor import CompanionBridgeSupervisor

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


class _SingleVerifiedMessageReceiver:
    """Present one already-authenticated bridge envelope to its schema parser."""

    def __init__(self, message: VerifiedBridgeMessage) -> None:
        self._message: VerifiedBridgeMessage | None = message

    def receive(self, timeout: float | None = None) -> VerifiedBridgeMessage:
        del timeout
        message, self._message = self._message, None
        if message is None:
            raise CompanionBridgeError("bridge_receive_timeout")
        return message


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
                     "game_process_running": None, "running_process_name_digests": None,
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


@dataclass(frozen=True, slots=True)
class ForegroundPublisherStatus:
    running: bool
    attempts: int
    acknowledgments: int
    failures: int
    last_attempt_at: str | None
    last_acknowledged_at: str | None
    last_message_id: str | None
    last_failure_code: str | None
    last_failure_delivery_state: str | None
    last_failure_at: str | None
    last_delivery_state: str | None


class WindowsForegroundObservationPump:
    """Supervise bounded periodic samples without replaying uncertain sends."""

    _JOIN_TIMEOUT_SECONDS = 35.0

    def __init__(self, *, publisher: WindowsForegroundBridgePublisher,
                 process_names: tuple[str, ...] | list[str], interval_seconds: float = 1.0) -> None:
        if type(publisher) is not WindowsForegroundBridgePublisher:
            raise CompanionBridgeError("foreground_bridge_publisher_required")
        if (isinstance(interval_seconds, bool)
                or not isinstance(interval_seconds, (int, float))
                or not math.isfinite(float(interval_seconds))
                or not 0.1 <= interval_seconds <= 60.0):
            raise CompanionBridgeError("foreground_publisher_interval_invalid")
        self._publisher = publisher
        self._process_names = normalize_game_process_names(process_names)
        self._interval = float(interval_seconds)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_once = False
        self._attempts = 0
        self._acknowledgments = 0
        self._failures = 0
        self._last_attempt_at: str | None = None
        self._last_acknowledged_at: str | None = None
        self._last_message_id: str | None = None
        self._last_failure_code: str | None = None
        self._last_failure_delivery_state: str | None = None
        self._last_failure_at: str | None = None
        self._last_delivery_state: str | None = None

    def start(self) -> None:
        """Start immediate sampling followed by fixed-interval fresh samples."""
        with self._lock:
            if self._started_once:
                raise CompanionBridgeError("foreground_publisher_generation_rotation_required")
            self._started_once = True
            self._stop.clear()
            self._thread = threading.Thread(target=self._run,
                name="sentientos-foreground-observer", daemon=True)
            self._thread.start()

    def close(self) -> None:
        """Stop sampling and wait for any bounded in-flight loopback request."""
        with self._lock:
            thread = self._thread
            self._stop.set()
        if thread is None:
            return
        if thread is not threading.current_thread():
            thread.join(timeout=self._JOIN_TIMEOUT_SECONDS)
        if thread.is_alive():
            raise CompanionBridgeError("foreground_publisher_shutdown_timeout")
        with self._lock:
            self._thread = None

    def status(self) -> ForegroundPublisherStatus:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive() and not self._stop.is_set()
            return ForegroundPublisherStatus(running, self._attempts, self._acknowledgments,
                self._failures, self._last_attempt_at, self._last_acknowledged_at,
                self._last_message_id, self._last_failure_code,
                self._last_failure_delivery_state, self._last_failure_at,
                self._last_delivery_state)

    def _run(self) -> None:
        while not self._stop.is_set():
            attempted_at = datetime.now(timezone.utc).isoformat()
            with self._lock:
                self._attempts += 1
                self._last_attempt_at = attempted_at
            try:
                acknowledgment = self._publisher.publish_once(self._process_names)
            except CompanionBridgeTransportError as exc:
                with self._lock:
                    self._failures += 1
                    self._last_failure_code = exc.code
                    self._last_failure_delivery_state = exc.delivery_state
                    self._last_failure_at = attempted_at
                    self._last_delivery_state = exc.delivery_state
            except CompanionBridgeError as exc:
                code = str(exc.args[0]) if exc.args else "foreground_publication_failed"
                with self._lock:
                    self._failures += 1
                    self._last_failure_code = code[:128]
                    self._last_failure_delivery_state = "unknown"
                    self._last_failure_at = attempted_at
                    self._last_delivery_state = "unknown"
            except Exception:
                with self._lock:
                    self._failures += 1
                    self._last_failure_code = "foreground_publication_failed"
                    self._last_failure_delivery_state = "unknown"
                    self._last_failure_at = attempted_at
                    self._last_delivery_state = "unknown"
            else:
                with self._lock:
                    self._acknowledgments += 1
                    self._last_acknowledged_at = acknowledgment.created_at
                    self._last_message_id = acknowledgment.payload.get("message_id")
                    self._last_delivery_state = "accepted"
            self._stop.wait(self._interval)


class BridgeForegroundGameDetector:
    """Consume verified Windows samples and fail conservatively when they expire."""

    def __init__(self, *, runtime: CompanionBridgeLoopbackRuntime | CompanionBridgeSupervisor,
                 source_id: str, generation_id: str | None = None,
                 clock: Callable[[], datetime] | None = None,
                 max_observation_age_seconds: float = 5.0) -> None:
        if not isinstance(runtime, (CompanionBridgeLoopbackRuntime, CompanionBridgeSupervisor)):
            raise CompanionBridgeError("bridge_runtime_or_supervisor_required")
        if isinstance(runtime, CompanionBridgeSupervisor):
            if generation_id is not None and generation_id != runtime.generation_id:
                raise CompanionBridgeError("bridge_supervisor_generation_mismatch")
            self._generation_provider = lambda: runtime.generation_id
        elif not isinstance(generation_id, str) or not generation_id:
            raise CompanionBridgeError("bridge_generation_id_required")
        else:
            self._generation_provider = lambda: generation_id
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
        self._game_performance_observer: Callable[
            [VerifiedGamePerformanceObservation], bool] | None = None

    def set_game_performance_admission_owner(self, owner: object) -> None:
        """Bind verified performance samples to the existing scheduling owner."""
        observer = getattr(owner, "observe_verified_game_performance", None)
        if not callable(observer):
            raise CompanionBridgeError("game_performance_admission_owner_required")
        self._game_performance_observer = observer

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
                if (message.kind == "observation"
                        and message.payload.get("schema_version") ==
                            "sentientos.game_performance_observation:v1"):
                    self._forward_game_performance(message)
                    continue
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

    def _forward_game_performance(self, message: VerifiedBridgeMessage) -> bool:
        observer = self._game_performance_observer
        if observer is None:
            return False
        generation_id = self._generation_provider()
        try:
            observation = GamePerformanceBridgeDetector(
                receiver=_SingleVerifiedMessageReceiver(message),
                source_id=self._source_id,
                generation_provider=lambda: generation_id,
                clock=self._clock,
                max_age_seconds=min(10.0, self._max_age),
            ).receive_once(timeout=0.0)
            return bool(observer(observation))
        except (CompanionBridgeError, TypeError, ValueError, OverflowError):
            return False

    def _parse(self, message: VerifiedBridgeMessage,
               allowed_digests: set[str]) -> ForegroundGameObservation | None:
        generation_id = self._generation_provider()
        if (message.kind != "observation" or message.source_id != self._source_id
                or not isinstance(generation_id, str) or message.generation_id != generation_id):
            return None
        payload = message.payload
        required = {"schema_version", "status", "game_foreground",
                    "process_name_digest", "game_process_running",
                    "running_process_name_digests", "observed_at"}
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
            running = payload.get("game_process_running")
            running_value = payload.get("running_process_name_digests")
            running_digests = None
            if running is None and running_value is None:
                pass
            elif (type(running) is not bool or not isinstance(running_value, list)
                  or len(running_value) > len(allowed_digests)
                  or any(not isinstance(item, str) or _DIGEST.fullmatch(item) is None
                         or item not in allowed_digests for item in running_value)
                  or len(set(running_value)) != len(running_value)
                  or running != bool(running_value)):
                return None
            else:
                running_digests = tuple(running_value)
            return ForegroundGameObservation("available", foreground, digest, observed_at,
                transport_provenance=provenance, game_process_running=running,
                running_process_name_digests=running_digests)
        if status not in _ALLOWED_FAILURES:
            return None
        if any(payload.get(key) is not None for key in (
                "game_foreground", "process_name_digest", "game_process_running",
                "running_process_name_digests")):
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
