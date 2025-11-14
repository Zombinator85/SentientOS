from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Literal

WorldEventKind = Literal[
    "message",
    "calendar",
    "system_load",
    "file_change",
    "demo_trigger",
    "heartbeat",
]


@dataclass
class WorldEvent:
    """Simple representation of an external event observed by SentientOS."""

    kind: WorldEventKind
    ts: datetime
    summary: str
    data: Dict[str, Any]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_message_event(subject: str, source: str) -> WorldEvent:
    summary = f"Message from {source}: {subject}".strip()
    payload = {"subject": subject, "source": source}
    return WorldEvent("message", _utcnow(), summary, payload)


def make_calendar_event(title: str, starts_in_minutes: int) -> WorldEvent:
    summary = f"Calendar reminder: {title} in {starts_in_minutes} minutes"
    payload = {"title": title, "starts_in_minutes": starts_in_minutes}
    return WorldEvent("calendar", _utcnow(), summary, payload)


def make_system_load_event(level: Literal["low", "medium", "high"]) -> WorldEvent:
    summary = f"System load {level}"
    payload = {"level": level}
    return WorldEvent("system_load", _utcnow(), summary, payload)


def make_demo_trigger_event(name: str) -> WorldEvent:
    summary = f"Trigger demo: {name}"
    payload = {"demo_name": name}
    return WorldEvent("demo_trigger", _utcnow(), summary, payload)
