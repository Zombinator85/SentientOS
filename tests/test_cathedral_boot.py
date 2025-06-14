"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
import json
from pathlib import Path
import importlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import test_cathedral_boot as boot


def test_run_checks_success(monkeypatch):
    monkeypatch.setattr(boot, "check_sse", lambda: True)
    monkeypatch.setattr(boot, "check_ingest", lambda: True)
    monkeypatch.setattr(boot, "check_status", lambda: True)
    monkeypatch.setattr(boot, "check_log", lambda: True)
    monkeypatch.setattr(boot, "check_gui", lambda: True)
    res = boot.run_checks()
    assert all(res.values()) and len(res) == 5


def test_main_writes_summary(tmp_path, monkeypatch, capsys):
    status = tmp_path / "status.json"
    monkeypatch.setattr(boot, "STATUS_PATH", status)
    monkeypatch.setattr(
        boot,
        "run_checks",
        lambda: {"sse": True, "ingest": False, "status": True, "log": True, "gui": True},
    )
    ret = boot.main([])
    out = capsys.readouterr().out
    assert "failed" in out and "ingest" in out
    assert status.exists()
    data = json.loads(status.read_text())
    assert not data["ok"] and not data["results"]["ingest"]
    assert ret == 1
