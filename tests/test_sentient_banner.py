import sys
import os
import sentientos.sentient_banner as sb
import sentientos.admin_utils as admin_utils
import sentientos.presence_ledger as pl


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
