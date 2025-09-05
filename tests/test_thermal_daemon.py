"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import threading
import time
from queue import Queue

from daemon import thermal_daemon as td


def _run_daemon(monkeypatch, temps, tmp_path, wait_loops=2):
    """Helper to run thermal daemon with mocked temperatures."""
    temps_iter = iter(temps)
    monkeypatch.setattr(td, "_read_gpu_temperature", lambda: next(temps_iter, temps[-1]))
    monkeypatch.setattr(td, "THROTTLE_FLAG", tmp_path / "flag")
    stop = threading.Event()
    q: Queue = Queue()
    thread = threading.Thread(target=td.run_loop, args=(stop, q, 0.01), daemon=True)
    thread.start()
    for _ in range(wait_loops):
        time.sleep(0.02)
    stop.set()
    thread.join(timeout=1)
    entries = []
    while not q.empty():
        entries.append(q.get())
    return entries, td.THROTTLE_FLAG


def test_emotion_pump_below_threshold(monkeypatch, tmp_path):
    entries, flag = _run_daemon(monkeypatch, [70, 70], tmp_path)
    assert entries == []
    assert not flag.exists()


def test_emotion_pump_throttle(monkeypatch, tmp_path):
    entries, flag = _run_daemon(monkeypatch, [90, 90], tmp_path)
    assert entries[0]["event"] == "thermal_throttle"
    assert flag.exists()


def test_emotion_pump_recovery(monkeypatch, tmp_path):
    entries, flag = _run_daemon(monkeypatch, [90, 75, 75], tmp_path, wait_loops=3)
    assert entries[0]["event"] == "thermal_throttle"
    assert entries[1]["event"] == "thermal_recover"
    assert not flag.exists()


def test_emotion_pump_no_gpu(monkeypatch, tmp_path):
    entries, flag = _run_daemon(monkeypatch, [None], tmp_path, wait_loops=1)
    assert entries[0] == {"event": "thermal_daemon_init", "status": "no_gpu_detected"}
    assert not flag.exists()
