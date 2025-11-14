"""Minimal event buffer for the persona loop."""

from __future__ import annotations

import threading
from collections import deque
from typing import Deque, Dict, Iterable, List, Mapping

_Event = Dict[str, object]

_BUFFER_LOCK = threading.Lock()
_BUFFER: Deque[_Event] = deque(maxlen=128)


def publish_event(event: Mapping[str, object]) -> None:
    """Publish an event for the persona loop to observe."""

    with _BUFFER_LOCK:
        _BUFFER.append(dict(event))


def extend_events(events: Iterable[Mapping[str, object]]) -> None:
    """Publish multiple events at once."""

    with _BUFFER_LOCK:
        for event in events:
            _BUFFER.append(dict(event))


def collect_recent_events() -> List[_Event]:
    """Return and clear the buffered persona events."""

    with _BUFFER_LOCK:
        events = list(_BUFFER)
        _BUFFER.clear()
    return events
