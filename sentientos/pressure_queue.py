from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from logging_config import get_log_path
from log_utils import append_json, read_json


@dataclass(frozen=True)
class PressureQueueEvent:
    event: str
    digest: str
    signal_type: str
    as_of_date: str | None
    window_days: int
    severity: str
    counts: Mapping[str, int]
    source: str
    enqueued_at: str
    actor: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload = {
            "event": self.event,
            "digest": self.digest,
            "signal_type": self.signal_type,
            "as_of_date": self.as_of_date,
            "window_days": self.window_days,
            "severity": self.severity,
            "counts": dict(self.counts),
            "source": self.source,
            "enqueued_at": self.enqueued_at,
        }
        if self.actor is not None:
            payload["actor"] = self.actor
        return payload


DEFAULT_PRESSURE_QUEUE_LOG = get_log_path("pressure_queue.jsonl", "PRESSURE_QUEUE_LOG")


def _resolve_log_path(log_path: Path | None) -> Path:
    return log_path or get_log_path("pressure_queue.jsonl", "PRESSURE_QUEUE_LOG")


def read_pressure_queue(log_path: Path | None = None) -> list[dict[str, object]]:
    path = _resolve_log_path(log_path)
    return read_json(path)


def enqueue_pressure_signal(
    signal: Mapping[str, object],
    *,
    log_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, object] | None:
    digest = signal.get("digest")
    if not isinstance(digest, str) or not digest:
        raise ValueError("pressure signal digest must be a non-empty string")
    path = _resolve_log_path(log_path)
    if _digest_seen(digest, read_pressure_queue(path)):
        return None
    enqueued_at = (now or datetime.now(timezone.utc)).isoformat()
    event = PressureQueueEvent(
        event="pressure_enqueue",
        digest=digest,
        signal_type=str(signal.get("signal_type", "")),
        as_of_date=signal.get("as_of_date") if isinstance(signal.get("as_of_date"), str) else None,
        window_days=int(signal.get("window_days", 0) or 0),
        severity=str(signal.get("severity", "")),
        counts=_coerce_counts(signal.get("counts")),
        source=str(signal.get("source", "")),
        enqueued_at=enqueued_at,
    )
    entry = event.to_payload()
    append_json(path, entry)
    return entry


def acknowledge_pressure_signal(
    digest: str,
    *,
    actor: str | None = None,
    log_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    if not isinstance(digest, str) or not digest:
        raise ValueError("pressure signal digest must be a non-empty string")
    path = _resolve_log_path(log_path)
    enqueued_at = (now or datetime.now(timezone.utc)).isoformat()
    event = PressureQueueEvent(
        event="pressure_acknowledged",
        digest=digest,
        signal_type="",
        as_of_date=None,
        window_days=0,
        severity="",
        counts={},
        source="",
        enqueued_at=enqueued_at,
        actor=actor or "unspecified",
    )
    entry = event.to_payload()
    append_json(path, entry)
    return entry


def _digest_seen(digest: str, entries: Iterable[Mapping[str, object]]) -> bool:
    return any(
        entry.get("event") == "pressure_enqueue" and entry.get("digest") == digest
        for entry in entries
    )


def _coerce_counts(counts: object) -> dict[str, int]:
    if not isinstance(counts, Mapping):
        return {}
    coerced: dict[str, int] = {}
    for key, value in counts.items():
        if not isinstance(key, str):
            continue
        try:
            coerced[key] = int(value)
        except (TypeError, ValueError):
            coerced[key] = 0
    return coerced


__all__ = [
    "DEFAULT_PRESSURE_QUEUE_LOG",
    "PressureQueueEvent",
    "acknowledge_pressure_signal",
    "enqueue_pressure_signal",
    "read_pressure_queue",
]
