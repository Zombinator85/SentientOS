import os
import sys
import importlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import support_cli
import support_log
import ledger


def test_support_bless(monkeypatch, capsys):
    def fake_add(name, message, amount=""):
        return {"supporter": name, "message": message, "amount": amount}
    monkeypatch.setattr(support_log, 'add', fake_add)
    calls = {"snap": 0, "recap": 0}
    monkeypatch.setattr(ledger, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(ledger, "print_recap", lambda limit=3: calls.__setitem__("recap", calls["recap"] + 1))
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
    monkeypatch.setattr(ledger, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(ledger, "print_recap", lambda limit=3: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, 'argv', ['support', '--bless', '--name', 'Ada', '--message', 'hi', '--amount', '0'])
    importlib.reload(support_cli)
    support_cli.main()
    out = capsys.readouterr().out
    assert 'Failed to record blessing' in out
    assert calls["snap"] >= 2 and calls["recap"] == 1
