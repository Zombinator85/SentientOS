from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_LOG_PATH = "logs/introspection_spine.jsonl"

_SENSITIVE_MARKERS = (
    "password",
    "secret",
    "token",
    "key",
    "credential",
    "auth",
)


class EventType(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    RECOVERY_SIMULATION = "RECOVERY_SIMULATION"
    RECOVERY_EXECUTION = "RECOVERY_EXECUTION"
    COGNITION_CYCLE = "COGNITION_CYCLE"
    FORGETTING_PRESSURE = "FORGETTING_PRESSURE"
    MEMORY_ECONOMICS = "MEMORY_ECONOMICS"
    SNAPSHOT_EMISSION = "SNAPSHOT_EMISSION"
    CLI_ACTION = "CLI_ACTION"


@dataclass(frozen=True)
class IntrospectionEvent:
    event_id: str
    event_type: EventType
    phase: str
    timestamp_logical: int
    linked_artifact_ids: tuple[str, ...]
    summary: str
    metadata: Mapping[str, Any]

    def to_ordered_dict(self) -> OrderedDict:
        ordered = OrderedDict(
            [
                ("event_id", self.event_id),
                ("event_type", self.event_type.value),
                ("phase", self.phase),
                ("timestamp_logical", self.timestamp_logical),
                ("linked_artifact_ids", list(self.linked_artifact_ids)),
                ("summary", self.summary),
                ("metadata", _stable_map(self.metadata)),
            ]
        )
        return ordered

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_ordered_dict(), indent=indent, ensure_ascii=False)

    def content_hash(self) -> str:
        payload = _payload_for_hash(
            event_type=self.event_type,
            phase=self.phase,
            timestamp_logical=self.timestamp_logical,
            linked_artifact_ids=self.linked_artifact_ids,
            summary=self.summary,
            metadata=self.metadata,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class TraceSpine:
    events: list[IntrospectionEvent]

    def linear_trace(
        self,
        *,
        phase: str | None = None,
        artifact_id: str | None = None,
        last: int | None = None,
    ) -> list[IntrospectionEvent]:
        filtered = self.events
        if phase:
            filtered = [event for event in filtered if event.phase == phase]
        if artifact_id:
            filtered = [
                event for event in filtered if artifact_id in event.linked_artifact_ids
            ]
        if last is not None:
            return filtered[-last:]
        return filtered

    def group_by_artifact(
        self,
        *,
        artifact_id: str | None = None,
    ) -> dict[str, list[IntrospectionEvent]]:
        grouped: dict[str, list[IntrospectionEvent]] = {}
        for event in self.linear_trace():
            for artifact in event.linked_artifact_ids:
                if artifact_id is not None and artifact != artifact_id:
                    continue
                grouped.setdefault(artifact, []).append(event)
        return grouped


class _IntrospectionClock:
    def __init__(self) -> None:
        self._counter = 0

    def tick(self) -> int:
        self._counter += 1
        return self._counter


_DEFAULT_CLOCK = _IntrospectionClock()
_LAST_TIMESTAMP_BY_PATH: dict[str, int] = {}


def _stable_map(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _stable_value(value[key]) for key in sorted(value.keys(), key=str)}


def _stable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _stable_map(value)
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    return value


def _should_redact(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _SENSITIVE_MARKERS)


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_value(item) for item in value]
    if isinstance(value, str) and _should_redact(value):
        return "***"
    return value


def _redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if _should_redact(str(key)):
            sanitized[str(key)] = "***"
        else:
            sanitized[str(key)] = _redact_value(item)
    return sanitized


