from __future__ import annotations

import copy
import json
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

import pytest

from network_daemon import NetworkDaemon
from sentientos.daemons import pulse_bus
from sentientos.daemons.integrity_daemon import IntegrityDaemon

LEDGER_PATH = Path("/daemon/logs/codex.jsonl")


@pytest.fixture(autouse=True)
def reset_bus():
    pulse_bus.reset()
    with suppress(FileNotFoundError):
        LEDGER_PATH.unlink()
    yield
    pulse_bus.reset()
    with suppress(FileNotFoundError):
        LEDGER_PATH.unlink()


@pytest.fixture
def base_config(tmp_path):
    return {
        "network_policies": {
            "allowed_ports": [80, 443],
            "blocked_ports": [23],
            "bandwidth_limit": 1000,
            "rules": [
                {"port": 23, "action": "block"},
                {"bandwidth": 1000, "action": "throttle"},
            ],
        },
        "federation_peer_ip": "192.0.2.10",
        "log_dir": tmp_path,
    }


def _build_event(event_type: str = "heartbeat") -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "test",
        "event_type": event_type,
        "payload": {"message": "ok"},
    }


def test_multiple_subscribers_receive_events():
    integrity = IntegrityDaemon()
    direct_events: list[dict] = []
    pulse_bus.subscribe(lambda event: direct_events.append(event))

    published = _build_event()
    pulse_bus.publish(published)

    assert direct_events and direct_events[0]["event_type"] == "heartbeat"
    assert integrity.received_events and integrity.received_events[0]["event_type"] == "heartbeat"
    integrity.stop()


def test_events_persist_until_consumed():
    published = _build_event("persist_test")
    pulse_bus.publish(published)

    pending = pulse_bus.pending_events()
    assert pending and pending[0]["event_type"] == "persist_test"

    consumed = pulse_bus.consume_events()
    assert consumed == pending
    assert pulse_bus.pending_events() == []


def test_network_daemon_publishes_to_pulse(base_config):
    config = copy.deepcopy(base_config)
    config["enforcement_enabled"] = True
    daemon = NetworkDaemon(config)

    daemon._check_ports([23], interface="eth0")

    with LEDGER_PATH.open("r", encoding="utf-8") as handle:
        ledger_entries = [json.loads(line) for line in handle if line.strip()]

    events = pulse_bus.pending_events()
    enforcement_events = [evt for evt in events if evt["event_type"] == "enforcement"]
    port_events = [evt for evt in events if evt["event_type"] == "port_violation"]

    assert enforcement_events, "Network daemon should emit enforcement pulse events"
    assert port_events, "Network daemon should emit port violation pulse events"

    assert enforcement_events[0]["source_daemon"] == "network"
    assert enforcement_events[0]["payload"] == ledger_entries[0]
    assert "port=23" in enforcement_events[0]["payload"]["policy"]
    assert port_events[0]["payload"]["policy"].startswith("port=23")
