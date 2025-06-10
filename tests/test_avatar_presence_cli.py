"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import importlib
from pathlib import Path

import avatar_presence_cli as ap


def test_log_invocation(tmp_path, monkeypatch, capsys):
    log = tmp_path / "presence.jsonl"
    monkeypatch.setenv("AVATAR_PRESENCE_LOG", str(log))
    importlib.reload(ap)
    ap.log_invocation("a.blend", "test", "visual")
    assert log.exists()
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    data = ap.log_invocation("a.blend", "test2")
    assert data["reason"] == "test2"

