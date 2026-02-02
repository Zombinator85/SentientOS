from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping

from logging_config import get_log_path
from log_utils import append_json, read_json

PRESSURE_SIGNAL_STATUSES = ("open", "acknowledged", "closed", "expired")
PRESSURE_CLOSURE_REASONS = (
    "resolved",
    "superseded",
    "invalid",
    "duplicate",
    "no_longer_applicable",
    "expired",
    "operator_close",
)
PRESSURE_SEVERITY_ORDER = ("none", "low", "medium", "high")
PRESSURE_PERSISTENCE_ESCALATION_REVIEWS = 3
PRESSURE_CLOSURE_NOTE_LIMIT = 240
PRESSURE_REVIEW_POLICY: Mapping[str, Mapping[str, timedelta]] = {
    "default": {
        "none": timedelta(days=14),
        "low": timedelta(days=7),
        "medium": timedelta(days=3),
        "high": timedelta(days=1),
    },
    "drift": {
        "none": timedelta(days=14),
        "low": timedelta(days=5),
        "medium": timedelta(days=2),
        "high": timedelta(days=1),
    },
}


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
    created_at: str | None = None
    last_reviewed_at: str | None = None
    next_review_due_at: str | None = None
    status: str | None = None
    closure_reason: str | None = None
    closure_note: str | None = None
    review_count: int | None = None
    persistence_count: int | None = None
    reviewed_at: str | None = None
    closed_at: str | None = None
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
        if self.created_at is not None:
            payload["created_at"] = self.created_at
        if self.last_reviewed_at is not None:
            payload["last_reviewed_at"] = self.last_reviewed_at
        if self.next_review_due_at is not None:
            payload["next_review_due_at"] = self.next_review_due_at
        if self.status is not None:
            payload["status"] = self.status
        if self.closure_reason is not None:
            payload["closure_reason"] = self.closure_reason
        if self.closure_note is not None:
            payload["closure_note"] = self.closure_note
        if self.review_count is not None:
            payload["review_count"] = self.review_count
        if self.persistence_count is not None:
            payload["persistence_count"] = self.persistence_count
        if self.reviewed_at is not None:
            payload["reviewed_at"] = self.reviewed_at
        if self.closed_at is not None:
            payload["closed_at"] = self.closed_at
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
    created_at = _coerce_datetime(now).isoformat()
    next_review_due_at = _compute_next_review_due_at(
        created_at,
        signal_type=str(signal.get("signal_type", "")),
        severity=str(signal.get("severity", "")),
    )
    event = PressureQueueEvent(
        event="pressure_enqueue",
        digest=digest,
        signal_type=str(signal.get("signal_type", "")),
        as_of_date=signal.get("as_of_date") if isinstance(signal.get("as_of_date"), str) else None,
        window_days=int(signal.get("window_days", 0) or 0),
        severity=str(signal.get("severity", "")),
        counts=_coerce_counts(signal.get("counts")),
        source=str(signal.get("source", "")),
        enqueued_at=created_at,
        created_at=created_at,
        last_reviewed_at=None,
        next_review_due_at=next_review_due_at,
        status="open",
        review_count=0,
        persistence_count=0,
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
    reviewed_at = _coerce_datetime(now).isoformat()
    path = _resolve_log_path(log_path)
    state = get_pressure_signal_state(digest, log_path=path)
    if state is None:
        raise ValueError("pressure signal digest not found")
    if state["status"] not in {"open", "acknowledged"}:
        raise ValueError("pressure signal is not active")
    review_count = int(state.get("review_count", 0)) + 1
    persistence_count = _next_persistence_count(state, severity=state["severity"])
    next_review_due_at = _compute_next_review_due_at(
        reviewed_at,
        signal_type=state["signal_type"],
        severity=state["severity"],
    )
    event = PressureQueueEvent(
        event="pressure_acknowledged",
        digest=digest,
        signal_type=state["signal_type"],
        as_of_date=state.get("as_of_date"),
        window_days=int(state.get("window_days", 0) or 0),
        severity=state["severity"],
        counts=_coerce_counts(state.get("counts")),
        source=state.get("source", ""),
        enqueued_at=reviewed_at,
        last_reviewed_at=reviewed_at,
        next_review_due_at=next_review_due_at,
        status="acknowledged",
        review_count=review_count,
        persistence_count=persistence_count,
        reviewed_at=reviewed_at,
        actor=actor or "unspecified",
    )
    entry = event.to_payload()
    append_json(path, entry)
    return entry


def list_due_pressure_signals(
    as_of_time: datetime,
    *,
    log_path: Path | None = None,
) -> list[dict[str, object]]:
    due_time = _coerce_datetime(as_of_time)
    states = list_pressure_signal_states(log_path=log_path)
    due = []
    for state in states:
        if state.get("status") not in {"open", "acknowledged"}:
            continue
        next_review = state.get("next_review_due_at")
        if not isinstance(next_review, str):
            continue
        if _coerce_datetime(next_review) <= due_time:
            due.append(state)
    return sorted(due, key=lambda record: (record.get("next_review_due_at", ""), record.get("digest", "")))


def revalidate_pressure_signal(
    digest: str,
    *,
    as_of_time: datetime,
    actor: str,
    log_path: Path | None = None,
) -> dict[str, object]:
    if not actor:
        raise ValueError("actor is required to revalidate pressure signals")
    path = _resolve_log_path(log_path)
    state = get_pressure_signal_state(digest, log_path=path)
    if state is None:
        raise ValueError("pressure signal digest not found")
    if state["status"] not in {"open", "acknowledged"}:
        raise ValueError("pressure signal is not active")
    reviewed_at = _coerce_datetime(as_of_time).isoformat()
    review_count = int(state.get("review_count", 0)) + 1
    persistence_count = _next_persistence_count(state, severity=state["severity"])
    severity_before = state["severity"]
    severity_after = severity_before
    if persistence_count >= PRESSURE_PERSISTENCE_ESCALATION_REVIEWS:
        severity_after = _escalate_severity(severity_before)
        if severity_after != severity_before:
            persistence_count = 0
    next_review_due_at = _compute_next_review_due_at(
        reviewed_at,
        signal_type=state["signal_type"],
        severity=severity_after,
    )
    event = PressureQueueEvent(
        event="pressure_revalidated",
        digest=digest,
        signal_type=state["signal_type"],
        as_of_date=state.get("as_of_date"),
        window_days=int(state.get("window_days", 0) or 0),
        severity=severity_after,
        counts=_coerce_counts(state.get("counts")),
        source=state.get("source", ""),
        enqueued_at=reviewed_at,
        last_reviewed_at=reviewed_at,
        next_review_due_at=next_review_due_at,
        status="acknowledged",
        review_count=review_count,
        persistence_count=persistence_count,
        reviewed_at=reviewed_at,
        actor=actor,
    )
    entry = event.to_payload()
    entry["severity_before"] = severity_before
    append_json(path, entry)
    return entry


def close_pressure_signal(
    digest: str,
    *,
    actor: str,
    reason: str,
    note: str | None = None,
    log_path: Path | None = None,
    closed_at: datetime | None = None,
) -> dict[str, object]:
    return _close_pressure_signal(
        digest,
        actor=actor,
        reason=reason,
        note=note,
        status="closed",
        log_path=log_path,
        closed_at=closed_at,
    )


def expire_pressure_signal(
    digest: str,
    *,
    actor: str,
    reason: str,
    note: str | None = None,
    log_path: Path | None = None,
    closed_at: datetime | None = None,
) -> dict[str, object]:
    return _close_pressure_signal(
        digest,
        actor=actor,
        reason=reason,
        note=note,
        status="expired",
        log_path=log_path,
        closed_at=closed_at,
    )


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


def _coerce_datetime(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise TypeError("timestamp must be datetime or ISO-8601 string")


def pressure_review_interval(signal_type: str, severity: str) -> timedelta:
    policy = PRESSURE_REVIEW_POLICY.get(signal_type) or PRESSURE_REVIEW_POLICY["default"]
    interval = policy.get(severity)
    if interval is not None:
        return interval
    return PRESSURE_REVIEW_POLICY["default"].get(severity, timedelta(days=7))


def _compute_next_review_due_at(
    base_time: str,
    *,
    signal_type: str,
    severity: str,
) -> str:
    base = _coerce_datetime(base_time)
    interval = pressure_review_interval(signal_type, severity)
    return (base + interval).isoformat()


def _escalate_severity(severity: str) -> str:
    if severity not in PRESSURE_SEVERITY_ORDER:
        return severity
    index = PRESSURE_SEVERITY_ORDER.index(severity)
    if index >= len(PRESSURE_SEVERITY_ORDER) - 1:
        return severity
    return PRESSURE_SEVERITY_ORDER[index + 1]


def _next_persistence_count(state: Mapping[str, object], *, severity: str) -> int:
    previous = state.get("severity")
    count = int(state.get("persistence_count", 0) or 0)
    if previous != severity:
        return 0
    return count + 1


def _close_pressure_signal(
    digest: str,
    *,
    actor: str,
    reason: str,
    note: str | None,
    status: str,
    log_path: Path | None,
    closed_at: datetime | None,
) -> dict[str, object]:
    if not actor:
        raise ValueError("actor is required to close pressure signals")
    if status not in PRESSURE_SIGNAL_STATUSES:
        raise ValueError("status must be a valid pressure status")
    if reason not in PRESSURE_CLOSURE_REASONS:
        raise ValueError(f"closure reason must be one of {sorted(PRESSURE_CLOSURE_REASONS)}")
    note_value = None
    if note is not None:
        note_value = str(note).strip()
        if len(note_value) > PRESSURE_CLOSURE_NOTE_LIMIT:
            raise ValueError("closure note exceeds maximum length")
    path = _resolve_log_path(log_path)
    state = get_pressure_signal_state(digest, log_path=path)
    if state is None:
        raise ValueError("pressure signal digest not found")
    if state.get("status") in {"closed", "expired"}:
        raise ValueError("pressure signal is already closed")
    closed_at_value = _coerce_datetime(closed_at).isoformat()
    event = PressureQueueEvent(
        event="pressure_closed" if status == "closed" else "pressure_expired",
        digest=digest,
        signal_type=state["signal_type"],
        as_of_date=state.get("as_of_date"),
        window_days=int(state.get("window_days", 0) or 0),
        severity=state["severity"],
        counts=_coerce_counts(state.get("counts")),
        source=state.get("source", ""),
        enqueued_at=closed_at_value,
        status=status,
        closure_reason=reason,
        closure_note=note_value,
        closed_at=closed_at_value,
        actor=actor,
    )
    entry = event.to_payload()
    append_json(path, entry)
    return entry


def list_pressure_signal_states(log_path: Path | None = None) -> tuple[dict[str, object], ...]:
    entries = read_pressure_queue(log_path)
    states = _build_signal_states(entries)
    return tuple(
        sorted(states.values(), key=lambda record: (record.get("status", ""), record.get("digest", "")))
    )


def get_pressure_signal_state(
    digest: str,
    *,
    log_path: Path | None = None,
) -> dict[str, object] | None:
    states = _build_signal_states(read_pressure_queue(log_path))
    return states.get(digest)


def _build_signal_states(
    entries: Iterable[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    states: dict[str, dict[str, object]] = {}
    for entry in entries:
        digest = entry.get("digest")
        if not isinstance(digest, str) or not digest:
            continue
        event = entry.get("event")
        if event == "pressure_enqueue":
            created_at = entry.get("created_at") or entry.get("enqueued_at")
            if not isinstance(created_at, str):
                continue
            signal_type = str(entry.get("signal_type", ""))
            severity = str(entry.get("severity", ""))
            next_review_due_at = entry.get("next_review_due_at")
            if not isinstance(next_review_due_at, str):
                next_review_due_at = _compute_next_review_due_at(
                    created_at,
                    signal_type=signal_type,
                    severity=severity,
                )
            states[digest] = {
                "digest": digest,
                "signal_type": signal_type,
                "as_of_date": entry.get("as_of_date"),
                "window_days": int(entry.get("window_days", 0) or 0),
                "severity": severity,
                "counts": _coerce_counts(entry.get("counts")),
                "source": str(entry.get("source", "")),
                "created_at": created_at,
                "last_reviewed_at": entry.get("last_reviewed_at"),
                "next_review_due_at": next_review_due_at,
                "status": entry.get("status") or "open",
                "closure_reason": entry.get("closure_reason"),
                "closure_note": entry.get("closure_note"),
                "review_count": int(entry.get("review_count", 0) or 0),
                "persistence_count": int(entry.get("persistence_count", 0) or 0),
            }
            continue
        state = states.get(digest)
        if state is None:
            continue
        if event in {"pressure_acknowledged", "pressure_revalidated"}:
            reviewed_at = entry.get("reviewed_at") or entry.get("last_reviewed_at") or entry.get("enqueued_at")
            if isinstance(reviewed_at, str):
                state["last_reviewed_at"] = reviewed_at
                state["next_review_due_at"] = _compute_next_review_due_at(
                    reviewed_at,
                    signal_type=state["signal_type"],
                    severity=str(entry.get("severity", state["severity"])),
                )
            state["status"] = "acknowledged"
            state["severity"] = str(entry.get("severity", state["severity"]))
            state["review_count"] = int(entry.get("review_count", state.get("review_count", 0)) or 0)
            state["persistence_count"] = int(
                entry.get("persistence_count", state.get("persistence_count", 0)) or 0
            )
            continue
        if event in {"pressure_closed", "pressure_expired"}:
            state["status"] = "closed" if event == "pressure_closed" else "expired"
            state["closure_reason"] = entry.get("closure_reason")
            state["closure_note"] = entry.get("closure_note")
            continue
    return states


__all__ = [
    "DEFAULT_PRESSURE_QUEUE_LOG",
    "PRESSURE_CLOSURE_NOTE_LIMIT",
    "PRESSURE_CLOSURE_REASONS",
    "PRESSURE_PERSISTENCE_ESCALATION_REVIEWS",
    "PRESSURE_REVIEW_POLICY",
    "PRESSURE_SEVERITY_ORDER",
    "PRESSURE_SIGNAL_STATUSES",
    "PressureQueueEvent",
    "acknowledge_pressure_signal",
    "close_pressure_signal",
    "enqueue_pressure_signal",
    "expire_pressure_signal",
    "get_pressure_signal_state",
    "list_due_pressure_signals",
    "list_pressure_signal_states",
    "pressure_review_interval",
    "read_pressure_queue",
    "revalidate_pressure_signal",
]
