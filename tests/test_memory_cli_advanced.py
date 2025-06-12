"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
import json
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import importlib
import memory_cli
import memory_tail
import admin_utils


def test_tail_follow(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    Path("logs").mkdir(exist_ok=True)
    Path("logs/memory.jsonl").write_text("{}\n")
    called = []
    monkeypatch.setattr(memory_tail, "tail_memory", lambda p: called.append(p))
    monkeypatch.setattr(sys, "argv", ["mc", "tail", "--follow"])
    importlib.reload(memory_cli)
    memory_cli.main()
    assert called


def test_list_since(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    raw = Path(os.environ["SENTIENTOS_LOG_DIR"]) / "memory" / "raw"
    raw.mkdir(parents=True)
    (raw / "a.json").write_text(json.dumps({"timestamp": "2024-01-01T00:00:00", "text": "old"}))
    (raw / "b.json").write_text(json.dumps({"timestamp": "2024-01-02T00:00:00", "text": "new"}))
    monkeypatch.setattr(sys, "argv", ["mc", "list", "--since", "2024-01-02T00:00:00"])
    import memory_manager
    importlib.reload(memory_manager)
    importlib.reload(memory_cli)
    memory_cli.main()
    out = capsys.readouterr().out
    assert "new" in out
    assert "old" not in out
