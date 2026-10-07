import os
import sys
import importlib
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import experiment_tracker as et


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIMENTS_FILE", str(tmp_path / "exp.json"))
    monkeypatch.setenv("EXPERIMENT_AUDIT_FILE", str(tmp_path / "audit.jsonl"))
    importlib.reload(et)


def test_propose_vote_comment(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr(et, "require_admin_banner", lambda: None)
    monkeypatch.setattr(et, "require_lumos_approval", lambda: None)
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


def test_save_authorizes_before_creating_or_writing_data(tmp_path, monkeypatch):
    events = []

    class Parent:
        def mkdir(self, **kwargs):
            events.append("mkdir")

    class DataFile:
        parent = Parent()

        def write_text(self, *_args, **_kwargs):
            events.append("write")

    monkeypatch.setattr(et, "DATA_FILE", DataFile())
    monkeypatch.setattr(et, "require_admin_banner", lambda: events.append("admin"))
    monkeypatch.setattr(et, "require_lumos_approval", lambda: events.append("lumos"))

    et._save([])

    assert events == ["admin", "lumos", "mkdir", "write"]
