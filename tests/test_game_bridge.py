"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import json
from pathlib import Path

import game_bridge as gb


def test_logging(tmp_path, monkeypatch):
    log = tmp_path / "game.jsonl"
    monkeypatch.setenv("GAME_BRIDGE_LOG", str(log))
    importlib.reload(gb)

    gb.avatar_ritual_bridge("minecraft", "Lumos", "crowned", "0,0,0")
    gb.build_sanctuary("valheim", "Shrine", "1,2,3")
    gb.presence_pulse("minecraft", "active")

    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["event"] == "avatar_ritual_bridge"
    assert first["game"] == "minecraft"
