"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


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
