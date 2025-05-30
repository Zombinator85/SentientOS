import importlib
import json

import review_requests as rr


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_REQUESTS_FILE", str(tmp_path / "req.jsonl"))
    monkeypatch.setenv("SUGGESTION_AUDIT_FILE", str(tmp_path / "audit.jsonl"))
    importlib.reload(rr)


def test_creation_and_explain(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    sid = rr.log_policy_suggestion(
        "workflow",
        "demo",
        "increase timeout",
        "3 failures in 5 runs",
    )
    item = rr.get_request(sid)
    assert item and item["suggestion"].startswith("increase")
    assert "rationale" in item


def test_vote_promote(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    sid = rr.log_policy_suggestion("workflow", "demo", "do", "because")
    rr.vote_request(sid, "alice", True)
    info = rr.get_request(sid)
    assert info["status"] == "pending"
    rr.vote_request(sid, "bob", True)
    info = rr.get_request(sid)
    assert info["status"] == "approved"
    log = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert any(json.loads(l).get("action") == "auto_approve" for l in log)


def test_cli_explain(tmp_path, monkeypatch, capsys):
    setup_env(tmp_path, monkeypatch)
    sid = rr.log_policy_suggestion("workflow", "demo", "x", "why")
    import suggestion_cli as sc
    monkeypatch.setattr(
        sc.sys, "argv", ["sc", "explain", sid], raising=False
    )
    sc.main()
    out = capsys.readouterr().out
    assert "why" in out
