"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
import importlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import ledger_cli
import sentient_banner as sb
import ledger
import admin_utils
import pytest


def test_ledger_cli_summary(monkeypatch):
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, "argv", ["ledger", "--summary"])
    importlib.reload(ledger_cli)
    ledger_cli.main()
    assert calls["snap"] >= 2 and calls["recap"] == 1


def test_ledger_cli_error(monkeypatch):
    monkeypatch.setattr(ledger, "log_support", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, "argv", ["ledger", "--support", "--name", "A", "--message", "B", "--amount", "1"])
    importlib.reload(ledger_cli)
    with pytest.raises(RuntimeError):
        ledger_cli.main()
    assert calls["snap"] >= 2 and calls["recap"] == 1
