"""Utilities for broadcasting boot ceremony events to interested listeners."""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Deque, Dict, List

LOGGER = logging.getLogger(__name__)


@dataclass
class EventRecord:
    """Immutable record of a boot-time announcement."""

    timestamp: str
    message: str
    level: str


_HISTORY_LIMIT = 128
_HISTORY: Deque[EventRecord] = deque(maxlen=_HISTORY_LIMIT)
_LOCK = Lock()


def record(message: str, *, level: str = "info") -> EventRecord:
    """Store a boot event in memory and return the structured record."""

    normalized_level = level.lower()
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = EventRecord(timestamp=timestamp, message=message, level=normalized_level)
    with _LOCK:
        _HISTORY.append(entry)
    LOGGER.log(_level_for(normalized_level), "Boot event recorded: %s", message)
    return entry


def history() -> List[Dict[str, str]]:
    """Return the boot event history as serialisable dictionaries."""

    with _LOCK:
        return [record.__dict__.copy() for record in _HISTORY]


def clear() -> None:
    """Reset the in-memory history. Primarily used for testing."""

    with _LOCK:
        _HISTORY.clear()


def _level_for(level: str) -> int:
    mapping = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    return mapping.get(level.lower(), logging.INFO)