def _payload_for_hash(
    *,
    event_type: EventType,
    phase: str,
    timestamp_logical: int,
    linked_artifact_ids: Sequence[str],
    summary: str,
    metadata: Mapping[str, Any],
) -> str:
    payload = OrderedDict(
        [
            ("event_type", event_type.value),
            ("phase", phase),
            ("timestamp_logical", timestamp_logical),
            ("linked_artifact_ids", sorted(set(linked_artifact_ids))),
            ("summary", summary),
            ("metadata", _stable_map(metadata)),
        ]
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _next_timestamp(path: Path, clock: _IntrospectionClock) -> int:
    cache_key = path.as_posix()
    cached = _LAST_TIMESTAMP_BY_PATH.get(cache_key)
    if cached is not None:
        cached += 1
        _LAST_TIMESTAMP_BY_PATH[cache_key] = cached
        return cached
    if path.exists():
        try:
            last_line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
        except Exception:
            last_line = ""
        if last_line:
            try:
                payload = json.loads(last_line)
                last_value = payload.get("timestamp_logical")
                if isinstance(last_value, int):
                    _LAST_TIMESTAMP_BY_PATH[cache_key] = last_value + 1
                    return last_value + 1
            except json.JSONDecodeError:
                pass
    next_value = clock.tick()
    _LAST_TIMESTAMP_BY_PATH[cache_key] = next_value
    return next_value


def build_event(
    *,
    event_type: EventType,
    phase: str,
    timestamp_logical: int,
    linked_artifact_ids: Sequence[str] | None,
    summary: str,
    metadata: Mapping[str, Any] | None,
) -> IntrospectionEvent:
    linked_ids = tuple(sorted({str(item) for item in (linked_artifact_ids or []) if item}))
    sanitized_meta = _redact_mapping(metadata or {})
    event_id = hashlib.sha256(
        _payload_for_hash(
            event_type=event_type,
            phase=phase,
            timestamp_logical=timestamp_logical,
            linked_artifact_ids=linked_ids,
            summary=summary,
            metadata=sanitized_meta,
        ).encode("utf-8")
    ).hexdigest()
    return IntrospectionEvent(
        event_id=event_id,
        event_type=event_type,
        phase=phase,
        timestamp_logical=timestamp_logical,
        linked_artifact_ids=linked_ids,
        summary=summary,
        metadata=sanitized_meta,
    )


def persist_event(event: IntrospectionEvent, *, path: str = DEFAULT_LOG_PATH) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(event.to_json())
        handle.write("\n")


def emit_introspection_event(
    *,
    event_type: EventType,
    phase: str,
    summary: str,
    metadata: Mapping[str, Any] | None = None,
    linked_artifact_ids: Sequence[str] | None = None,
    timestamp_logical: int | None = None,
    path: str = DEFAULT_LOG_PATH,
    clock: _IntrospectionClock | None = None,
) -> None:
    try:
        path_obj = Path(path)
        logical_time = timestamp_logical
        if logical_time is None:
            logical_time = _next_timestamp(path_obj, clock or _DEFAULT_CLOCK)
        event = build_event(
            event_type=event_type,
            phase=phase,
            timestamp_logical=logical_time,
            linked_artifact_ids=linked_artifact_ids,
            summary=summary,
            metadata=metadata,
        )
        persist_event(event, path=path)
    except Exception:
        return


def load_events(path: str = DEFAULT_LOG_PATH) -> list[IntrospectionEvent]:
    events: list[IntrospectionEvent] = []
    source_path = Path(path)
    if not source_path.exists():
        return events
    lines = source_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        event = _event_from_payload(payload)
        if event is not None:
            events.append(event)
    return events


def _event_from_payload(payload: Mapping[str, Any]) -> IntrospectionEvent | None:
    try:
        event_type = EventType(str(payload.get("event_type")))
    except ValueError:
        return None
    event_id = str(payload.get("event_id", ""))
    phase = str(payload.get("phase", ""))
    summary = str(payload.get("summary", ""))
    timestamp_logical = payload.get("timestamp_logical")
    linked_ids = payload.get("linked_artifact_ids")
    metadata = payload.get("metadata")
    if not isinstance(timestamp_logical, int):
        return None
    if not isinstance(linked_ids, list):
        linked_ids = []
    if not isinstance(metadata, Mapping):
        metadata = {}
    event = IntrospectionEvent(
        event_id=event_id,
        event_type=event_type,
        phase=phase,
        timestamp_logical=timestamp_logical,
        linked_artifact_ids=tuple(str(item) for item in linked_ids if item),
        summary=summary,
        metadata=metadata,
    )
    return event


def trace_from_events(events: Iterable[IntrospectionEvent]) -> TraceSpine:
    return TraceSpine(events=list(events))
