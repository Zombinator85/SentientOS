from logging_config import get_log_path
import os
import sys
import json
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import mood_wall
import presence_ledger as pl
import ledger


def test_wall_load_and_bless(monkeypatch, tmp_path):
    log = tmp_path / "music_log.jsonl"
    entries = [
        {"timestamp": "t1", "event": "shared", "file": "a.mp3", "emotion": {"reported": {"Joy": 1.0}}, "user": "Ada", "peer": "ally"},
        {"timestamp": "t2", "event": "mood_blessing", "sender": "Ada", "recipient": "ally", "emotion": {"Joy": 1.0}, "phrase": "be well"},
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

    orig_exists = Path.exists
    orig_read = Path.read_text

    def fake_exists(self):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return True
        return orig_exists(self)

    def fake_read(self, encoding="utf-8"):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return log.read_text(encoding=encoding)
        return orig_read(self, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read)

    wall = mood_wall.load_wall()
    assert len(wall) == 2
    totals = mood_wall.top_moods(wall)
    assert totals["Joy"] == 2
    rec = []

    def fake_log(sender, recipient, emotion, phrase):
        rec.append(phrase)
        return {"ok": True}

    monkeypatch.setattr(ledger, "log_mood_blessing", fake_log)

    mood_wall.bless_mood("Joy", "Ada")
    assert rec and "Ada blesses Joy" in rec[0]


def test_sync_wall_http(monkeypatch, tmp_path):
    data = [{"event": "shared", "file": "a", "timestamp": "t"}]
    class Resp:
        def raise_for_status(self):
            pass
        def json(self):
            return data
    def fake_get(url, timeout=10):
        return Resp()

    log = tmp_path / "music_log.jsonl"
    monkeypatch.setattr(mood_wall, "LOG", log)
    monkeypatch.setattr(mood_wall, "requests", type("obj", (), {"get": fake_get}))
    count = mood_wall.sync_wall_http("http://peer")
    assert count == 1
    assert log.exists() and "a" in log.read_text()
