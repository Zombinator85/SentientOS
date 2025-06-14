from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import importlib
import os
from pathlib import Path

import presence_ledger as pl


def test_presence_bridge_metadata(tmp_path, monkeypatch):
    path = tmp_path / "user_presence.jsonl"
    monkeypatch.setenv("USER_PRESENCE_LOG", str(path))
    monkeypatch.setenv("PRESENCE_BRIDGE", "telegram")
    importlib.reload(pl)
    pl.log("alice", "greet")
    pl.log_privilege("alice", "Linux", "tool", "success")
    lines = [json.loads(x)["data"] for x in path.read_text().splitlines()]
    assert all(entry.get("bridge") == "telegram" for entry in lines)
