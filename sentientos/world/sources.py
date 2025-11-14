from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Sequence, Tuple

from .events import WorldEvent


class WorldSource:
    def poll(self) -> List[WorldEvent]:
        """
        Return any new events since last poll.
        Implementations may maintain internal state.
        """

        raise NotImplementedError


class ScriptedTimelineSource(WorldSource):
    """Emit pre-scripted events at deterministic offsets."""

    def __init__(
        self,
        timeline: Sequence[Tuple[float, WorldEvent]],
        *,
        monotonic: Callable[[], float] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._schedule = sorted(((float(offset), event) for offset, event in timeline), key=lambda item: item[0])
        self._monotonic = monotonic or time.monotonic
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._start = self._monotonic()
        self._index = 0

    def poll(self) -> List[WorldEvent]:
        if self._index >= len(self._schedule):
            return []
        elapsed = self._monotonic() - self._start
        emitted: List[WorldEvent] = []
        while self._index < len(self._schedule) and elapsed >= self._schedule[self._index][0]:
            template = self._schedule[self._index][1]
            emitted.append(
                WorldEvent(
                    template.kind,
                    self._now(),
                    template.summary,
                    dict(template.data),
                )
            )
            self._index += 1
        return emitted


class IdlePulseSource(WorldSource):
    """Generate periodic heartbeat events signalling idle activity."""

    def __init__(
        self,
        interval_seconds: float,
        *,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._interval = float(interval_seconds)
        self._monotonic = monotonic or time.monotonic
        self._last_emitted: float | None = None

    def poll(self) -> List[WorldEvent]:
        now = self._monotonic()
        should_emit = self._last_emitted is None or (now - self._last_emitted) >= self._interval
        if not should_emit:
            return []
        self._last_emitted = now
        event = WorldEvent(
            "heartbeat",
            datetime.now(timezone.utc),
            "Idle pulse",
            {"source": "idle"},
        )
        return [event]


class DemoTriggerSource(WorldSource):
    """Emit a demo trigger event once after a configured delay."""

    def __init__(
        self,
        demo_name: str,
        *,
        trigger_after_seconds: float = 0.0,
        monotonic: Callable[[], float] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._demo_name = demo_name
        self._delay = max(0.0, float(trigger_after_seconds))
        self._monotonic = monotonic or time.monotonic
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._start = self._monotonic()
        self._emitted = False

    def poll(self) -> List[WorldEvent]:
        if self._emitted:
            return []
        elapsed = self._monotonic() - self._start
        if elapsed < self._delay:
            return []
        self._emitted = True
        event = WorldEvent(
            "demo_trigger",
            self._now(),
            f"Trigger demo: {self._demo_name}",
            {"demo_name": self._demo_name},
        )
        return [event]


def poll_sources(sources: Iterable[WorldSource]) -> List[WorldEvent]:
    events: List[WorldEvent] = []
    for source in sources:
        events.extend(source.poll())
    return events
