from datetime import datetime, timedelta, timezone

from sentientos.world.bus import WorldEventBus, world_events_to_persona_pulse
from sentientos.world.events import (
    WorldEvent,
    make_calendar_event,
    make_demo_trigger_event,
    make_message_event,
    make_system_load_event,
)


def test_world_event_helpers_create_expected_payloads() -> None:
    message = make_message_event("Status", "operator")
    assert message.kind == "message"
    assert message.data["subject"] == "Status"
    assert message.data["source"] == "operator"

    calendar = make_calendar_event("Sync", 15)
    assert calendar.kind == "calendar"
    assert calendar.data["starts_in_minutes"] == 15

    system_load = make_system_load_event("high")
    assert system_load.kind == "system_load"
    assert system_load.data["level"] == "high"

    demo = make_demo_trigger_event("demo_simple_success")
    assert demo.kind == "demo_trigger"
    assert demo.data["demo_name"] == "demo_simple_success"


def test_world_event_bus_filters_by_timestamp() -> None:
    bus = WorldEventBus(max_events=10)
    now = datetime.now(timezone.utc)
    first = WorldEvent("message", now, "First", {})
    second = WorldEvent("calendar", now + timedelta(seconds=5), "Second", {})
    bus.push(first)
    bus.push(second)

    all_events = bus.drain_since(None)
    assert all_events == [first, second]

    later_events = bus.drain_since(now)
    assert later_events == [second]


def test_world_events_to_persona_pulse_structure() -> None:
    events = [
        make_message_event("Hello", "ally"),
        make_system_load_event("low"),
    ]
    pulses = world_events_to_persona_pulse(events)
    assert len(pulses) == 2
    assert pulses[0]["kind"] == "world"
    assert pulses[0]["world_kind"] == "message"
    assert "data" in pulses[0]
    assert pulses[1]["world_kind"] == "system_load"
    assert pulses[1]["data"]["level"] == "low"
