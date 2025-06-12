"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import importlib
import json

import reflex_manager as rm
import reflection_stream as rs
import workflow_controller as wc


def test_reflex_proposal_logging(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLECTION_DIR", str(tmp_path))
    importlib.reload(rs)
    importlib.reload(rm)
    mgr = rm.ReflexManager()
    mgr.propose_improvements({"usage": {"wf1": {"fail_rate": 0.6}}})
    logs = rs.recent_reflex_learn(1)
    assert logs and logs[0]["data"]["proposal"]["workflow"] == "wf1"


def test_workflow_agent_logging(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    importlib.reload(wc)
    wc.register_workflow("demo", [{"name": "s1", "action": lambda: None}])
    assert wc.run_workflow("demo", agent="botA")
    events = (tmp_path / "events.jsonl").read_text().splitlines()
    assert any('"agent": "botA"' in ev for ev in events)


def test_review_comment(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_REVIEW_DIR", str(tmp_path))
    import workflow_review as wr
    importlib.reload(wr)
    wr.flag_for_review("demo", "a", "b")
    wr.comment_review("demo", "alice", "looks good")
    log = (tmp_path / "review_log.jsonl").read_text().splitlines()
    assert log and json.loads(log[-1])["action"] == "comment"

