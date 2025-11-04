"""Utilities to route new perception observations into the curiosity loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import memory_manager as mm
from sentientos.metrics import MetricsRegistry


@dataclass
class ObservationEvent:
    modality: str
    payload: Mapping[str, object]


class ObservationRouter:
    """Persist multimodal observations and emit basic metrics."""

    def __init__(self, metrics: MetricsRegistry | None = None) -> None:
        self._metrics = metrics or MetricsRegistry()

    def route(self, event: ObservationEvent) -> Mapping[str, object]:
        record = mm.store_observation({"modality": event.modality, **dict(event.payload)})
        self._metrics.increment("sos_observation_events_total", labels={"modality": event.modality})
        return record


def route_events(events: Iterable[ObservationEvent], metrics: MetricsRegistry | None = None) -> list[Mapping[str, object]]:
    router = ObservationRouter(metrics)
    return [router.route(event) for event in events]


__all__ = ["ObservationEvent", "ObservationRouter", "route_events"]

