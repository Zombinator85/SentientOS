"""Utilities for broadcasting boot ceremony events to interested listeners."""
from __future__ import annotations

import logging
import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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
FORGE_EVENTS_PATH = Path("pulse/forge_events.jsonl")


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


def record_forge_event(event: dict[str, object]) -> dict[str, object]:
    """Append a structured forge event to pulse/forge_events.jsonl and in-memory history."""

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **event,
    }
    FORGE_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FORGE_EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")

    message = str(payload.get("message") or payload.get("event") or "forge_event")
    level = str(payload.get("level") or "info")
    record(message, level=level)
    return payload


def _level_for(level: str) -> int:
    mapping = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    return mapping.get(level.lower(), logging.INFO)
