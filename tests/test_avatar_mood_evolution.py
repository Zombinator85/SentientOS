"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import json
import os
from pathlib import Path

import avatar_mood_evolution as ame


def test_mood_stats(tmp_path, monkeypatch):
    log = tmp_path / "mood.jsonl"
    entries = [
        {"timestamp": "1", "avatar": "a", "mood": {"Joy": 1}},
        {"timestamp": "2", "avatar": "a", "mood": {"Sad": 1}},
        {"timestamp": "3", "avatar": "b", "mood": {"Calm": 1}},
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries))
    monkeypatch.setenv("AVATAR_MEMORY_LINK_LOG", str(log))
    importlib.reload(ame)
    hist = ame.mood_history("a")
    stats = ame.mood_stats("a")
    assert len(hist) == 2
    assert stats["Joy"] == 1 and stats["Sad"] == 1

