"""Drift report event stream adapter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterator

from logging_config import get_log_path

from .audit_stream import follow_audit_entries, tail_audit_entries
from .event_stream import EventEnvelope, EventStreamAdapter, ReplayPolicy, iter_replay

_DRIFT_TYPE_FLAGS = {
    "POSTURE_STUCK": "posture_stuck",
    "PLUGIN_DOMINANCE": "plugin_dominance",
    "MOTION_STARVATION": "motion_starvation",
    "ANOMALY_ESCALATION": "anomaly_trend",
}


@dataclass
class DriftReport:
    date: str
    timestamp: str
    posture_stuck: bool = False
    plugin_dominance: bool = False
    motion_starvation: bool = False
    anomaly_trend: bool = False
    source_hash: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload = {
            "date": self.date,
            "posture_stuck": self.posture_stuck,
            "plugin_dominance": self.plugin_dominance,
            "motion_starvation": self.motion_starvation,
            "anomaly_trend": self.anomaly_trend,
            "summary_counts": {
                "flags_total": sum(
                    [
                        self.posture_stuck,
                        self.plugin_dominance,
                        self.motion_starvation,
                        self.anomaly_trend,
                    ]
                ),
            },
        }
        if self.source_hash:
            payload["source_hash"] = self.source_hash
        return payload


def _parse_date(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            try:
                return datetime.fromisoformat(raw).date().isoformat()
            except ValueError:
                return None
    return None


def _entry_date(entry: dict[str, object]) -> str | None:
    dates = entry.get("dates")
    if isinstance(dates, list):
        for raw in dates:
            parsed = _parse_date(raw)
            if parsed:
                return parsed
    return _parse_date(entry.get("timestamp"))


def _parse_cursor(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = _parse_date(value)
    return parsed


class DriftEventStream(EventStreamAdapter):
    def __init__(
        self,
        *,
        log_path: Path | None = None,
        replay_policy: ReplayPolicy,
        max_replay_lines: int = 2000,
    ) -> None:
        resolved = log_path or get_log_path("drift_detector.jsonl", "DRIFT_DETECTOR_LOG")
        super().__init__(stream="drift", schema_version=1, replay_policy=replay_policy)
        self.log_path = resolved
        self.max_replay_lines = max_replay_lines

    def replay(self, since_cursor: str | None, limit: int | None = None) -> list[EventEnvelope]:
        capped = self.replay_policy.clamp_limit(limit)
        if capped <= 0:
            return []
        entries = tail_audit_entries(
            self.log_path,
            max_lines=self.max_replay_lines,
            max_bytes=self.replay_policy.max_replay_bytes,
        )
        reports: dict[str, DriftReport] = {}
        for _, entry in entries:
            if entry.get("type") != "drift_detected":
                continue
            drift_type = entry.get("drift_type")
            flag = _DRIFT_TYPE_FLAGS.get(drift_type)
            if not flag:
                continue
            date_value = _entry_date(entry)
            if date_value is None:
                continue
            timestamp = entry.get("timestamp")
            timestamp_str = timestamp if isinstance(timestamp, str) else f"{date_value}T00:00:00+00:00"
            report = reports.get(date_value)
            if report is None:
                report = DriftReport(date=date_value, timestamp=timestamp_str)
                reports[date_value] = report
            elif report.timestamp > timestamp_str:
                report.timestamp = timestamp_str
            setattr(report, flag, True)
            source_hash = entry.get("rolling_hash")
            if isinstance(source_hash, str):
                report.source_hash = source_hash
        ordered = sorted(reports.values(), key=lambda r: r.date, reverse=True)
        cursor_token = _parse_cursor(since_cursor)
        envelopes = [
            self._to_envelope(report)
            for report in ordered
        ]
        return iter_replay(
            envelopes,
            since_cursor=cursor_token,
            limit=capped,
            cursor_key=lambda item: item.event_id,
        )

    def tail(
        self,
        start_cursor: str | None,
        *,
        should_stop: Callable[[], bool],
    ) -> Iterator[EventEnvelope | str]:
        start_offset = self.log_path.stat().st_size if self.log_path.exists() else 0
        seen_dates: set[str] = set()
        if start_cursor:
            cursor_date = _parse_cursor(start_cursor)
            if cursor_date:
                seen_dates.add(cursor_date)
        for item in follow_audit_entries(
            self.log_path,
            start_offset=start_offset,
            should_stop=should_stop,
            heartbeat="drift-stream-ping",
        ):
            if isinstance(item, str):
                yield item
                continue
            _, entry = item
            if entry.get("type") != "drift_detected":
                continue
            date_value = _entry_date(entry)
            if date_value is None or date_value in seen_dates:
                continue
            drift_type = entry.get("drift_type")
            flag = _DRIFT_TYPE_FLAGS.get(drift_type)
            timestamp = entry.get("timestamp")
            timestamp_str = timestamp if isinstance(timestamp, str) else f"{date_value}T00:00:00+00:00"
            report = DriftReport(date=date_value, timestamp=timestamp_str)
            if flag:
                setattr(report, flag, True)
            source_hash = entry.get("rolling_hash")
            if isinstance(source_hash, str):
                report.source_hash = source_hash
            seen_dates.add(date_value)
            yield self._to_envelope(report)

    def _to_envelope(self, report: DriftReport) -> EventEnvelope:
        return EventEnvelope(
            stream=self.stream,
            schema_version=self.schema_version,
            event_id=report.date,
            event_type="drift_day",
            timestamp=report.timestamp,
            payload=report.to_payload(),
            digest=report.source_hash,
        )


__all__ = ["DriftEventStream"]
