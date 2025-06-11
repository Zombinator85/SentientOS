import os
import sys
import importlib
import json


import sentientos.experiment_tracker as et


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIMENTS_FILE", str(tmp_path / "exp.json"))
    monkeypatch.setenv("EXPERIMENT_AUDIT_FILE", str(tmp_path / "audit.jsonl"))
    importlib.reload(et)


def test_propose_vote_comment(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    eid = et.propose_experiment("calming", "haptic agitation", "lower stress", proposer="alice")
    assert et.get_experiment(eid)
    et.vote_experiment(eid, "alice", True)
    et.vote_experiment(eid, "bob", True)
    info = et.get_experiment(eid)
    assert info["status"] == "active"
    et.comment_experiment(eid, "carol", "works")
    info = et.get_experiment(eid)
    assert info["comments"]
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert any(json.loads(l)["action"] == "propose" for l in lines)
