import os
import sys
import importlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import treasury_federation as tf


def test_cli_invite(monkeypatch, capsys):
    def fake_invite(peer, email="", message="federation invite", **kw):
        return {"peer": peer, "email": email, "message": message}

    monkeypatch.setattr(tf, "invite", fake_invite)
    monkeypatch.setattr(sys, "argv", ["fed", "invite", "peer1", "--email", "a@example.com", "--message", "hi"])
    import federation_cli
    importlib.reload(federation_cli)
    federation_cli.main()
    out = capsys.readouterr().out
    assert "peer1" in out and "hi" in out
