"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import admin_utils
import sentientos.__main__ as sm


def test_main(monkeypatch, capsys):
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    monkeypatch.setattr(admin_utils, "require_lumos_approval", lambda: None)
    importlib.reload(sm)
    sm.main()
    out = capsys.readouterr().out
    assert "SentientOS" in out
