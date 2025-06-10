"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import os
import sys
import importlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import reflection_stream as rs
import trust_engine as te


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLECTION_DIR", str(tmp_path / "reflect"))
    monkeypatch.setenv("TRUST_DIR", str(tmp_path / "trust"))
    importlib.reload(rs)
    importlib.reload(te)


def test_timeline_and_filter(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    rs.log_event("core", "heal", "x", "heal")
    te.log_event("policy_change", "policy:x", "update", "policy")

    import reflection_dashboard as rd
    importlib.reload(rd)

    events = rd.load_timeline(limit=5)
    assert len(events) == 2
    filtered = rd.filter_events(events, event_type="heal")
    assert len(filtered) == 1 and filtered[0]["type"] == "heal"
    assert "explain" in filtered[0]["explain_cmd"]


def test_cli_fallback(tmp_path, monkeypatch, capsys):
    setup_env(tmp_path, monkeypatch)
    rs.log_event("core", "heal", "x", "heal")

    import reflection_dashboard as rd
    importlib.reload(rd)

    monkeypatch.setattr(sys, "argv", ["rd", "--last", "1"])
    rd.run_dashboard()
    out = capsys.readouterr().out
    assert "heal" in out
