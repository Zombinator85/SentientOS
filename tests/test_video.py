import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger
import presence_ledger as pl
import admin_utils


def test_log_video_event(monkeypatch):
    entries = []

    def fake_append(path: Path, entry: dict):
        entries.append(entry)
        return entry

    monkeypatch.setattr(ledger, "_append", fake_append)
    e = ledger.log_video_create("p", "t", "f.mp4", {"Joy": 1.0}, user="u")
    assert e["title"] == "t"
    assert entries[0]["file"] == "f.mp4"
    watch = ledger.log_video_watch("f.mp4", user="u", perceived={"Calm": 0.5})
    assert watch["event"] == "watched"


def test_presence_video(monkeypatch, tmp_path):
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"data")
    monkeypatch.setattr(pl, "LEDGER_PATH", tmp_path / "presence.jsonl")
    pl.log_video_event("alice", "p", "demo", str(vid), {"Joy": 1.0})
    pl.log_video_watch("alice", str(vid), {"Calm": 1.0})
    data = (tmp_path / "presence.jsonl").read_text().splitlines()
    assert any("video_created" in d for d in data)
    assert any("video_watched" in d for d in data)


def test_video_cli_create(monkeypatch, tmp_path, capsys):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"data")
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    monkeypatch.setattr(sys, "argv", [
        "video_cli.py", "create", str(video), "Clip", "--prompt", "hi", "--emotion", "Joy=1.0"
    ])
    import video_cli
    import importlib
    importlib.reload(video_cli)
    video_cli.main()
    out = capsys.readouterr().out
    assert "Clip" in out
