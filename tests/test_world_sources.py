from datetime import datetime, timedelta, timezone

from sentientos.world.events import WorldEvent
from sentientos.world.sources import DemoTriggerSource, IdlePulseSource, ScriptedTimelineSource


class _FakeClock:
    def __init__(self) -> None:
        self._monotonic = 0.0
        self._now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._now += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self._monotonic

    def now(self) -> datetime:
        return self._now


def test_scripted_timeline_source_emits_in_order() -> None:
    clock = _FakeClock()
    event_a = WorldEvent("message", clock.now(), "Greeting", {"subject": "hello"})
    event_b = WorldEvent("calendar", clock.now(), "Meeting", {"title": "sync"})
    source = ScriptedTimelineSource(
        [(1.0, event_a), (3.0, event_b)],
        monotonic=clock.monotonic,
        now=clock.now,
    )

    assert source.poll() == []
    clock.advance(1.5)
    emitted_first = source.poll()
    assert len(emitted_first) == 1
    assert emitted_first[0].summary == "Greeting"

    clock.advance(1.0)
    assert source.poll() == []

    clock.advance(1.0)
    emitted_second = source.poll()
    assert len(emitted_second) == 1
    assert emitted_second[0].summary == "Meeting"

    assert source.poll() == []


def test_idle_pulse_source_respects_interval() -> None:
    clock = _FakeClock()
    source = IdlePulseSource(5.0, monotonic=clock.monotonic)

    first = source.poll()
    assert len(first) == 1
    clock.advance(4.0)
    assert source.poll() == []
    clock.advance(1.0)
    second = source.poll()
    assert len(second) == 1


def test_demo_trigger_source_emits_once_after_delay() -> None:
    clock = _FakeClock()
    source = DemoTriggerSource(
        "demo_simple_success",
        trigger_after_seconds=2.0,
        monotonic=clock.monotonic,
        now=clock.now,
    )

    assert source.poll() == []
    clock.advance(1.5)
    assert source.poll() == []
    clock.advance(0.6)
    events = source.poll()
    assert len(events) == 1
    assert events[0].kind == "demo_trigger"
    assert source.poll() == []
