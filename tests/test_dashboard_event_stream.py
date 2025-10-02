import asyncio

import pytest

from dashboard_ui.event_stream import EventStream


@pytest.fixture()
def event_stream() -> EventStream:
    return EventStream(categories={"feed", "oracle", "gapseeker", "commits", "research"}, history_limit=3)


def test_publish_and_history(event_stream: EventStream) -> None:
    event_stream.publish(category="feed", message="Booted", module="BootDaemon")
    history = event_stream.get_history("feed")
    assert len(history) == 1
    assert history[0]["message"] == "Booted"


def test_history_limit(event_stream: EventStream) -> None:
    for index in range(5):
        event_stream.publish(category="feed", message=f"event-{index}", module="BootDaemon")
    history = event_stream.get_history("feed")
    assert len(history) == 3
    assert history[0]["message"] == "event-4"
    assert history[-1]["message"] == "event-2"


def test_subscribe_receives_events(event_stream: EventStream) -> None:
    subscriber_id, queue = event_stream.subscribe()
    try:
        event_stream.publish(category="oracle", message="Query", module="OracleCycle")
        received = asyncio.run(asyncio.wait_for(queue.get(), timeout=1))
        assert received.message == "Query"
        assert received.category == "oracle"
    finally:
        event_stream.unsubscribe(subscriber_id)
