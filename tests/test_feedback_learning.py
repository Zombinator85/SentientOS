"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_learning_tuning(tmp_path, monkeypatch):
    monkeypatch.setenv("FEEDBACK_USER_LOG", str(tmp_path / "u.jsonl"))
    monkeypatch.setenv("REFLEX_TUNING_LOG", str(tmp_path / "t.jsonl"))
    import importlib, feedback
    importlib.reload(feedback)
    from feedback import FeedbackManager, FeedbackRule

    fm = FeedbackManager(learning=True)
    fm.register_action("noop", lambda r, u, v: None)
    rule = FeedbackRule(emotion="Fear", threshold=0.6, action="noop", name="calm")
    fm.add_rule(rule)
    for i in range(5):
        fm.log_user_feedback(str(i), rule, 1 if i < 4 else 0)
    assert rule.threshold < 0.6
    logs = (tmp_path / "t.jsonl").read_text().splitlines()
    assert logs and json.loads(logs[0])["rule"] == "calm"

