"""Pressure queue event stream adapter."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

from logging_config import get_log_path
from .audit_stream import follow_audit_entries, tail_audit_entries
from .event_stream import EventEnvelope, EventStreamAdapter, ReplayPolicy, iter_replay
from .schema_registry import PRESSURE_PAYLOAD_FIELDS, previous_schema_version


def _parse_cursor(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


class PressureEventStream(EventStreamAdapter):
    def __init__(
        self,
        *,
        log_path: Path | None = None,
        replay_policy: ReplayPolicy,
    ) -> None:
        resolved = log_path or get_log_path("pressure_queue.jsonl", "PRESSURE_QUEUE_LOG")
        super().__init__(stream="pressure", schema_version=previous_schema_version("pressure"), replay_policy=replay_policy)
        self.log_path = resolved

    def replay(self, since_cursor: str | None, limit: int | None = None) -> list[EventEnvelope]:
        capped = self.replay_policy.clamp_limit(limit)
        if capped <= 0:
            return []
        entries = tail_audit_entries(
            self.log_path,
            max_lines=self.replay_policy.max_replay_items,
            max_bytes=self.replay_policy.max_replay_bytes,
        )
        envelopes: list[EventEnvelope] = []
        for offset, entry in entries:
            envelope = self._to_envelope(offset, entry)
            if envelope is not None:
                envelopes.append(envelope)
        cursor_value = _parse_cursor(since_cursor)
        return iter_replay(
            envelopes,
            since_cursor=cursor_value,
            limit=capped,
            cursor_key=lambda item: int(item.event_id),
        )

    def tail(
        self,
        start_cursor: str | None,
        *,
        should_stop: Callable[[], bool],
    ) -> Iterator[EventEnvelope | str]:
        offset = _parse_cursor(start_cursor) or 0
        for item in follow_audit_entries(
            self.log_path,
            start_offset=offset,
            should_stop=should_stop,
            heartbeat="pressure-stream-ping",
        ):
            if isinstance(item, str):
                yield item
                continue
            entry_offset, entry = item
            envelope = self._to_envelope(entry_offset, entry)
            if envelope is not None:
                yield envelope

    def _to_envelope(self, offset: int, entry: dict[str, object]) -> EventEnvelope | None:
        event_type = entry.get("event")
        timestamp = entry.get("timestamp")
        if not isinstance(event_type, str) or not isinstance(timestamp, str):
            return None
        payload = {field: entry.get(field) for field in PRESSURE_PAYLOAD_FIELDS if field in entry}
        envelope = EventEnvelope(
            stream=self.stream,
            schema_version=self.schema_version,
            event_id=str(offset),
            event_type=event_type,
            timestamp=timestamp,
            payload=payload,
            digest=entry.get("digest") if isinstance(entry.get("digest"), str) else None,
        )
        return envelope


__all__ = ["PressureEventStream"]
