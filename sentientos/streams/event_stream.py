"""Deterministic event stream substrate for append-only logs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Iterator


@dataclass(frozen=True)
class ReplayPolicy:
    max_replay_items: int
    max_replay_bytes: int | None = None
    max_lookback: int | None = None

    def clamp_limit(self, limit: int | None) -> int:
        if limit is None:
            return self.max_replay_items
        if limit <= 0:
            return 0
        return min(limit, self.max_replay_items)


@dataclass(frozen=True)
class EventEnvelope:
    stream: str
    schema_version: int
    event_id: str
    event_type: str
    timestamp: str
    payload: dict[str, object]
    digest: str | None = None

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "stream": self.stream,
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }
        if self.digest is not None:
            data["digest"] = self.digest
        return data


class EventStreamAdapter:
    """Adapter interface for deterministic replay and tailing."""

    def __init__(self, *, stream: str, schema_version: int, replay_policy: ReplayPolicy) -> None:
        self.stream = stream
        self.schema_version = schema_version
        self.replay_policy = replay_policy

    def replay(self, since_cursor: str | None, limit: int | None = None) -> list[EventEnvelope]:
        raise NotImplementedError

    def tail(
        self,
        start_cursor: str | None,
        *,
        should_stop: Callable[[], bool],
    ) -> Iterator[EventEnvelope | str]:
        raise NotImplementedError


def iter_replay(
    entries: Iterable[EventEnvelope],
    *,
    since_cursor: object | None,
    limit: int,
    cursor_key: Callable[[EventEnvelope], object],
) -> list[EventEnvelope]:
    if limit <= 0:
        return []
    items: list[EventEnvelope] = []
    for entry in entries:
        if since_cursor is not None and cursor_key(entry) <= since_cursor:
            continue
        items.append(entry)
        if len(items) >= limit:
            break
    return items
