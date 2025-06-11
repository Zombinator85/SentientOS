"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
from importlib import reload
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import reflection_log_cli as rlc


def test_search_entries(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2025-01-01.log").write_text("one keyword here\nsecond line\n")
    monkeypatch.setenv("REFLECTION_LOG_DIR", str(log_dir))
    reload(rlc)
    results = list(rlc.search_entries("keyword"))
    assert results and "keyword" in results[0][1]
