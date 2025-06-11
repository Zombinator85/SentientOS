"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import sys
import os
from importlib import reload
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import reflection_log_cli as rlc


def test_export_day(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    day_file = log_dir / "2025-01-01.log"
    day_file.write_text("one\ntwo\n")
    monkeypatch.setenv("REFLECTION_LOG_DIR", str(log_dir))
    reload(rlc)
    out = tmp_path / "out.txt"
    ok = rlc.export_day("2025-01-01", out, markdown=True)
    assert ok
    text = out.read_text()
    assert "- one" in text and "- two" in text
