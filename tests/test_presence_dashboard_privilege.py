import sys
import os
import time


import sentientos.presence_dashboard as presence_dashboard
import sentientos.admin_utils as admin_utils


def test_presence_dashboard_banner(capsys, monkeypatch):
    monkeypatch.setattr(admin_utils, "is_admin", lambda: True)
    monkeypatch.setattr("presence_dashboard.get_presence", lambda url: [])
    monkeypatch.setattr(time, "sleep", lambda x: None)
    presence_dashboard.run_cli("http://example", once=True)
    out = capsys.readouterr().out
    assert "Sanctuary Privilege Status" in out
