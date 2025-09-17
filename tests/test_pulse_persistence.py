from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.daemons import pulse_bus


@pytest.fixture(autouse=True)
def clean_bus_state():
    pulse_bus.reset()
    yield
    pulse_bus.reset()


def _build_event(ts: datetime, *, event_type: str = "heartbeat", **payload: object) -> dict:
    return {
        "timestamp": ts.isoformat(),
        "source_daemon": "tester",
        "event_type": event_type,
        "payload": payload or {"value": event_type},
    }


def _history_entries() -> list[dict]:
    history_root = Path(os.environ["PULSE_HISTORY_ROOT"])
    entries: list[dict] = []
    for path in sorted(history_root.glob("pulse_*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            entries.extend(json.loads(line) for line in handle if line.strip())
    return entries


def test_event_persisted_with_signature() -> None:
    ts = datetime(2025, 1, 1, 12, 30, tzinfo=timezone.utc)
    published = pulse_bus.publish(_build_event(ts, event_type="persist", value=1))

    assert "signature" in published and published["signature"]
    assert published["priority"] == "info"

    entries = _history_entries()
    assert len(entries) == 1
    stored = entries[0]
    assert stored["signature"] == published["signature"]
    assert stored["priority"] == "info"
    assert stored["source_peer"] == "local"
    assert pulse_bus.verify(stored) is True


def test_signature_verification_detects_tampering() -> None:
    ts = datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc)
    pulse_bus.publish(_build_event(ts, event_type="tamper", value=2))
    stored = _history_entries()[0]

    tampered = copy.deepcopy(stored)
    tampered["payload"]["value"] = 999

    assert pulse_bus.verify(stored) is True
    assert pulse_bus.verify(tampered) is False


def test_replay_returns_events_in_chronological_order() -> None:
    base = datetime(2025, 3, 1, 8, 0, tzinfo=timezone.utc)
    events = [
        _build_event(base, event_type="first", order=0),
        _build_event(base + timedelta(hours=1), event_type="second", order=1),
        _build_event(base + timedelta(days=1), event_type="third", order=2),
    ]
    for event in events:
        pulse_bus.publish(event)

    replayed = list(pulse_bus.replay())
    assert [evt["event_type"] for evt in replayed] == ["first", "second", "third"]
    assert all(evt.get("source_peer") == "local" for evt in replayed)
    assert all(pulse_bus.verify(evt) for evt in replayed)


def test_replay_since_filters_events() -> None:
    base = datetime(2025, 4, 10, 14, 0, tzinfo=timezone.utc)
    pulse_bus.publish(_build_event(base, event_type="early", order=0))
    pulse_bus.publish(_build_event(base + timedelta(minutes=30), event_type="late", order=1))
    pulse_bus.publish(_build_event(base + timedelta(days=1), event_type="next", order=2))

    since = base + timedelta(minutes=30)
    replayed = list(pulse_bus.replay(since=since))

    assert [evt["event_type"] for evt in replayed] == ["late", "next"]
    assert all(evt.get("source_peer") == "local" for evt in replayed)


def test_history_survives_reset() -> None:
    ts = datetime(2025, 5, 5, 5, 5, tzinfo=timezone.utc)
    pulse_bus.publish(_build_event(ts, event_type="survive", order=42))

    pulse_bus.reset()  # simulate daemon restart

    replayed = list(pulse_bus.replay())
    assert replayed and replayed[0]["event_type"] == "survive"
    assert replayed[0]["source_peer"] == "local"
