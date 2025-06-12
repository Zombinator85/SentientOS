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

import narrator


def test_narrator_dry_run(tmp_path, monkeypatch, capsys):
    log_dir = tmp_path
    mem = log_dir / "memory.jsonl"
    refl = log_dir / "reflection.jsonl"
    emo = log_dir / "emotions.jsonl"
    day = "2024-01-01"
    mem.write_text(json.dumps({"timestamp": f"{day}T10:00:00", "text": "boot", "emotions": {"Joy": 0.9}}) + "\n", encoding="utf-8")
    refl.write_text(json.dumps({"timestamp": f"{day}T12:00:00", "text": "all good"}) + "\n", encoding="utf-8")
    emo.write_text(json.dumps({"timestamp": f"{day}T11:00:00", "emotions": {"Joy": 0.8}}) + "\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["nr", "--date", day, "--log-dir", str(log_dir), "--dry-run"])
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    narrator.main()
    out = capsys.readouterr().out
    assert "System mood" in out
    assert "boot" in out
