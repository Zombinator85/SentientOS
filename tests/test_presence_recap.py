"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


from logging_config import get_log_path
import os
import sys
import json
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import presence_ledger as pl
import importlib


def test_presence_recap(monkeypatch, tmp_path):
    mus = tmp_path / "music_log.jsonl"
    entries = [
        {"event": "shared", "emotion": {"reported": {"Joy": 1.0}}, "file": "a"},
        {"event": "mood_blessing", "emotion": {"Joy":1.0}}
    ]
    mus.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

    orig_exists = Path.exists
    orig_read = Path.read_text

    def fake_exists(self):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return True
        return orig_exists(self)

    def fake_read(self, encoding="utf-8"):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return mus.read_text(encoding=encoding)
        return orig_read(self, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read)

    importlib.reload(pl)
    data = pl.recap()
    assert data["music"]["most_shared_mood"] == "Joy"
    assert data["blessings"] == 1


def test_recap_milestone(monkeypatch, tmp_path):
    mus = tmp_path / "music_log.jsonl"
    entries = [
        {"event": "reflection", "emotion": {"reported": {"Grief": 1.0}}}
        for _ in range(10)
    ]
    mus.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

    orig_exists = Path.exists
    orig_read = Path.read_text

    def fake_exists(self):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return True
        return orig_exists(self)

    def fake_read(self, encoding="utf-8"):
        if str(self) == str(get_log_path("music_log.jsonl")):
            return mus.read_text(encoding=encoding)
        return orig_read(self, encoding=encoding)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read)

    import importlib
    importlib.reload(pl)
    data = pl.recap()
    assert any("Grief" in m for m in data["milestones"])
