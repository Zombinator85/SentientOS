"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import json
import workflow_review as wr


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_REVIEW_DIR", str(tmp_path))
    importlib.reload(wr)


def test_vote_auto_accept(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    import final_approval
    monkeypatch.setattr(final_approval, "request_approval", lambda d: True)
    wr.flag_for_review("demo", "a", "b", required_votes=2)
    wr.vote_review("demo", "alice", True)
    assert "demo" in wr.list_pending()
    wr.vote_review("demo", "bob", True)
    assert "demo" not in wr.list_pending()
    log = (tmp_path / "review_log.jsonl").read_text().splitlines()
    assert any(json.loads(l).get("action") == "auto_accept" for l in log)
