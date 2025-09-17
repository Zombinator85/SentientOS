"""In-memory event bus allowing daemons to broadcast live pulse updates."""

from __future__ import annotations

import copy
from collections import deque
from threading import Lock
from typing import Callable, Deque, Dict, Iterable, List

PulseEvent = Dict[str, object]
EventHandler = Callable[[PulseEvent], None]

_REQUIRED_FIELDS = {"timestamp", "source_daemon", "event_type", "payload"}


class PulseSubscription:
    """Represents a registered handler on the :mod:`pulse_bus`."""

    def __init__(self, bus: "_PulseBus", handler: EventHandler) -> None:
        self._bus = bus
        self._handler = handler
        self._active = True

    @property
    def active(self) -> bool:
        """Return whether the subscription is currently active."""

        return self._active

    def unsubscribe(self) -> None:
        """Detach the underlying handler from the pulse bus."""

        if self._active:
            self._bus._unsubscribe(self._handler)
            self._active = False


class _PulseBus:
    """Simple publish/subscribe bus backed by an in-memory queue."""

    def __init__(self) -> None:
        self._events: Deque[PulseEvent] = deque()
        self._subscribers: List[EventHandler] = []
        self._lock = Lock()

    def publish(self, event: PulseEvent) -> PulseEvent:
        """Publish ``event`` to all subscribers after validation."""

        normalized = self._normalize_event(event)
        with self._lock:
            self._events.append(normalized)
            subscribers = list(self._subscribers)
        for handler in subscribers:
            handler(copy.deepcopy(normalized))
        return copy.deepcopy(normalized)

    def subscribe(self, handler: EventHandler) -> PulseSubscription:
        """Register ``handler`` and replay pending events immediately."""

        if not callable(handler):  # pragma: no cover - defensive branch
            raise TypeError("Pulse handlers must be callable")

        with self._lock:
            self._subscribers.append(handler)
            replay = [copy.deepcopy(evt) for evt in self._events]
        for event in replay:
            handler(event)
        return PulseSubscription(self, handler)

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

    def _normalize_event(self, event: PulseEvent) -> PulseEvent:
        if not isinstance(event, dict):
            raise TypeError("Pulse events must be dictionaries")
        normalized = copy.deepcopy(event)
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
        return normalized

    def _unsubscribe(self, handler: EventHandler) -> None:
        with self._lock:
            self._subscribers = [h for h in self._subscribers if h is not handler]


_BUS = _PulseBus()


def publish(event: PulseEvent) -> PulseEvent:
    """Publish ``event`` to the global pulse bus."""

    return _BUS.publish(event)


def subscribe(handler: EventHandler) -> PulseSubscription:
    """Subscribe ``handler`` to receive future pulse events."""

    return _BUS.subscribe(handler)


def pending_events() -> List[PulseEvent]:
    """Return a copy of queued pulse events without removing them."""

    return _BUS.pending_events()


def consume_events(count: int | None = None) -> List[PulseEvent]:
    """Remove and return up to ``count`` events from the queue."""

    return _BUS.consume(count)


def reset() -> None:
    """Clear all queued events and registered subscribers."""

    _BUS.reset()


__all__ = [
    "PulseEvent",
    "PulseSubscription",
    "publish",
    "subscribe",
    "pending_events",
    "consume_events",
    "reset",
]
