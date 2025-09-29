"""Dashboard helpers for the Integration Memory panel."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from codex.narratives import CodexNarrator
from integration_memory import IntegrationEntry, IntegrationMemory, integration_memory

__all__ = [
    "IntegrationPanelState",
    "integration_panel_state",
    "lock_entry",
    "prune_entries",
    "replay_entry",
]


@dataclass(frozen=True)
class IntegrationPanelState:
    """Serialized view model for the Integration Memory dashboard."""

    events: list[dict[str, Any]]
    projections: list[dict[str, Any]]
    state_vectors: dict[str, Any]
    locked_entries: set[str]
    narratives: list[dict[str, Any]]
    active_view: str
    feed: list[dict[str, Any]]


def _unique_sources(entries: Iterable[IntegrationEntry]) -> set[str]:
    return {entry.source for entry in entries}


def integration_panel_state(
    *,
    limit: int = 10,
    memory: IntegrationMemory | None = None,
    view: str = "logs",
    narrator: CodexNarrator | None = None,
) -> IntegrationPanelState:
    """Build the current panel state for streamlit or CLI consumers."""

    mem = memory or integration_memory
    entries = mem.load_events(limit=limit)
    events_payload = [entry.to_dict() for entry in entries]
    projections: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        pattern = entry.payload.get("anomaly_pattern") or entry.event_type
        key = (entry.source, pattern)
        if key in seen:
            continue
        seen.add(key)
        projections.append(mem.project_state(entry.source, pattern))
    for source in sorted(_unique_sources(entries)):
        overall_key = (source, "*")
        if overall_key not in seen:
            projections.append(mem.project_state(source))
            seen.add(overall_key)
    state_vectors = mem.state_vector()
    active_view = view.lower() if isinstance(view, str) else "logs"
    if active_view not in {"logs", "narratives"}:
        active_view = "logs"
    narrative_engine = narrator or CodexNarrator(mem.root)
    narratives = narrative_engine.list_narratives(limit=limit)
    feed = narratives if active_view == "narratives" else events_payload
    return IntegrationPanelState(
        events=events_payload,
        projections=projections,
        state_vectors=state_vectors,
        locked_entries=mem.locked_entries(),
        narratives=narratives,
        active_view=active_view,
        feed=feed,
    )


def lock_entry(entry_id: str, *, memory: IntegrationMemory | None = None) -> None:
    mem = memory or integration_memory
    mem.lock_entry(entry_id)


def prune_entries(
    *,
    before: str | datetime | None = None,
    source: str | None = None,
    memory: IntegrationMemory | None = None,
) -> int:
    mem = memory or integration_memory
    return mem.prune(before=before, source=source)


def replay_entry(entry_id: str, *, memory: IntegrationMemory | None = None) -> dict[str, Any] | None:
    mem = memory or integration_memory
    entry = mem.replay(entry_id)
    return entry.to_dict() if entry else None
