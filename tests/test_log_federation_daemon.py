from __future__ import annotations

import os
import threading
import time
from queue import Empty, Queue

from daemon.log_federation_daemon import run_loop


def drain(q: Queue) -> list[dict]:
    items: list[dict] = []
    while True:
        try:
            items.append(q.get_nowait())
        except Empty:
            break
    return items


def test_emotion_pump_sync(tmp_path):
    local_glow = tmp_path / "glow"
    local_ledger = tmp_path / "ledger"
    peer_root = tmp_path / "peer"
    stop = threading.Event()
    ledger = Queue()
    t = threading.Thread(
        target=run_loop,
        args=(stop, ledger, str(peer_root), "local_mount"),
        kwargs={"poll_interval": 0.1, "base_glow": local_glow, "base_ledger": local_ledger},
        daemon=True,
    )
    t.start()
    file_path = local_glow / "note.txt"
    local_glow.mkdir()
    file_path.write_text("hi", encoding="utf-8")
    time.sleep(0.5)
    stop.set()
    t.join(timeout=2)
    synced = peer_root / "glow" / "note.txt"
    assert synced.read_text(encoding="utf-8") == "hi"
    logs = drain(ledger)
    assert any(e["event"] == "federation_sync" and e["direction"] == "push" and e["status"] == "success" for e in logs)


def test_emotion_pump_conflict(tmp_path):
    local_glow = tmp_path / "glow"
    peer_root = tmp_path / "peer"
    peer_glow = peer_root / "glow"
    local_glow.mkdir()
    peer_glow.mkdir(parents=True)
    f = "conflict.txt"
    (local_glow / f).write_text("old", encoding="utf-8")
    time.sleep(0.1)
    (peer_glow / f).write_text("new", encoding="utf-8")
    os.utime(peer_glow / f, None)  # ensure peer is newer
    stop = threading.Event()
    ledger = Queue()
    t = threading.Thread(
        target=run_loop,
        args=(stop, ledger, str(peer_root), "local_mount"),
        kwargs={"poll_interval": 0.1, "base_glow": local_glow, "base_ledger": tmp_path / "ledger"},
        daemon=True,
    )
    t.start()
    time.sleep(0.5)
    stop.set()
    t.join(timeout=2)
    assert (local_glow / f).read_text(encoding="utf-8") == "new"
    assert (peer_glow / f).read_text(encoding="utf-8") == "new"
    logs = drain(ledger)
    assert any(e["event"] == "federation_conflict" for e in logs)


def test_emotion_pump_offline_retry(tmp_path):
    local_glow = tmp_path / "glow"
    peer_root = tmp_path / "peer"
    peer_root.write_text("offline")  # simulate peer path as file
    stop = threading.Event()
    ledger = Queue()
    t = threading.Thread(
        target=run_loop,
        args=(stop, ledger, str(peer_root), "local_mount"),
        kwargs={"poll_interval": 0.1, "base_glow": local_glow, "base_ledger": tmp_path / "ledger"},
        daemon=True,
    )
    t.start()
    local_glow.mkdir()
    (local_glow / "retry.txt").write_text("data", encoding="utf-8")
    time.sleep(0.3)
    logs = drain(ledger)
    assert any(e["status"] == "fail" for e in logs)
    peer_root.unlink()
    (peer_root / "glow").mkdir(parents=True)
    (peer_root / "ledger").mkdir()
    time.sleep(0.6)
    stop.set()
    t.join(timeout=2)
    assert (peer_root / "glow" / "retry.txt").read_text(encoding="utf-8") == "data"
    logs = drain(ledger)
    assert any(e["status"] == "success" for e in logs)

