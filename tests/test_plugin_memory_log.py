"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import json
import importlib
import datetime
import os
from pathlib import Path


def test_plugin_memory_logged(tmp_path, monkeypatch):
    mem_dir = tmp_path / "mem"
    monkeypatch.setenv("MEMORY_DIR", str(mem_dir))
    monkeypatch.setenv("USER_PRESENCE_LOG", str(tmp_path / "user_presence.jsonl"))
    monkeypatch.setenv("PRESENCE_LOG", str(tmp_path / "presence_log.jsonl"))
    monkeypatch.setenv("PRESENCE_BRIDGE", "test_plugin")
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    import plugin_framework as pf
    import presence_ledger as pl
    import memory_manager as mm
    import plugins.escalate as escalate
    importlib.reload(pl)
    importlib.reload(mm)
    importlib.reload(pf)
    escalate.register(None)
    pf.run_plugin("escalate", {"goal": "bridge", "text": "check"})
    mm.summarize_memory()
    day = datetime.date.today().isoformat()
    summary = mem_dir / "distilled" / f"{day}.txt"
    assert summary.exists()
    log_file = tmp_path / "presence_log.jsonl"
    entries = [json.loads(l)["data"] for l in log_file.read_text().splitlines()]
    assert any(e.get("bridge") == "test_plugin" for e in entries)
