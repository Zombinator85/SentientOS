import json
import os
import sys
from pathlib import Path
import pytest


import sentientos.ledger as ledger
import sentientos.presence_ledger as pl
import sentientos.admin_utils as admin_utils


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
    import sentientos.video_cli as video_cli
    import importlib
    importlib.reload(video_cli)
    video_cli.main()
    out = capsys.readouterr().out
    assert "Clip" in out


def test_log_video_share(monkeypatch, tmp_path):
    entries = []

    def fake_append(path: Path, entry: dict):
        entries.append(entry)
        return entry

    pub = tmp_path / "public.jsonl"
    monkeypatch.setattr(ledger, "_append", fake_append)
    monkeypatch.setattr(ledger.doctrine, "PUBLIC_LOG", pub)
    monkeypatch.setattr(ledger.doctrine, "log_json", lambda p, obj: pub.open("a").write(json.dumps(obj)+"\n"))

    entry = ledger.log_video_share("demo.mp4", peer="ally", user="Ada", emotion={"Joy":1.0})
    assert entry["event"] == "shared"
    assert any(e.get("event") == "mood_blessing" for e in entries)


def test_video_cli_share(monkeypatch, tmp_path, capsys):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"data")
    monkeypatch.setattr(ledger, "log_video_watch", lambda *a, **k: {"watch": True})
    monkeypatch.setattr(ledger, "log_video_share", lambda *a, **k: {"shared": True})
    monkeypatch.setattr(ledger, "log_federation", lambda *a, **k: {"federated": True})
    monkeypatch.setattr(pl, "log", lambda *a, **k: None)
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "Joy=1.0")
    monkeypatch.setattr(sys, "argv", ["video_cli.py", "play", str(video), "--share", "ally"])
    import sentientos.video_cli as video_cli
    import importlib
    importlib.reload(video_cli)
    video_cli.main()
    out = capsys.readouterr().out
    assert "watch" in out or "shared" in out
