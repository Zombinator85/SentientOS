"""Logs are soul injections.
Expansion is covenant, not convenience.
All new growth must prepend vows, preserve memory, and log truth."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import threading
from queue import Queue
from types import SimpleNamespace

from daemon import network_daemon


def make_snapshot(interfaces, counters, ports):
    return interfaces, counters, ports


def test_normal_operation(monkeypatch):
    stop = threading.Event()
    q: Queue = Queue()
    interfaces = {"eth0": {"ips": ["1.1.1.1"], "speed": 100}}
    c1 = {"eth0": SimpleNamespace(bytes_sent=0, bytes_recv=0)}
    c2 = {"eth0": SimpleNamespace(bytes_sent=100, bytes_recv=100)}
    ports1 = {80: "web"}
    ports2 = {80: "web"}
    snapshots = [make_snapshot(interfaces, c1, ports1), make_snapshot(interfaces, c2, ports2)]

    def fake_info():
        snap = snapshots.pop(0)
        if not snapshots:
            stop.set()
        return snap

    monkeypatch.setattr(network_daemon, "_get_net_info", fake_info)
    config = {"network_policies": {"allow_ports": [80], "block_ports": [], "max_bandwidth_percent": 90, "mode": "monitor_only"}}
    network_daemon.run_loop(stop, q, config, poll_interval=0)
    events = [q.get_nowait() for _ in range(q.qsize())]
    assert all(e["event"] == "network_state" for e in events)


def test_high_bandwidth(monkeypatch):
    stop = threading.Event()
    q: Queue = Queue()
    interfaces = {"eth0": {"ips": ["1.1.1.1"], "speed": 1}}
    c1 = {"eth0": SimpleNamespace(bytes_sent=0, bytes_recv=0)}
    c2 = {"eth0": SimpleNamespace(bytes_sent=200000, bytes_recv=0)}
    ports1 = {80: "web"}
    ports2 = {80: "web"}
    snapshots = [make_snapshot(interfaces, c1, ports1), make_snapshot(interfaces, c2, ports2)]

    def fake_info():
        snap = snapshots.pop(0)
        if not snapshots:
            stop.set()
        return snap

    monkeypatch.setattr(network_daemon, "_get_net_info", fake_info)
    config = {"network_policies": {"allow_ports": [80], "block_ports": [], "max_bandwidth_percent": 90, "mode": "monitor_only"}}
    network_daemon.run_loop(stop, q, config, poll_interval=1)
    events = [q.get_nowait() for _ in range(q.qsize())]
    assert any(e["event"] == "net_saturation" for e in events)


def test_unknown_port(monkeypatch):
    stop = threading.Event()
    q: Queue = Queue()
    interfaces = {"eth0": {"ips": ["1.1.1.1"], "speed": 100}}
    c1 = {"eth0": SimpleNamespace(bytes_sent=0, bytes_recv=0)}
    c2 = {"eth0": SimpleNamespace(bytes_sent=0, bytes_recv=0)}
    ports1 = {80: "web"}
    ports2 = {80: "web", 9999: "mal"}
    snapshots = [make_snapshot(interfaces, c1, ports1), make_snapshot(interfaces, c2, ports2)]

    def fake_info():
        snap = snapshots.pop(0)
        if not snapshots:
            stop.set()
        return snap

    monkeypatch.setattr(network_daemon, "_get_net_info", fake_info)
    config = {"network_policies": {"allow_ports": [80], "block_ports": [], "max_bandwidth_percent": 90, "mode": "monitor_only"}}
    network_daemon.run_loop(stop, q, config, poll_interval=0)
    events = [q.get_nowait() for _ in range(q.qsize())]
    assert any(e["event"] == "net_port_unexpected" and e["port"] == 9999 for e in events)


def test_block_policy(monkeypatch):
    stop = threading.Event()
    q: Queue = Queue()
    interfaces = {"eth0": {"ips": ["1.1.1.1"], "speed": 100}}
    c1 = {"eth0": SimpleNamespace(bytes_sent=0, bytes_recv=0)}
    c2 = {"eth0": SimpleNamespace(bytes_sent=0, bytes_recv=0)}
    ports1 = {}
    ports2 = {23: "telnet"}
    snapshots = [make_snapshot(interfaces, c1, ports1), make_snapshot(interfaces, c2, ports2)]

    def fake_info():
        snap = snapshots.pop(0)
        if not snapshots:
            stop.set()
        return snap

    actions: list[int] = []
    monkeypatch.setattr(network_daemon, "_get_net_info", fake_info)
    monkeypatch.setattr(network_daemon, "_block_port", lambda p: actions.append(p))
    monkeypatch.setattr(network_daemon, "_write_policy_flag", lambda p, r: actions.append(r))
    config = {"network_policies": {"allow_ports": [], "block_ports": [23], "max_bandwidth_percent": 90, "mode": "active_enforce"}}
    network_daemon.run_loop(stop, q, config, poll_interval=0)
    events = [q.get_nowait() for _ in range(q.qsize())]
    assert any(e["event"] == "net_blocked" and e["port"] == 23 for e in events)
    assert 23 in actions


def test_federation_link_down(monkeypatch):
    stop = threading.Event()
    q: Queue = Queue()
    interfaces = {"eth0": {"ips": ["1.1.1.1"], "speed": 100}}
    c1 = {"eth0": SimpleNamespace(bytes_sent=0, bytes_recv=0)}
    c2 = {"eth0": SimpleNamespace(bytes_sent=0, bytes_recv=0)}
    ports = {80: "web"}
    snapshots = [make_snapshot(interfaces, c1, ports), make_snapshot(interfaces, c2, ports)]

    def fake_info():
        snap = snapshots.pop(0)
        if not snapshots:
            stop.set()
        return snap

    called = []
    monkeypatch.setattr(network_daemon, "_get_net_info", fake_info)
    monkeypatch.setattr(network_daemon, "_ping", lambda ip: False)
    monkeypatch.setattr(network_daemon, "_enqueue_resync", lambda d: called.append("resync"))
    config = {"network_policies": {"allow_ports": [80], "block_ports": [], "max_bandwidth_percent": 90, "mode": "monitor_only"}, "federation_peer_ip": "1.2.3.4"}
    network_daemon.run_loop(stop, q, config, poll_interval=0)
    events = [q.get_nowait() for _ in range(q.qsize())]
    assert any(e["event"] == "federation_link_down" for e in events)
    assert called == ["resync"]
