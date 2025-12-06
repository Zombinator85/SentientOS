"""In-memory pulse bus with persistent, signed history."""

from __future__ import annotations

import base64
import copy
import json
import logging
import os
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Callable, Deque, Dict, Iterable, Iterator, List

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

PulseEvent = Dict[str, object]
EventHandler = Callable[[PulseEvent], None]

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {"timestamp", "source_daemon", "event_type", "payload"}
_VALID_PRIORITIES = {"info", "warning", "critical"}
_DEFAULT_PRIORITY = "info"

PULSE_V2_SCHEMA: Dict[str, Dict[str, object]] = {
    "focus": {
        "type": (str, type(None)),
        "description": "Optional attention target identifier.",
        "default": None,
    },
    "context": {
        "type": dict,
        "description": "Arbitration-provided contextual metadata.",
        "default": dict,
    },
    "internal_priority": {
        "type": (str, int, float, type(None)),
        "description": "Internal ordering hint separate from external priority.",
        "default": "baseline",
    },
    "event_origin": {
        "type": str,
        "description": "Origin hint for arbitration and auditing.",
        "default": "local",
    },
}

_HISTORY_ROOT_ENV = "PULSE_HISTORY_ROOT"
_SIGNING_KEY_ENV = "PULSE_SIGNING_KEY"
_VERIFY_KEY_ENV = "PULSE_VERIFY_KEY"

_DEFAULT_HISTORY_ROOT = Path("/glow/pulse_history")
_DEFAULT_SIGNING_KEY = Path("/vow/keys/ed25519_private.key")
_DEFAULT_VERIFY_KEY = Path("/vow/keys/ed25519_public.key")

_HISTORY_FILENAME = re.compile(r"pulse_(\d{4}-\d{2}-\d{2})\.jsonl$")


def _history_root() -> Path:
    return Path(os.getenv(_HISTORY_ROOT_ENV, str(_DEFAULT_HISTORY_ROOT)))


def _signing_key_path() -> Path:
    return Path(os.getenv(_SIGNING_KEY_ENV, str(_DEFAULT_SIGNING_KEY)))


def _verify_key_path() -> Path:
    return Path(os.getenv(_VERIFY_KEY_ENV, str(_DEFAULT_VERIFY_KEY)))


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_day(timestamp: str) -> str:
    return _parse_timestamp(timestamp).date().isoformat()


