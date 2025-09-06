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

