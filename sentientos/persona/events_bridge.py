from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from sentientos.world.bus import WorldEventBus, world_events_to_persona_pulse

PersonaEvent = Dict[str, object]
PersonaSource = Callable[[], Iterable[Mapping[str, object]]]


def _collect_other_events(sources: Sequence[PersonaSource] | None) -> List[PersonaEvent]:
    events: List[PersonaEvent] = []
    if not sources:
        return events
    for source in sources:
        try:
            produced = source()
        except Exception:
            continue
        for item in produced:
            if isinstance(item, Mapping):
                events.append(dict(item))
    return events


def make_persona_event_source(
    world_bus: Optional[WorldEventBus],
    other_sources: Sequence[PersonaSource] | None = None,
) -> Callable[[], List[PersonaEvent]]:
    """Combine world bus events with existing persona event sources."""

    last_ts: Optional[datetime] = None

    def _source() -> List[PersonaEvent]:
        nonlocal last_ts
        merged: List[PersonaEvent] = []
        if world_bus is not None:
            world_events = world_bus.drain_since(last_ts)
            if world_events:
                last_ts = world_events[-1].ts
                merged.extend(world_events_to_persona_pulse(world_events))
        merged.extend(_collect_other_events(other_sources))
        return merged

    return _source
