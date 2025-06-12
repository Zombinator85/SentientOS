"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


from logging_config import get_log_path
import os
import sys
import importlib
import json
import pytest
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger
import doctrine
import music_cli
import jukebox_integration
import presence_ledger as pl
import sentient_banner as sb
import admin_utils
import mood_wall


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
    assert "received" in entries[0]["emotion"]

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
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, "argv", ["music_cli.py", "generate", "hi"])
    importlib.reload(music_cli)
    music_cli.main()
    out = capsys.readouterr().out
    assert "ok" in out
    assert calls["snap"] >= 2 and calls["recap"] == 1


def test_music_cli_recap(monkeypatch, tmp_path, capsys):
    log = tmp_path / "music_log.jsonl"
    entries = [json.dumps({"timestamp": "1", "emotion": {"reported": {"Joy": 0.5}}})]
    log.write_text("\n".join(entries))

    orig_exists = Path.exists
    orig_read = Path.read_text

    def fake_exists(self):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return True
        return orig_exists(self)

    def fake_read_text(self, encoding="utf-8"):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return log.read_text(encoding=encoding)
        return orig_read(self, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)
    monkeypatch.setattr(sys, "argv", ["music_cli.py", "recap", "--emotion", "--limit", "1"])
    importlib.reload(music_cli)
    music_cli.main()
    out = capsys.readouterr().out
    assert "Joy" in out


def test_music_cli_play(monkeypatch, tmp_path, capsys):
    track = tmp_path / "song.mp3"
    track.write_bytes(b"data")

    monkeypatch.setattr(ledger, "log_music_listen", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(pl, "log", lambda *a, **k: None)
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


def test_playlist_and_blessing(monkeypatch, tmp_path):
    log = tmp_path / "music_log.jsonl"
    pub = tmp_path / "public.jsonl"
    entries = [
        json.dumps({
            "timestamp": "t1",
            "event": "shared",
            "file": "a.mp3",
            "emotion": {"reported": {"Joy": 1.0}},
            "user": "Ada",
            "peer": "ally",
        })
    ]
    log.write_text("\n".join(entries), encoding="utf-8")

    orig_exists = Path.exists
    orig_read = Path.read_text

    def fake_exists(self):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return True
        if str(self) == str(pub):
            return True
        return orig_exists(self)

    def fake_read(self, encoding="utf-8"):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return log.read_text(encoding=encoding)
        return orig_read(self, encoding=encoding)

    rec = []

    def fake_append(path: Path, entry: dict):
        rec.append(entry)
        return entry

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read)
    monkeypatch.setattr(ledger, "_append", fake_append)
    monkeypatch.setattr(doctrine, "PUBLIC_LOG", pub)
    monkeypatch.setattr(doctrine, "log_json", lambda p, obj: pub.open("a").write(json.dumps(obj)+"\n"))

    plist = ledger.playlist_by_mood("Joy")
    assert plist and plist[0]["file"] == "a.mp3"
    entry = ledger.log_music_share("a.mp3", peer="ally", user="Ada", emotion={"Joy":1.0})
    assert any(e.get("event") == "mood_blessing" for e in rec)


def test_music_cli_share(monkeypatch, tmp_path, capsys):
    track = tmp_path / "song.mp3"
    track.write_bytes(b"data")

    monkeypatch.setattr(ledger, "log_music_listen", lambda *a, **k: {"listen": True})
    monkeypatch.setattr(ledger, "log_music_share", lambda *a, **k: {"shared": True})
    monkeypatch.setattr(ledger, "log_federation", lambda *a, **k: {"federated": True})
    monkeypatch.setattr(pl, "log", lambda *a, **k: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "Joy=1.0")
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, "argv", ["music_cli.py", "play", str(track), "--share", "ally"])
    importlib.reload(music_cli)
    music_cli.main()
    out = capsys.readouterr().out
    assert "shared" in out or "listen" in out
    assert calls["snap"] >= 2 and calls["recap"] == 1


def test_music_cli_wall_global(monkeypatch, capsys):
    monkeypatch.setattr(mood_wall, "peers_from_federation", lambda: ["p1", "p2"])
    logged = []
    monkeypatch.setattr(ledger, "log_mood_blessing", lambda u, r, e, p: logged.append(r) or {"ok": True})
    monkeypatch.setattr(sys, "argv", ["music_cli.py", "wall", "--bless", "Joy", "--global"])
    import music_cli
    import importlib
    importlib.reload(music_cli)
    music_cli.main()
    out = capsys.readouterr().out
    assert "p1" in out and "p2" in out
    assert len(logged) == 2


def test_playlist_explanation(monkeypatch, capsys):
    monkeypatch.setattr(mood_wall, "load_wall", lambda n=100: [{"mood": ["Hope"]}]*2)
    monkeypatch.setattr(mood_wall, "top_moods", lambda events: {"Hope": len(events)})
    monkeypatch.setattr(mood_wall, "latest_blessing_for", lambda m: {"sender": "Ada"})
    monkeypatch.setattr(ledger, "playlist_by_mood", lambda m, l: [{"file": "a"}])
    monkeypatch.setattr(sys, "argv", ["music_cli.py", "playlist", "Joy"])
    import music_cli
    import importlib
    importlib.reload(music_cli)
    music_cli.main()
    out = capsys.readouterr().out
    assert "blessed by Ada" in out
