"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import os
import sys
import json
import importlib


import sentientos.workflow_library as wl
import sentientos.workflow_controller as wc
import sentientos.workflow_review as wr
import sentientos.self_reflection as sr


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "mem"))
    monkeypatch.setenv("WORKFLOW_REVIEW_DIR", str(tmp_path / "review"))
    monkeypatch.setenv("WORKFLOW_LIBRARY", str(tmp_path / "lib"))
    for mod in (wl, wc, wr, sr):
        importlib.reload(mod)
    import sentientos.notification as notification
    importlib.reload(notification)
    wl.LIB_DIR.mkdir(exist_ok=True)
    wr.REVIEW_DIR.mkdir(exist_ok=True)


def test_suggest_and_dashboard_cli(tmp_path, monkeypatch, capsys):
    setup_env(tmp_path, monkeypatch)
    tpl = wl.LIB_DIR / "reset_workspace.json"
    tpl.write_text(json.dumps({"name": "reset_workspace", "steps": []}))
    import sentientos.workflow_dashboard as wd
    importlib.reload(wd)
    wd.st = None
    wd.pd = None
    monkeypatch.setattr(sys, "argv", ["wd", "--list"])
    wd.run_dashboard()
    out = capsys.readouterr().out
    assert "reset_workspace" in out

    data = wl.suggest_workflow("reset workspace")
    assert data["name"].startswith("reset")


def test_auto_heal_review(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    tpl = wl.LIB_DIR / "fail.json"
    mod = wl.LIB_DIR / "failer.py"
    mod.write_text("""def act():
    raise RuntimeError('boom')
def undo():
    pass
""", encoding="utf-8")
    tpl.write_text(json.dumps({
        "name": "fail",
        "steps": [{"name": "bad", "action": "failer.act", "undo": "failer.undo"}]
    }))
    wl.load_template("fail")
    # Simulate failures
    for _ in range(3):
        wc.run_workflow("fail")
    mgr = sr.SelfHealingManager()
    mgr.run_cycle()
    pending = wr.list_pending()
    assert "fail" in pending
    info = wr.load_review("fail")
    assert info and "before" in info
    assert wr.revert_review("fail")
    assert "fail" not in wr.list_pending()


def test_record_feedback(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    import sentientos.workflow_dashboard as wd
    importlib.reload(wd)
    wd.record_feedback("demo", True)
    log = (tmp_path / "mem" / "events.jsonl").read_text()
    assert "workflow.feedback" in log

