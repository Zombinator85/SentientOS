"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import importlib
import admin_utils
import sentientos.__main__ as sm


def test_main(monkeypatch, capsys):
    importlib.reload(sm)
    sm.main()
    out = capsys.readouterr().out
    assert "SentientOS" in out
