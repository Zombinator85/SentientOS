"""In-memory pulse bus with persistent, signed history."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import logging
import os
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Deque, Dict, Iterable, Iterator, List, cast

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey
from sentientos.pulse_trust_epoch import (
    get_manager as get_trust_epoch_manager,
    reset_manager as reset_trust_epoch_manager,
)

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
_DEFAULT_RUNTIME_ROOT = Path("/glow/pulse")
_DEFAULT_SIGNING_KEY = Path("/vow/keys/ed25519_private.key")
_DEFAULT_VERIFY_KEY = Path("/vow/keys/ed25519_public.key")

_HISTORY_FILENAME = re.compile(r"pulse_(\d{4}-\d{2}-\d{2})\.jsonl$")
_INGRESS_AUDIT_FILENAME = "ingress_audit.jsonl"
_UNTRUSTED_QUARANTINE_FILENAME = "untrusted_quarantine.jsonl"
_QUARANTINE_LIMIT = max(16, int(os.getenv("PULSE_UNTRUSTED_QUARANTINE_LIMIT", "256")))


def _history_root() -> Path:
    return Path(os.getenv(_HISTORY_ROOT_ENV, str(_DEFAULT_HISTORY_ROOT)))


def _runtime_root() -> Path:
    return Path(os.getenv("PULSE_RUNTIME_ROOT", str(_DEFAULT_RUNTIME_ROOT)))


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
    payload.pop("event_hash", None)
    payload.pop("correlation_id", None)
    payload.pop("ingress_status", None)
    payload.pop("ingress_reason", None)
    payload.pop("ingress_classification", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_event_hash(event: PulseEvent) -> str:
    """Return a deterministic digest for canonical pulse event content."""

    payload = copy.deepcopy(event)
    payload.pop("signature", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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
        expected = cast(type[Any] | tuple[type[Any], ...], meta["type"])
        if not isinstance(event[field], expected):
            readable = (
                expected.__name__
                if isinstance(expected, type)
                else ", ".join(t.__name__ for t in expected)
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
        self._quarantined: Deque[PulseEvent] = deque(maxlen=_QUARANTINE_LIMIT)
        self._lock = Lock()

    def publish(self, event: PulseEvent) -> PulseEvent:
        """Publish ``event`` to all subscribers after validation."""

        normalized = self._normalize_event(event)
        normalized["source_peer"] = str(normalized.get("source_peer", "local"))
        if normalized["source_peer"] == "local":
            normalized = get_trust_epoch_manager().annotate_local_event(normalized)
        normalized["event_hash"] = str(normalized.get("event_hash") or compute_event_hash(normalized))
        normalized["correlation_id"] = str(
            normalized.get("correlation_id") or normalized["event_hash"]
        )
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
        if normalized.get("source_peer") in {None, "local"}:
            try:
                from sentientos.runtime_governor import get_runtime_governor

                get_runtime_governor().observe_pulse_event(normalized)
            except Exception:
                pass
        return copy.deepcopy(normalized)

    def ingest(
        self, event: PulseEvent, *, source_peer: str | None = None
    ) -> PulseEvent:
        return self.ingest_verified(event, source_peer=source_peer)

    def ingest_verified(
        self, event: PulseEvent, *, source_peer: str | None = None
    ) -> PulseEvent:
        if not isinstance(event, dict):
            raise TypeError("Pulse events must be dictionaries")
        signature = event.get("signature")
        if not isinstance(signature, str) or not signature:
            self.ingest_untrusted(
                event,
                source_peer=source_peer,
                reason="missing_signature",
                classification="reject",
            )
            raise ValueError("Federated pulse events require a signature")

        verification_event = copy.deepcopy(event)
        if source_peer is not None:
            verification_event["source_peer"] = str(source_peer)
        else:
            verification_event["source_peer"] = str(verification_event.get("source_peer", "remote"))
        if not verify(verification_event):
            verification_source = str(verification_event.get("source_peer", "remote"))
            self.ingest_untrusted(
                event,
                source_peer=verification_source,
                reason="signature_verification_failed",
                classification="reject",
            )
            raise ValueError("Federated pulse event signature verification failed")

        normalized = self._normalize_event(event, apply_defaults=False)
        normalized["signature"] = signature
        normalized["source_peer"] = str(verification_event["source_peer"])
        normalized["event_hash"] = str(normalized.get("event_hash") or compute_event_hash(normalized))
        normalized["correlation_id"] = str(
            normalized.get("correlation_id") or normalized["event_hash"]
        )
        normalized["ingress_status"] = "verified"
        normalized["ingress_reason"] = "signature_verified"
        normalized["ingress_classification"] = "accept"
        self._record_ingress_decision(
            normalized,
            source_peer=str(normalized["source_peer"]),
            status="verified",
            reason="signature_verified",
            classification="accept",
        )
        self._persist_event(normalized)
        with self._lock:
            stored = copy.deepcopy(normalized)
            self._events.append(stored)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            if self._should_deliver(normalized, subscriber):
                subscriber.handler(copy.deepcopy(normalized))
        try:
            from sentientos.runtime_governor import get_runtime_governor

            get_runtime_governor().observe_pulse_event(normalized)
        except Exception:
            pass
        return copy.deepcopy(normalized)

    def ingest_untrusted(
        self,
        event: PulseEvent,
        *,
        source_peer: str | None = None,
        reason: str,
        classification: str = "quarantine",
    ) -> PulseEvent:
        if not isinstance(event, dict):
            raise TypeError("Pulse events must be dictionaries")
        snapshot = copy.deepcopy(event)
        normalized_peer = str(source_peer or snapshot.get("source_peer") or "remote")
        snapshot["source_peer"] = normalized_peer
        event_hash = str(snapshot.get("event_hash") or compute_event_hash(snapshot))
        correlation_id = str(snapshot.get("correlation_id") or event_hash)
        snapshot["event_hash"] = event_hash
        snapshot["correlation_id"] = correlation_id
        snapshot["ingress_status"] = "untrusted"
        snapshot["ingress_reason"] = reason
        snapshot["ingress_classification"] = classification
        with self._lock:
            self._quarantined.append(copy.deepcopy(snapshot))
        self._record_ingress_decision(
            snapshot,
            source_peer=normalized_peer,
            status="untrusted",
            reason=reason,
            classification=classification,
        )
        return snapshot

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
            self._quarantined.clear()

    def _record_ingress_decision(
        self,
        event: PulseEvent,
        *,
        source_peer: str,
        status: str,
        reason: str,
        classification: str,
    ) -> None:
        root = _runtime_root()
        root.mkdir(parents=True, exist_ok=True)
        event_hash = str(event.get("event_hash") or compute_event_hash(event))
        correlation_id = str(event.get("correlation_id") or event_hash)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "classification": classification,
            "reason": reason,
            "source_peer": source_peer,
            "event_type": str(event.get("event_type", "")),
            "event_hash": event_hash,
            "correlation_id": correlation_id,
        }
        with (root / _INGRESS_AUDIT_FILENAME).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        if status == "untrusted":
            with (root / _UNTRUSTED_QUARANTINE_FILENAME).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({**record, "event": event}, sort_keys=True) + "\n")

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
                    if not verify(event):
                        logger.warning(
                            "Pulse history signature mismatch for entry in %s", path
                        )
                        continue
                    yield copy.deepcopy(event)
        except FileNotFoundError:  # pragma: no cover - file removed concurrently
            return

    def _normalize_event(self, event: PulseEvent, *, apply_defaults: bool = True) -> PulseEvent:
        if not isinstance(event, dict):
            raise TypeError("Pulse events must be dictionaries")
        normalized = apply_pulse_defaults(event) if apply_defaults else copy.deepcopy(event)
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

    return _BUS.ingest_verified(event, source_peer=source_peer)


def ingest_verified(event: PulseEvent, *, source_peer: str | None = None) -> PulseEvent:
    """Ingest and cryptographically verify a pre-signed pulse event."""

    return _BUS.ingest_verified(event, source_peer=source_peer)


def ingest_untrusted(
    event: PulseEvent,
    *,
    source_peer: str | None = None,
    reason: str,
    classification: str = "quarantine",
) -> PulseEvent:
    """Explicitly quarantine/reject untrusted pulse ingress without dispatching."""

    return _BUS.ingest_untrusted(
        event,
        source_peer=source_peer,
        reason=reason,
        classification=classification,
    )


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

    signature = event.get("signature")
    if not isinstance(signature, str) or not signature:
        return False

    if not _SIGNATURE_MANAGER.verify(event):
        return False

    return True


def reset() -> None:
    """Clear queued events and drop cached signing keys."""

    _BUS.reset()
    _SIGNATURE_MANAGER.reset()
    reset_trust_epoch_manager()


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
    "ingest_verified",
    "ingest_untrusted",
    "verify",
    "apply_pulse_defaults",
    "compute_event_hash",
    "reset",
]
