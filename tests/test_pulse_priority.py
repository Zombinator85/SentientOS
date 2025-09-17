"""Tests covering pulse priority routing and integrations."""

from __future__ import annotations

import copy
import importlib
import threading
import time
from datetime import datetime, timezone
from queue import Queue
from typing import List

import pytest

from sentientos.daemons import pulse_bus
from sentientos.daemons.integrity_daemon import IntegrityDaemon
from sentientos.daemons.monitoring_daemon import MonitoringDaemon


@pytest.fixture(autouse=True)
def reset_bus() -> None:
    pulse_bus.reset()
    yield
    pulse_bus.reset()


def _build_event(event_type: str, *, priority: str | None = None) -> dict:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "test",
        "event_type": event_type,
        "payload": {"event": event_type},
    }
    if priority is not None:
        event["priority"] = priority
    return event


def test_priority_filter_delivers_expected_events() -> None:
    """Subscribers receive only the priorities they register for."""

    critical_events: List[dict] = []
    info_events: List[dict] = []

    pulse_bus.subscribe(lambda evt: critical_events.append(evt), priorities=["critical"])
    pulse_bus.subscribe(lambda evt: info_events.append(evt), priorities=["info"])

    pulse_bus.publish(_build_event("info_event"))
    pulse_bus.publish(_build_event("critical_event", priority="critical"))

    assert [evt["event_type"] for evt in critical_events] == ["critical_event"]
    assert [evt["event_type"] for evt in info_events] == ["info_event"]


def test_default_priority_is_info_for_unfiltered_subscribers() -> None:
    """Subscribers without filters should observe all events with default info priority."""

    received: List[dict] = []
    pulse_bus.subscribe(lambda evt: received.append(evt))

    pulse_bus.publish(_build_event("default"))
    pulse_bus.publish(_build_event("warning", priority="warning"))

    priorities = [evt["priority"] for evt in received]
    assert priorities == ["info", "warning"]


def test_integrity_daemon_emits_critical_on_signature_mismatch() -> None:
    """Integrity daemon publishes a critical pulse when verification fails."""

    valid = pulse_bus.publish(_build_event("heartbeat"))
    integrity = IntegrityDaemon()
    captured: List[dict] = []
    subscription = pulse_bus.subscribe(captured.append, priorities=["critical"])

    tampered = copy.deepcopy(valid)
    tampered["payload"]["event"] = "tampered"

    integrity._handle_event(tampered)

    assert integrity.invalid_events
    assert captured and captured[-1]["event_type"] == "integrity_violation"
    assert captured[-1]["priority"] == "critical"
    assert any(evt.get("event_type") == "integrity_violation" for evt in integrity.alerts)

    subscription.unsubscribe()
    integrity.stop()


def test_monitoring_daemon_tracks_warning_and_critical() -> None:
    """Monitoring daemon surfaces warning and critical pulses."""

    monitor = MonitoringDaemon()
    pulse_bus.publish(_build_event("routine"))
    pulse_bus.publish(_build_event("warning_event", priority="warning"))
    pulse_bus.publish(_build_event("critical_event", priority="critical"))

    assert monitor.warning_events and monitor.warning_events[0]["priority"] == "warning"
    assert monitor.critical_events and monitor.critical_events[0]["priority"] == "critical"
    assert len(monitor.warning_events) == 1
    assert len(monitor.critical_events) == 1

    monitor.stop()


def test_codex_self_repair_triggers_on_critical(monkeypatch, tmp_path) -> None:
    """Codex daemon subscribes to critical events and reacts to them."""

    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    codex_module = importlib.import_module("daemon.codex_daemon")
    codex_daemon = importlib.reload(codex_module)

    monkeypatch.setattr(codex_daemon, "CODEX_SESSION_FILE", tmp_path / "codex_session.json")
    monkeypatch.setattr(codex_daemon, "CODEX_INTERVAL", 0.01)
    monkeypatch.setattr(codex_daemon, "run_once", lambda queue: None)
    monkeypatch.setattr(codex_daemon.pulse_bus, "replay", lambda since=None: [])

    captured_priorities: List[list[str] | None] = []
    original_subscribe = codex_daemon.pulse_bus.subscribe

    def spy_subscribe(handler, priorities=None):
        captured_priorities.append(list(priorities) if priorities is not None else None)
        return original_subscribe(handler, priorities)

    monkeypatch.setattr(codex_daemon.pulse_bus, "subscribe", spy_subscribe)

    calls: List[bool] = []

    def fake_self_repair(queue):
        calls.append(True)

    monkeypatch.setattr(codex_daemon, "self_repair_check", fake_self_repair)

    stop = threading.Event()
    queue = Queue()
    thread = threading.Thread(target=codex_daemon.run_loop, args=(stop, queue))
    thread.start()
    try:
        for _ in range(100):
            if captured_priorities:
                break
            time.sleep(0.01)
        assert captured_priorities and captured_priorities[0] == ["critical"]

        pulse_bus.publish(_build_event("info_chatter"))
        time.sleep(0.05)
        assert not calls

        pulse_bus.publish(
            _build_event("resync_required", priority="critical")
        )

        for _ in range(100):
            if calls:
                break
            time.sleep(0.01)
        assert len(calls) == 1
    finally:
        stop.set()
        thread.join(timeout=1)
        codex_daemon.pulse_bus.reset()
