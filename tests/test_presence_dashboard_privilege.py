import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import presence_dashboard
import admin_utils


def test_presence_dashboard_banner(capsys, monkeypatch):
    monkeypatch.setattr(admin_utils, "is_admin", lambda: True)
    monkeypatch.setattr("presence_dashboard.get_presence", lambda url: [])
    monkeypatch.setattr(time, "sleep", lambda x: None)
    presence_dashboard.run_cli("http://example", once=True)
    out = capsys.readouterr().out
    assert "Sanctuary Privilege Status" in out