def _serialize_for_signature(event: PulseEvent) -> bytes:
    payload = copy.deepcopy(event)
    payload.pop("signature", None)
    payload.pop("source_peer", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def apply_pulse_defaults(event: PulseEvent) -> PulseEvent:
    """Apply Pulse Bus 2.0 defaults without overwriting existing keys."""

    enriched = copy.deepcopy(event)
    for field, meta in PULSE_V2_SCHEMA.items():
        if field not in enriched:
            default_value = meta["default"]
            enriched[field] = default_value() if callable(default_value) else copy.deepcopy(default_value)
    return enriched


def _validate_extended_fields(event: PulseEvent) -> None:
    for field, meta in PULSE_V2_SCHEMA.items():
        if field not in event:
            continue
        expected = meta["type"]
        if not isinstance(event[field], expected):
            readable = (
                expected.__name__
                if isinstance(expected, type)
                else ", ".join(t.__name__ for t in expected)  # type: ignore[arg-type]
            )
            raise TypeError(f"Pulse field '{field}' must be of type {readable}")


class _SignatureManager:
    def __init__(self) -> None:
        self._signing_key: SigningKey | None = None
        self._verify_key: VerifyKey | None = None

    def reset(self) -> None:
        self._signing_key = None
        self._verify_key = None

    def sign(self, event: PulseEvent) -> str:
        signing_key = self._load_signing_key()
        signature = signing_key.sign(_serialize_for_signature(event)).signature
        return base64.b64encode(signature).decode("ascii")

    def verify(self, event: PulseEvent) -> bool:
        signature = event.get("signature")
        if not isinstance(signature, str) or not signature:
            return False
        verify_key = self._load_verify_key()
        if verify_key is None:
            return False
        try:
            verify_key.verify(
                _serialize_for_signature(event),
                base64.b64decode(signature),
            )
            return True
        except BadSignatureError:
            return False

    def _load_signing_key(self) -> SigningKey:
        if self._signing_key is not None:
            return self._signing_key
        key_path = _signing_key_path()
        try:
            data = key_path.read_bytes()
        except FileNotFoundError as exc:  # pragma: no cover - misconfiguration
            raise RuntimeError(
                f"Pulse signing key missing at {key_path}. "
                "Provision the integrity envelope key before publishing events."
            ) from exc
        self._signing_key = SigningKey(data)
        self._verify_key = self._signing_key.verify_key
        return self._signing_key

    def _load_verify_key(self) -> VerifyKey | None:
        if self._verify_key is not None:
            return self._verify_key
        verify_path = _verify_key_path()
        if verify_path.exists():
            self._verify_key = VerifyKey(verify_path.read_bytes())
            return self._verify_key
        try:
            return self._load_signing_key().verify_key
        except RuntimeError:  # pragma: no cover - surfaces missing key early
            return None


_SIGNATURE_MANAGER = _SignatureManager()


class _Subscriber:
    __slots__ = ("handler", "priorities")

    def __init__(self, handler: EventHandler, priorities: frozenset[str] | None) -> None:
        self.handler = handler
        self.priorities = priorities


class PulseSubscription:
    """Represents a registered handler on the :mod:`pulse_bus`."""

    def __init__(self, bus: "_PulseBus", subscriber: _Subscriber) -> None:
        self._bus = bus
        self._subscriber = subscriber
        self._active = True

    @property
    def active(self) -> bool:
        """Return whether the subscription is currently active."""

        return self._active

    def unsubscribe(self) -> None:
        """Detach the underlying handler from the pulse bus."""

        if self._active:
            self._bus._unsubscribe(self._subscriber)
            self._active = False


class _PulseBus:
    """Publish/subscribe bus with append-only persisted history."""

    def __init__(self) -> None:
        self._events: Deque[PulseEvent] = deque()
        self._subscribers: List[_Subscriber] = []
        self._lock = Lock()

    def publish(self, event: PulseEvent) -> PulseEvent:
        """Publish ``event`` to all subscribers after validation."""

        normalized = self._normalize_event(event)
        normalized["source_peer"] = str(normalized.get("source_peer", "local"))
        signature = _SIGNATURE_MANAGER.sign(normalized)
        normalized["signature"] = signature
        self._persist_event(normalized)
        with self._lock:
            stored = copy.deepcopy(normalized)
            self._events.append(stored)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            if self._should_deliver(normalized, subscriber):
                subscriber.handler(copy.deepcopy(normalized))
        return copy.deepcopy(normalized)

    def ingest(
        self, event: PulseEvent, *, source_peer: str | None = None
    ) -> PulseEvent:
        if not isinstance(event, dict):
            raise TypeError("Pulse events must be dictionaries")
        normalized = self._normalize_event(event)
        signature = event.get("signature")
        if not isinstance(signature, str) or not signature:
            raise ValueError("Federated pulse events require a signature")
        normalized["signature"] = signature
        if source_peer is not None:
            normalized["source_peer"] = str(source_peer)
        else:
            normalized["source_peer"] = str(normalized.get("source_peer", "remote"))
        self._persist_event(normalized)
        with self._lock:
            stored = copy.deepcopy(normalized)
            self._events.append(stored)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            if self._should_deliver(normalized, subscriber):
                subscriber.handler(copy.deepcopy(normalized))
        return copy.deepcopy(normalized)

    def replay(self, since: datetime | None = None) -> Iterator[PulseEvent]:
        cutoff = _ensure_utc(since) if since is not None else None
        for path in self._history_files(cutoff):
            yield from self._replay_file(path, cutoff)

    def subscribe(
        self, handler: EventHandler, priorities: Iterable[str] | None = None
    ) -> PulseSubscription:
        """Register ``handler`` and replay pending events immediately.

        Parameters
        ----------
        handler:
            Callable invoked for each delivered pulse event.
        priorities:
            Optional iterable of accepted priority levels. When provided,
            only events whose ``priority`` matches one of these levels will be
            delivered to ``handler``.
        """

        if not callable(handler):  # pragma: no cover - defensive branch
            raise TypeError("Pulse handlers must be callable")

        priority_filter = self._normalize_priorities(priorities)
        subscriber = _Subscriber(handler, priority_filter)

        with self._lock:
            self._subscribers.append(subscriber)
            replay = [
                copy.deepcopy(evt)
                for evt in self._events
                if self._should_deliver(evt, subscriber)
            ]
        for event in replay:
            handler(event)
        return PulseSubscription(self, subscriber)

    def pending_events(self) -> List[PulseEvent]:
        """Return a snapshot of queued events without consuming them."""

        with self._lock:
            return [copy.deepcopy(evt) for evt in self._events]

    def consume(self, count: int | None = None) -> List[PulseEvent]:
        """Remove and return up to ``count`` events from the queue."""

        with self._lock:
            if count is None or count >= len(self._events):
                events: Iterable[PulseEvent] = list(self._events)
                self._events.clear()
            else:
                events = [self._events.popleft() for _ in range(count)]
        return [copy.deepcopy(evt) for evt in events]

    def reset(self) -> None:
        """Clear the queue and any registered subscribers."""

        with self._lock:
            self._events.clear()
            self._subscribers.clear()

    def _persist_event(self, event: PulseEvent) -> None:
        history_root = _history_root()
        history_root.mkdir(parents=True, exist_ok=True)
        filename = history_root / f"pulse_{_event_day(str(event['timestamp']))}.jsonl"
        with filename.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _history_files(self, cutoff: datetime | None) -> List[Path]:
        root = _history_root()
        if not root.exists():
            return []
        files = sorted(path for path in root.glob("pulse_*.jsonl") if path.is_file())
        if cutoff is None:
            return files
        cutoff_date = cutoff.date()
        filtered: List[Path] = []
        for path in files:
            match = _HISTORY_FILENAME.match(path.name)
            if not match:
                continue
            try:
                file_date = datetime.fromisoformat(match.group(1)).date()
            except ValueError:
                continue
            if file_date < cutoff_date:
                continue
            filtered.append(path)
        return filtered

    def _replay_file(
        self, path: Path, cutoff: datetime | None
    ) -> Iterator[PulseEvent]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed pulse history entry in %s", path)
                        continue
                    if not isinstance(event, dict):
                        continue
                    if cutoff is not None:
                        event_ts = _parse_timestamp(str(event.get("timestamp", "")))
                        if event_ts < cutoff:
                            continue
                    if not _SIGNATURE_MANAGER.verify(event):
                        logger.warning(
                            "Pulse history signature mismatch for entry in %s", path
                        )
                        continue
                    yield copy.deepcopy(event)
        except FileNotFoundError:  # pragma: no cover - file removed concurrently
            return

    def _normalize_event(self, event: PulseEvent) -> PulseEvent:
        if not isinstance(event, dict):
            raise TypeError("Pulse events must be dictionaries")
        normalized = apply_pulse_defaults(event)
        normalized.pop("signature", None)
        missing = _REQUIRED_FIELDS - normalized.keys()
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Pulse events require fields: {missing_list}")
        payload = normalized.get("payload")
        if not isinstance(payload, dict):
            raise TypeError("Pulse event payload must be a dictionary")
        timestamp = normalized.get("timestamp")
        if not isinstance(timestamp, str):
            normalized["timestamp"] = str(timestamp)
        normalized["source_daemon"] = str(normalized["source_daemon"])
        normalized["event_type"] = str(normalized["event_type"])
        _validate_extended_fields(normalized)
        priority_value = normalized.get("priority", _DEFAULT_PRIORITY)
        if isinstance(priority_value, str):
            priority_value = priority_value.lower()
        else:
            priority_value = str(priority_value).lower()
        if priority_value not in _VALID_PRIORITIES:
            valid = ", ".join(sorted(_VALID_PRIORITIES))
            raise ValueError(
                f"Pulse event priority must be one of: {valid}"
            )
        normalized["priority"] = priority_value
        return normalized

    def _unsubscribe(self, subscriber: _Subscriber) -> None:
        with self._lock:
            self._subscribers = [
                registered for registered in self._subscribers if registered is not subscriber
            ]

    def _normalize_priorities(
        self, priorities: Iterable[str] | None
    ) -> frozenset[str] | None:
        if priorities is None:
            return None
        if isinstance(priorities, str):
            values = [priorities]
        else:
            values = list(priorities)
        normalized: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                raise TypeError("Pulse subscription priorities must be strings")
            priority = value.lower()
            if priority not in _VALID_PRIORITIES:
                valid = ", ".join(sorted(_VALID_PRIORITIES))
                raise ValueError(
                    f"Pulse subscription priorities must be within: {valid}"
                )
            normalized.add(priority)
        return frozenset(normalized)

    def _should_deliver(self, event: PulseEvent, subscriber: _Subscriber) -> bool:
        if subscriber.priorities is None:
            return True
        priority = str(event.get("priority", _DEFAULT_PRIORITY)).lower()
        return priority in subscriber.priorities


_BUS = _PulseBus()


def publish(event: PulseEvent) -> PulseEvent:
    """Publish ``event`` to the global pulse bus."""

    return _BUS.publish(event)


def ingest(event: PulseEvent, *, source_peer: str | None = None) -> PulseEvent:
    """Ingest a pre-signed pulse event from a remote peer."""

    return _BUS.ingest(event, source_peer=source_peer)


def replay(since: datetime | None = None) -> Iterator[PulseEvent]:
    """Replay verified events from persistent history."""

    return _BUS.replay(since)


def subscribe(
    handler: EventHandler, priorities: Iterable[str] | None = None
) -> PulseSubscription:
    """Subscribe ``handler`` to receive future pulse events.

    Parameters
    ----------
    handler:
        Callable invoked for each delivered pulse event.
    priorities:
        Optional iterable of priority levels to filter delivered events. When
        omitted, the subscriber receives all events regardless of priority.
    """

    return _BUS.subscribe(handler, priorities)


def pending_events() -> List[PulseEvent]:
    """Return a copy of queued pulse events without removing them."""

    return _BUS.pending_events()


def consume_events(count: int | None = None) -> List[PulseEvent]:
    """Remove and return up to ``count`` events from the queue."""

    return _BUS.consume(count)


def verify(event: PulseEvent) -> bool:
    """Verify the signature of a pulse event."""

    source_peer = event.get("source_peer")
    if source_peer not in (None, "local"):
        try:
            from . import pulse_federation
        except ImportError:  # pragma: no cover - optional federation support
            return False
        return pulse_federation.verify_remote_signature(event, str(source_peer))

    return _SIGNATURE_MANAGER.verify(event)


def reset() -> None:
    """Clear queued events and drop cached signing keys."""

    _BUS.reset()
    _SIGNATURE_MANAGER.reset()


__all__ = [
    "PulseEvent",
    "PULSE_V2_SCHEMA",
    "PulseSubscription",
    "publish",
    "replay",
    "subscribe",
    "pending_events",
    "consume_events",
    "ingest",
    "verify",
    "apply_pulse_defaults",
    "reset",
]
