import os
import sys
import importlib
import json
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger
import music_cli
import jukebox_integration
import presence_ledger as pl
import sentient_banner as sb
import admin_utils


def test_log_music(monkeypatch, tmp_path):
    entries = []

    def fake_append(path: Path, entry: dict):
        entries.append(entry)
        return entry

    monkeypatch.setattr(ledger, "_append", fake_append)
    e = ledger.log_music("p", {"Joy": 1.0}, "f.mp3", "hash", "u")
    assert e["prompt"] == "p"
    assert entries[0]["file"] == "f.mp3"
    assert "emotion" in entries[0] and entries[0]["emotion"]["intended"]["Joy"] == 1.0

    listen = ledger.log_music_listen("f.mp3", user="u", reported={"Calm": 0.5})
    assert listen["event"] == "listened"


def test_music_cli_generate(monkeypatch, tmp_path, capsys):
    song = tmp_path / "song.mp3"
    song.write_bytes(b"data")

    async def fake_gen(self, prompt, emotion):
        return str(song)

    monkeypatch.setattr(jukebox_integration.JukeboxIntegration, "generate_music", fake_gen)
    monkeypatch.setattr(ledger, "log_music", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(pl, "log", lambda *a, **k: None)
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, "argv", ["music_cli.py", "generate", "hi"])
    importlib.reload(music_cli)
    music_cli.main()
    out = capsys.readouterr().out
    assert "ok" in out
    assert calls["snap"] >= 2 and calls["recap"] == 1


def test_music_cli_play(monkeypatch, tmp_path, capsys):
    track = tmp_path / "song.mp3"
    track.write_bytes(b"data")

    monkeypatch.setattr(ledger, "log_music_listen", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(pl, "log", lambda *a, **k: None)
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "Happy=1.0")
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, "argv", ["music_cli.py", "play", str(track)])
    importlib.reload(music_cli)
    music_cli.main()
    out = capsys.readouterr().out
    assert "ok" in out
    assert calls["snap"] >= 2 and calls["recap"] == 1
