from __future__ import annotations

from collections import deque
from datetime import datetime
from threading import Lock
from typing import Deque, Dict, List, Optional

from .events import WorldEvent


class WorldEventBus:
    """Thread-safe in-memory buffer for world events."""

    def __init__(self, max_events: int = 200) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        self._events: Deque[WorldEvent] = deque(maxlen=max_events)
        self._lock = Lock()

    def push(self, event: WorldEvent) -> None:
        with self._lock:
            self._events.append(event)

    def drain_since(self, last_ts: Optional[datetime]) -> List[WorldEvent]:
        with self._lock:
            snapshot = list(self._events)
        if last_ts is None:
            return sorted(snapshot, key=lambda event: event.ts)
        return sorted((event for event in snapshot if event.ts > last_ts), key=lambda event: event.ts)


def world_events_to_persona_pulse(events: List[WorldEvent]) -> List[Dict[str, object]]:
    """Convert world events into persona-friendly pulse dictionaries."""

    pulses: List[Dict[str, object]] = []
    for event in events:
        pulses.append(
            {
                "kind": "world",
                "world_kind": event.kind,
                "summary": event.summary,
                "ts": event.ts.isoformat(),
                "data": dict(event.data),
            }
        )
    return pulses
