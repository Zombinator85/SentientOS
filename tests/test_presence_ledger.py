import json
import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import presence_ledger as pl

def test_recent_privilege_attempts(tmp_path, monkeypatch):
    path = tmp_path / "user_presence.jsonl"
    monkeypatch.setenv("USER_PRESENCE_LOG", str(path))
    entries = [
        {"timestamp": "t1", "event": "admin_privilege_check", "status": "success"},
        {"timestamp": "t2", "event": "admin_privilege_check", "status": "failed"},
        {"timestamp": "t3", "event": "something_else"},
    ]
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    import importlib
    importlib.reload(pl)
    recent = pl.recent_privilege_attempts()
    assert len(recent) == 2
    assert recent[0]["timestamp"] == "t1"
    assert recent[1]["status"] == "failed"


def test_log_privilege(tmp_path, monkeypatch):
    path = tmp_path / "user_presence.jsonl"
    monkeypatch.setenv("USER_PRESENCE_LOG", str(path))
    import importlib
    importlib.reload(pl)
    pl.log_privilege("tester", "Linux", "tool", "success")
    data = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert data["user"] == "tester"
    assert data["platform"] == "Linux"
    assert data["tool"] == "tool"
    assert data["status"] == "success"


def test_music_stats(tmp_path, monkeypatch):
    mus = tmp_path / "music_log.jsonl"
    entries = [
        {"event": "shared", "emotion": {"reported": {"Joy": 1.0}}},
        {"event": "generated", "emotion": {"intended": {"Joy": 0.5}}},
    ]
    with mus.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    orig_exists = Path.exists
    orig_read = Path.read_text

    def fake_exists(self):
        if str(self) == "logs/music_log.jsonl":
            return True
        return orig_exists(self)

    def fake_read(self, encoding="utf-8"):
        if str(self) == "logs/music_log.jsonl":
            return mus.read_text(encoding=encoding)
        return orig_read(self, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read)
    stats = pl.music_stats()
    assert stats["events"]["shared"] == 1
    assert stats["emotions"]["Joy"] > 1.0 - 0.1
