import pytest

from network_daemon import NetworkDaemon


@pytest.fixture
def daemon(tmp_path):
    """Provide a NetworkDaemon with a minimal config for testing."""
    config = {
        "network_policies": {
            "allowed_ports": [80, 443],
            "blocked_ports": [23],
            "bandwidth_limit": 1000,  # kbps
        },
        "federation_peer_ip": "192.0.2.10",
        "log_dir": tmp_path,
    }
    return NetworkDaemon(config)


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

