"""Embodiment hooks for bounded sensory integrations."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping

import json

__all__ = ["EmbodimentEvent", "EmbodimentMount"]


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class EmbodimentEvent:
    """Normalized embodiment event recorded from physical or sensory feeds."""

    channel: str
    event_type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_default_now)

    def to_record(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "payload": dict(self.payload),
            "source": self.channel,
            "tags": ["embodiment", self.channel],
        }


class EmbodimentMount:
    """Manage embodiment streams, toggles, and quarantine storage."""

    _DEFAULT_CHANNELS = ("camera_feed", "audio_events", "vr_signals")

    def __init__(
        self,
        root: Path | str = Path("/embodiment"),
        *,
        channels: Iterable[str] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        active_channels = tuple(channels) if channels is not None else self._DEFAULT_CHANNELS
        self._channels: MutableMapping[str, bool] = {channel: True for channel in active_channels}
        self._locked: set[str] = set()
        self._now = now or _default_now
        self._quarantine_root = self._root / "quarantine"
        self._quarantine_root.mkdir(parents=True, exist_ok=True)
        self._quarantined: list[Dict[str, Any]] = []

    @property
    def channels(self) -> Dict[str, bool]:
        return dict(self._channels)

    @property
    def quarantined_events(self) -> list[Dict[str, Any]]:
        return list(self._quarantined)

    def is_enabled(self, channel: str) -> bool:
        self._ensure_channel(channel)
        return self._channels[channel] and channel not in self._locked

    def toggle(self, channel: str, enabled: bool) -> None:
        self._ensure_channel(channel)
        self._channels[channel] = bool(enabled)

    def lock(self, channel: str) -> None:
        self._ensure_channel(channel)
        self._locked.add(channel)

    def unlock(self, channel: str) -> None:
        self._ensure_channel(channel)
        self._locked.discard(channel)

    def ingest(
        self,
        channel: str,
        payload: Mapping[str, Any],
        *,
        event_type: str | None = None,
        timestamp: datetime | None = None,
    ) -> EmbodimentEvent:
        self._ensure_channel(channel)
        if not self._channels[channel]:
            raise PermissionError(f"Channel {channel} is disabled")
        if channel in self._locked:
            raise PermissionError(f"Channel {channel} is locked")

        event = EmbodimentEvent(
            channel=channel,
            event_type=event_type or str(payload.get("event") or payload.get("type") or "event"),
            payload=dict(payload),
            timestamp=timestamp or self._now(),
        )
        stream_path = self._root / f"{channel}.jsonl"
        with stream_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_record(), sort_keys=True) + "\n")
        return event

    def quarantine(self, record: Mapping[str, Any], *, reason: str | None = None) -> Path:
        entry = dict(record)
        entry.setdefault("timestamp", self._now().isoformat())
        if reason:
            entry.setdefault("reason", reason)
        tags = entry.get("tags")
        if not isinstance(tags, list):
            tags = [] if tags is None else [str(tags)]
        if "embodiment" not in tags:
            tags.append("embodiment")
        entry["tags"] = tags
        self._quarantined.append(entry)
        path = self._quarantine_root / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return path

    def _ensure_channel(self, channel: str) -> None:
        if channel not in self._channels:
            raise KeyError(f"Unknown embodiment channel {channel}")

