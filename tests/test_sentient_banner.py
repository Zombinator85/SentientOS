"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import sentient_banner as sb
import admin_utils
import presence_ledger as pl


def test_timestamped_closing(capsys):
    sb.print_timestamped_closing()
    out = capsys.readouterr().out
    assert "Presence is law" in out and "[" in out and "]" in out


def test_print_banner(capsys, monkeypatch):
    monkeypatch.setattr(admin_utils, "is_admin", lambda: True)
    monkeypatch.setattr(pl, "recent_privilege_attempts", lambda n=3: [{"status": "success"}])
    sb.print_banner()
    out = capsys.readouterr().out
    assert "Privilege Status" in out
    assert "success" in out
