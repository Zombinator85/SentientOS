"""Tests for the lightweight :mod:`network_daemon` module."""

from __future__ import annotations

import copy
import json
from contextlib import suppress
from pathlib import Path

import pytest

from network_daemon import NetworkDaemon


LEDGER_PATH = Path("/daemon/logs/codex.jsonl")


def _read_ledger() -> list[dict]:
    """Return parsed ledger events for assertions."""

    if not LEDGER_PATH.exists():
        return []
    with LEDGER_PATH.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@pytest.fixture(autouse=True)
def clean_ledger():
    """Ensure each test observes a clean ledger file."""

    with suppress(FileNotFoundError):
        LEDGER_PATH.unlink()
    yield
    with suppress(FileNotFoundError):
        LEDGER_PATH.unlink()


@pytest.fixture
def base_config(tmp_path):
    """Provide a reusable configuration dictionary."""

    return {
        "network_policies": {
            "allowed_ports": [80, 443],
            "blocked_ports": [23],
            "bandwidth_limit": 1000,  # kbps
            "rules": [
                {"port": 23, "action": "block"},
                {"bandwidth": 1000, "action": "throttle"},
            ],
        },
        "federation_peer_ip": "192.0.2.10",
        "log_dir": tmp_path,
    }


@pytest.fixture
def daemon(base_config):
    """Network daemon fixture with enforcement disabled by default."""

    config = copy.deepcopy(base_config)
    config["enforcement_enabled"] = False
    return NetworkDaemon(config)


@pytest.fixture
def make_daemon(base_config):
    """Factory for daemons with configurable enforcement mode."""

    def _factory(enforcement_enabled: bool = True) -> NetworkDaemon:
        config = copy.deepcopy(base_config)
        config["enforcement_enabled"] = enforcement_enabled
        return NetworkDaemon(config)

    return _factory


def test_bandwidth_event_emits(daemon):
    """Bandwidth over the limit should emit a saturation event."""

    daemon._check_bandwidth(1500)
    assert any("bandwidth_saturation" in e for e in daemon.events)


def test_unexpected_port_block(daemon):
    """Unexpected ports should be flagged in the event log."""

    daemon._check_ports([22, 80])
    assert any("unexpected_port" in e for e in daemon.events)


def test_federation_resync_trigger(daemon):
    """Unreachable peers should trigger a resync request."""

    daemon._check_federation(False)
    assert daemon.resync_queued is True


def test_no_uptime_event_below_threshold(daemon):
    """Interfaces below threshold should not emit uptime events."""

    daemon._check_uptime({"eth0": True}, 0)
    daemon._check_uptime({"eth0": True}, 299)
    assert not any("uptime_event" in e for e in daemon.events)


def test_uptime_event_triggers_once(daemon):
    """An uptime event fires once when threshold is crossed."""

    daemon._check_uptime({"eth0": True}, 0)
    daemon._check_uptime({"eth0": True}, 301)
    daemon._check_uptime({"eth0": True}, 400)
    events = [e for e in daemon.events if e.startswith("uptime_event")]
    assert len(events) == 1 and "eth0" in events[0]


def test_multiple_interfaces_tracked_independently(daemon):
    """Each interface maintains its own uptime tracking."""

    daemon._check_uptime({"eth0": True, "wlan0": True}, 0)
    daemon._check_uptime({"eth0": True, "wlan0": False}, 301)
    daemon._check_uptime({"eth0": True, "wlan0": False}, 400)
    daemon._check_uptime({"eth0": True, "wlan0": True}, 400)
    daemon._check_uptime({"eth0": True, "wlan0": True}, 701)
    events = [e for e in daemon.events if e.startswith("uptime_event")]
    assert len([e for e in events if "eth0" in e]) == 1
    assert len([e for e in events if "wlan0" in e]) == 1


def test_policy_violation_generates_ledger_entry(make_daemon):
    """Blocked ports should generate ledger-backed enforcement records."""

    daemon = make_daemon(enforcement_enabled=True)
    daemon._check_ports([23], interface="eth0")

    entries = _read_ledger()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["interface"] == "eth0"
    assert entry["action"] == "block"
    assert "port=23" in entry["policy"]


def test_enforcement_mode_toggle_suppresses_ledger(make_daemon):
    """Observe-only mode should not write enforcement events to the ledger."""

    daemon = make_daemon(enforcement_enabled=False)
    daemon._check_ports([23], interface="eth0")
    daemon._check_bandwidth(1500, interface="eth0")
    daemon._check_federation(False)

    assert _read_ledger() == []


def test_multiple_violations_logged_independently(make_daemon):
    """Distinct violations should emit separate ledger events."""

    daemon = make_daemon(enforcement_enabled=True)
    daemon._check_ports([23], interface="eth0")
    daemon._check_bandwidth(1500, interface="eth0")
    daemon._check_federation(False)

    entries = _read_ledger()
    actions = [entry["action"] for entry in entries]
    assert len(entries) == 3
    assert actions.count("block") == 1
    assert "throttle" in actions
    assert "resync" in actions
