import os
import sys
import importlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import support_cli
import support_log


def test_support_bless(monkeypatch, capsys):
    def fake_add(name, message, amount=""):
        return {"supporter": name, "message": message, "amount": amount}
    monkeypatch.setattr(support_log, 'add', fake_add)
    monkeypatch.setattr(sys, 'argv', ['support', '--bless', '--name', 'Ada', '--message', 'hi', '--amount', '0'])
    importlib.reload(support_cli)
    support_cli.main()
    out = capsys.readouterr().out
    assert 'sanctuary acknowledged' in out

def test_support_bless_fail(monkeypatch, capsys):
    def fake_add(name, message, amount=""):
        raise RuntimeError('fail')
    monkeypatch.setattr(support_log, 'add', fake_add)
    monkeypatch.setattr(sys, 'argv', ['support', '--bless', '--name', 'Ada', '--message', 'hi', '--amount', '0'])
    importlib.reload(support_cli)
    support_cli.main()
    out = capsys.readouterr().out
    assert 'Failed to record blessing' in out
