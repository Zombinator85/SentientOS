"""Event stream primitives for the dashboard UI."""
from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, Iterable, List, MutableMapping, Optional

import asyncio


EventDict = MutableMapping[str, object]


@dataclass(slots=True)
class Event:
    """Representation of a single dashboard event."""

    category: str
    message: str
    module: str
    metadata: Dict[str, object] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def as_dict(self) -> EventDict:
        """Return a JSON-serialisable dictionary."""
        payload: EventDict = {
            "id": self.id,
            "category": self.category,
            "message": self.message,
            "module": self.module,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
        return payload


class EventStream:
    """In-memory pub/sub stream with bounded history."""

    def __init__(self, *, categories: Iterable[str], history_limit: int = 250) -> None:
        self._categories = set(categories)
        self._history: Dict[str, Deque[Event]] = {
            category: deque(maxlen=history_limit) for category in self._categories
        }
        self._history["__all__"] = deque(maxlen=history_limit)
        self._subscribers: Dict[int, asyncio.Queue[Event]] = {}
        self._lock = threading.Lock()
        self._subscriber_index = 0
        self._history_limit = history_limit

    @property
    def categories(self) -> Iterable[str]:
        return tuple(sorted(self._categories))

    def publish(
        self,
        *,
        category: str,
        message: str,
        module: str,
        metadata: Optional[Dict[str, object]] = None,
    ) -> Event:
        if category not in self._categories:
            raise ValueError(f"Unknown category '{category}'")

        event = Event(
            category=category,
            message=message,
            module=module,
            metadata=metadata or {},
        )

        self._history[category].appendleft(event)
        self._history["__all__"].appendleft(event)

        with self._lock:
            stale_subscribers: List[int] = []
            for subscriber_id, queue in self._subscribers.items():
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    stale_subscribers.append(subscriber_id)
            for subscriber_id in stale_subscribers:
                self._subscribers.pop(subscriber_id, None)

        return event

    def get_history(self, category: str, *, limit: Optional[int] = None) -> List[EventDict]:
        if category not in self._categories:
            raise ValueError(f"Unknown category '{category}'")
        items = list(self._history[category])
        if limit is not None:
            items = items[:limit]
        return [event.as_dict() for event in items]

    def get_recent(self, *, limit: Optional[int] = None) -> List[EventDict]:
        items = list(self._history["__all__"])
        if limit is not None:
            items = items[:limit]
        return [event.as_dict() for event in items]

    def subscribe(self) -> tuple[int, asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        with self._lock:
            subscriber_id = self._subscriber_index
            self._subscriber_index += 1
            self._subscribers[subscriber_id] = queue
        return subscriber_id, queue

    def unsubscribe(self, subscriber_id: int) -> None:
        with self._lock:
            self._subscribers.pop(subscriber_id, None)
