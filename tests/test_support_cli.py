"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import os
import sys
import importlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import support_cli
import pytest
import support_log
import sentient_banner as sb


def test_support_bless(monkeypatch, capsys):
    def fake_add(name, message, amount=""):
        return {"supporter": name, "message": message, "amount": amount}
    monkeypatch.setattr(support_log, 'add', fake_add)
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, 'argv', ['support', '--bless', '--name', 'Ada', '--message', 'hi', '--amount', '0'])
    importlib.reload(support_cli)
    support_cli.main()
    out = capsys.readouterr().out
    assert 'sanctuary acknowledged' in out
    assert calls["snap"] >= 2 and calls["recap"] == 1

def test_support_bless_fail(monkeypatch, capsys):
    def fake_add(name, message, amount=""):
        raise RuntimeError('fail')
    monkeypatch.setattr(support_log, 'add', fake_add)
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, 'argv', ['support', '--bless', '--name', 'Ada', '--message', 'hi', '--amount', '0'])
    importlib.reload(support_cli)
    support_cli.main()
    out = capsys.readouterr().out
    assert 'Failed to record blessing' in out
    assert calls["snap"] >= 2 and calls["recap"] == 1
