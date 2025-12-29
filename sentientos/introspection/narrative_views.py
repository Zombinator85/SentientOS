from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterable, Sequence

from .spine import EventType, IntrospectionEvent, TraceSpine

_DISALLOWED_CONTEXTS = {"cognition", "recovery"}
_DEFAULT_NEARBY_WINDOW = 5


@dataclass(frozen=True)
class RenderedView:
    title: str
    lines: tuple[str, ...]


def ensure_view_allowed() -> None:
    context = os.getenv("SENTIENTOS_EXECUTION_CONTEXT", "").strip().lower()
    if context in _DISALLOWED_CONTEXTS:
        raise RuntimeError(
            "Trace views are read-only and cannot run inside cognition or recovery contexts."
        )


def render_event_chain(events: Sequence[IntrospectionEvent]) -> RenderedView:
    ordered = _ordered_events(events)
    lines = tuple(_format_event_line(event) for event in ordered)
    return RenderedView(title="EventChainView", lines=lines)


def render_artifact_view(spine: TraceSpine, artifact_id: str) -> RenderedView:
    grouped = spine.group_by_artifact(artifact_id=artifact_id)
    events = grouped.get(artifact_id, [])
    ordered = _ordered_events(events)
    header = (
        f"Artifact {artifact_id}",
        f"Events {len(ordered)}",
    )
    lines = header + tuple(_format_event_line(event) for event in ordered)
    return RenderedView(title="ArtifactCentricView", lines=lines)


def render_cycle_context_view(
    spine: TraceSpine,
    cycle_id: str,
    *,
    window: int = _DEFAULT_NEARBY_WINDOW,
) -> RenderedView:
    cycle_event = _find_cycle_event(spine, cycle_id)
    if cycle_event is None:
        return RenderedView(title="CycleContextView", lines=("No matching cognition cycle found.",))

    posture = _string_or_dash(cycle_event.metadata.get("cognitive_posture"))
    load = _string_or_dash(cycle_event.metadata.get("cognitive_load_narrative"))
    posture_transition = _string_or_dash(cycle_event.metadata.get("posture_transition"))
    posture_duration = _string_or_dash(cycle_event.metadata.get("posture_duration"))

    forgetting_event = _nearest_event(spine.events, EventType.FORGETTING_PRESSURE, cycle_event)
    forgetting_line = "forgetting_pressure_event_id=-"
    if forgetting_event is not None:
        forgetting_line = (
            "forgetting_pressure_event_id="
            f"{forgetting_event.event_id}"
        )

    nearby_events = _nearby_events(spine.events, cycle_event, window)
    nearby_lines = tuple(_format_event_line(event) for event in nearby_events)

    header = (
        f"Cycle {cycle_event.event_id}",
        f"timestamp={cycle_event.timestamp_logical:06d}",
        f"posture={posture}",
        f"load={load}",
        f"posture_transition={posture_transition}",
        f"posture_duration={posture_duration}",
        forgetting_line,
        f"Nearby diagnostics/recoveries (±{window})",
    )
    lines = header + (nearby_lines or ("none",))
    return RenderedView(title="CycleContextView", lines=lines)


def _find_cycle_event(spine: TraceSpine, cycle_id: str) -> IntrospectionEvent | None:
    for event in spine.events:
        if event.event_type != EventType.COGNITION_CYCLE:
            continue
        if event.event_id == cycle_id:
            return event
        snapshot_hash = event.metadata.get("snapshot_hash")
        if isinstance(snapshot_hash, str) and snapshot_hash == cycle_id:
            return event
    return None


def _nearby_events(
    events: Iterable[IntrospectionEvent],
    cycle_event: IntrospectionEvent,
    window: int,
) -> list[IntrospectionEvent]:
    candidates = []
    for event in events:
        if event.event_type not in {
            EventType.DIAGNOSTIC,
            EventType.RECOVERY_SIMULATION,
            EventType.RECOVERY_EXECUTION,
        }:
            continue
        if abs(event.timestamp_logical - cycle_event.timestamp_logical) <= window:
            candidates.append(event)
    return _ordered_events(candidates)


def _nearest_event(
    events: Iterable[IntrospectionEvent],
    event_type: EventType,
    anchor: IntrospectionEvent,
) -> IntrospectionEvent | None:
    candidates = [event for event in events if event.event_type == event_type]
    if not candidates:
        return None
    candidates.sort(key=lambda event: (abs(event.timestamp_logical - anchor.timestamp_logical), event.event_id))
    return candidates[0]


def _ordered_events(events: Iterable[IntrospectionEvent]) -> list[IntrospectionEvent]:
    return sorted(events, key=lambda event: (event.timestamp_logical, event.event_id))


def _format_event_line(event: IntrospectionEvent) -> str:
    metadata = json.dumps(event.metadata, sort_keys=True)
    artifacts = ",".join(event.linked_artifact_ids) if event.linked_artifact_ids else "-"
    verb = _event_verb(event.event_type)
    return (
        f"{event.timestamp_logical:06d} | event_id={event.event_id} | {verb} | "
        f"type={event.event_type.value} | phase={event.phase} | summary={event.summary} | "
        f"artifacts={artifacts} | metadata={metadata}"
    )


def _event_verb(event_type: EventType) -> str:
    mapping = {
        EventType.DIAGNOSTIC: "diagnostic emitted",
        EventType.RECOVERY_SIMULATION: "recovery simulated",
        EventType.RECOVERY_EXECUTION: "recovery executed",
        EventType.COGNITION_CYCLE: "cognition cycle occurred",
        EventType.FORGETTING_PRESSURE: "forgetting pressure emitted",
        EventType.SNAPSHOT_EMISSION: "snapshot emitted",
        EventType.CLI_ACTION: "cli action emitted",
    }
    return mapping.get(event_type, "event occurred")


def _string_or_dash(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, str) and not value.strip():
        return "-"
    return str(value)


__all__ = [
    "RenderedView",
    "ensure_view_allowed",
    "render_artifact_view",
    "render_cycle_context_view",
    "render_event_chain",
]
