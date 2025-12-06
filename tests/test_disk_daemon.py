"""Privilege rituals have been replaced by autonomous covenant alignment."""
from __future__ import annotations

import threading
from queue import Queue

from daemon import disk_daemon


def drain(q: Queue) -> list[dict]:
    items: list[dict] = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def test_emotion_pump_normal_usage(tmp_path, monkeypatch):
    pulse = tmp_path / "pulse"
    stop = threading.Event()
    q: Queue = Queue()
    monkeypatch.setattr(disk_daemon, "_get_mounts", lambda: ["/"])

    def usage(_):
        stop.set()
        return {"total": 100, "used": 50, "free": 50, "percent": 50}

    monkeypatch.setattr(disk_daemon, "_disk_usage", usage)
    monkeypatch.setattr(disk_daemon, "_read_io", lambda prev, interval: (0.0, 0.0, prev))
    monkeypatch.setattr(disk_daemon, "_check_smart_health", lambda: [])
    config = {"disk_threshold_warn": 90, "disk_threshold_critical": 95, "prune_paths": []}
    disk_daemon.run_loop(stop, q, config, poll_interval=0, pulse_dir=pulse)
    assert not (pulse / "disk_pressure").exists()
    events = drain(q)
    assert any(e["event"] == "disk_state" for e in events)
    assert not any(e["event"] == "disk_pressure" for e in events)
    assert not any(e["event"] == "disk_critical" for e in events)


def test_emotion_pump_pressure_and_recovery(tmp_path, monkeypatch):
    pulse = tmp_path / "pulse"
    stop = threading.Event()
    q: Queue = Queue()
    monkeypatch.setattr(disk_daemon, "_get_mounts", lambda: ["/"])
    vals = [92.0, 50.0]

    def usage(_):
        val = vals.pop(0)
        if not vals:
            stop.set()
        return {"total": 100, "used": val, "free": 100 - val, "percent": val}

    monkeypatch.setattr(disk_daemon, "_disk_usage", usage)
    monkeypatch.setattr(disk_daemon, "_read_io", lambda prev, interval: (0.0, 0.0, prev))
    monkeypatch.setattr(disk_daemon, "_check_smart_health", lambda: [])
    config = {"disk_threshold_warn": 90, "disk_threshold_critical": 95, "prune_paths": []}
    disk_daemon.run_loop(stop, q, config, poll_interval=0, pulse_dir=pulse)
    events = drain(q)
    assert any(e["event"] == "disk_pressure" for e in events)
    assert not (pulse / "disk_pressure").exists()


def test_emotion_pump_critical_prune(tmp_path, monkeypatch):
    pulse = tmp_path / "pulse"
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "old.txt").write_text("x" * 10)
    stop = threading.Event()
    q: Queue = Queue()
    monkeypatch.setattr(disk_daemon, "_get_mounts", lambda: ["/"])

    def usage(_):
        stop.set()
        return {"total": 100, "used": 96, "free": 4, "percent": 96}

    monkeypatch.setattr(disk_daemon, "_disk_usage", usage)
    monkeypatch.setattr(disk_daemon, "_read_io", lambda prev, interval: (0.0, 0.0, prev))
    monkeypatch.setattr(disk_daemon, "_check_smart_health", lambda: [])
    config = {
        "disk_threshold_warn": 90,
        "disk_threshold_critical": 95,
        "prune_paths": [str(cache)],
    }
    disk_daemon.run_loop(stop, q, config, poll_interval=0, pulse_dir=pulse)
    events = drain(q)
    assert any(e["event"] == "disk_critical" for e in events)
    prune_events = [e for e in events if e["event"] == "disk_prune"]
    assert prune_events and int(prune_events[0]["freed_space"]) > 0
    assert not any(cache.iterdir())


def test_emotion_pump_io_overload(tmp_path, monkeypatch):
    pulse = tmp_path / "pulse"
    stop = threading.Event()
    q: Queue = Queue()
    monkeypatch.setattr(disk_daemon, "_get_mounts", lambda: ["/"])
    monkeypatch.setattr(disk_daemon, "_disk_usage", lambda m: {"total": 100, "used": 10, "free": 90, "percent": 10})
    vals = [(2e7, 0.0), (2e7, 0.0), (2e7, 0.0)]

    def read_io(prev, interval):
        r, w = vals.pop(0)
        if not vals:
            stop.set()
        return r, w, prev

    monkeypatch.setattr(disk_daemon, "_read_io", read_io)
    monkeypatch.setattr(disk_daemon, "_check_smart_health", lambda: [])
    config = {"disk_threshold_warn": 90, "disk_threshold_critical": 95, "prune_paths": []}
    disk_daemon.run_loop(stop, q, config, poll_interval=0, pulse_dir=pulse)
    events = drain(q)
    assert any(e["event"] == "disk_io_overload" for e in events)


def test_emotion_pump_smart_failure(tmp_path, monkeypatch):
    pulse = tmp_path / "pulse"
    stop = threading.Event()
    q: Queue = Queue()
    monkeypatch.setattr(disk_daemon, "_get_mounts", lambda: ["/"])
    monkeypatch.setattr(disk_daemon, "_disk_usage", lambda m: {"total": 100, "used": 10, "free": 90, "percent": 10})

    def smart_fail():
        stop.set()
        return ["/dev/sda"]

    monkeypatch.setattr(disk_daemon, "_check_smart_health", smart_fail)
    monkeypatch.setattr(disk_daemon, "_read_io", lambda prev, interval: (0.0, 0.0, prev))
    config = {"disk_threshold_warn": 90, "disk_threshold_critical": 95, "prune_paths": []}
    disk_daemon.run_loop(stop, q, config, poll_interval=0, pulse_dir=pulse)
    events = drain(q)
    assert any(e["event"] == "disk_failure" for e in events)
