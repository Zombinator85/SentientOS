from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Banner: This script requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import importlib
import sys
from pathlib import Path

import avatar_presence_cli as ap
import avatar_gallery_cli as ag


def test_gallery_listing(tmp_path, monkeypatch, capsys):
    log = tmp_path / "presence.jsonl"
    monkeypatch.setenv("AVATAR_PRESENCE_LOG", str(log))
    importlib.reload(ap)
    importlib.reload(ag)
    ap.log_invocation("a.blend", "ritual")
    monkeypatch.setattr(sys, "argv", ["gallery"])
    ag.main()
    out = capsys.readouterr().out
    assert "a.blend" in out


