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


def test_chained_and_provenance(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    sid = rr.log_policy_suggestion("workflow", "demo", "x", "why", agent="alice")
    import final_approval
    monkeypatch.setattr(final_approval, "request_approval", lambda d: True)
    rr.implement_request(sid)
    rr.comment_request(sid, "bob", "fail again")
    chain = rr.get_chain(sid)
    assert len(chain) == 2
    prov = rr.get_provenance(sid)
    acts = [p["action"] for p in prov]
    assert "create" in acts and "implement" in acts


def test_implement_requires_approval(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    sid = rr.log_policy_suggestion("workflow", "demo", "x", "why")
    import final_approval
    monkeypatch.setattr(final_approval, "request_approval", lambda d: False)
    assert not rr.implement_request(sid)
    info = rr.get_request(sid)
    assert info["status"] == "pending"
    monkeypatch.setattr(final_approval, "request_approval", lambda d: True)
    assert rr.implement_request(sid)
    info = rr.get_request(sid)
    assert info["status"] == "implemented"


def test_rationale_refinement(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    sid = rr.log_policy_suggestion("workflow", "demo", "x", "why")
    rr.vote_request(sid, "alice", True)
    rr.vote_request(sid, "bob", False)
    rr.comment_request(sid, "carol", "needs more work")
    info = rr.get_request(sid)
    assert info["refined"]
    assert info["rationale_log"]
