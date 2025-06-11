import os
import sys
import importlib
import sentientos.ledger_cli as ledger_cli
import sentientos.sentient_banner as sb
import sentientos.ledger as ledger
import sentientos.admin_utils as admin_utils
import pytest


def test_ledger_cli_summary(monkeypatch):
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    monkeypatch.setattr(sys, "argv", ["ledger", "--summary"])
    importlib.reload(ledger_cli)
    ledger_cli.main()
    assert calls["snap"] >= 2 and calls["recap"] == 1


def test_ledger_cli_error(monkeypatch):
    monkeypatch.setattr(ledger, "log_support", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(admin_utils, "require_admin_banner", lambda: None)
    monkeypatch.setattr(sys, "argv", ["ledger", "--support", "--name", "A", "--message", "B", "--amount", "1"])
    importlib.reload(ledger_cli)
    with pytest.raises(RuntimeError):
        ledger_cli.main()
    assert calls["snap"] >= 2 and calls["recap"] == 1
