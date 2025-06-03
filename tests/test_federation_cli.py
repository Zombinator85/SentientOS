import os
import sys
import importlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest

import treasury_federation as tf
import sentient_banner as sb


def test_cli_invite(monkeypatch, capsys):
    def fake_invite(peer, email="", message="federation invite", blessing="", supporter="", affirm=False):
        return {
            "peer": peer,
            "email": email,
            "message": message,
            "blessing": blessing,
            "supporter": supporter,
            "affirm": affirm,
        }

    calls = {"snap": 0, "recap": 0}

    def fake_snap():
        calls["snap"] += 1

    def fake_recap(limit: int = 3):
        calls["recap"] += 1

    monkeypatch.setattr(tf, "invite", fake_invite)
    monkeypatch.setattr(sb, "print_snapshot_banner", fake_snap)
    monkeypatch.setattr(sb, "print_closing_recap", fake_recap)
    monkeypatch.setattr(sys, "argv", [
        "fed",
        "invite",
        "peer1",
        "--email",
        "a@example.com",
        "--message",
        "hi",
        "--blessing",
        "hello",
        "--name",
        "Ada",
        "--affirm",
    ])
    import federation_cli
    importlib.reload(federation_cli)
    federation_cli.main()
    out = capsys.readouterr().out
    assert "peer1" in out and "hi" in out and "hello" in out
    assert calls["snap"] >= 2 and calls["recap"] == 1


def test_cli_ledger_summary(monkeypatch):
    calls = {"snap": 0, "recap": 0}

    monkeypatch.setattr(sb, "print_snapshot_banner", lambda: calls.__setitem__("snap", calls["snap"] + 1))
    monkeypatch.setattr(sb, "print_closing_recap", lambda: calls.__setitem__("recap", calls["recap"] + 1))
    monkeypatch.setattr(sys, "argv", ["fed", "--ledger-summary"])
    import federation_cli
    importlib.reload(federation_cli)
    federation_cli.main()
    assert calls["snap"] >= 2 and calls["recap"] == 1
