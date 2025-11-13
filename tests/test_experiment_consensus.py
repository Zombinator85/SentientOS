from __future__ import annotations

import importlib
import json
import os
import sys

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import experiment_tracker as et


def _setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIMENTS_FILE", str(tmp_path / "exp.json"))
    monkeypatch.setenv("EXPERIMENT_AUDIT_FILE", str(tmp_path / "audit.jsonl"))
    importlib.reload(et)


def _load_experiments(tmp_path):
    return json.loads((tmp_path / "exp.json").read_text())


def test_non_consensus_behaves_normally(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    eid = et.propose_experiment(
        "desc",
        "conditions",
        "expected",
        proposer="node0",
        requires_consensus=False,
    )
    assert et.get_experiment(eid)["status"] == "pending"
    et.vote_experiment(eid, "node0", True)
    et.vote_experiment(eid, "node1", True)
    assert et.get_experiment(eid)["status"] == "active"


def test_consensus_path_requires_quorum(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    eid = et.propose_experiment(
        "risky",
        "conditions",
        "expected",
        proposer="node0",
        requires_consensus=True,
        quorum_k=2,
        quorum_n=3,
    )

    assert et.get_experiment(eid)["status"] == "pending"
    et.vote_experiment(eid, "node1", True)
    assert et.get_experiment(eid)["status"] == "pending"
    et.vote_experiment(eid, "node2", True)
    assert et.get_experiment(eid)["status"] == "active"


def test_consensus_downvote_rejects(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    eid = et.propose_experiment(
        "risky",
        "conditions",
        "expected",
        proposer="node0",
        requires_consensus=True,
        quorum_k=2,
    )

    et.vote_experiment(eid, "node1", True)
    et.vote_experiment(eid, "node2", False)
    assert et.get_experiment(eid)["status"] == "rejected"


def test_digest_mismatch_detected(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    eid = et.propose_experiment(
        "risky",
        "conditions",
        "expected",
        proposer="node0",
        requires_consensus=True,
        quorum_k=2,
    )

    data = _load_experiments(tmp_path)
    for exp in data:
        if exp["id"] == eid:
            exp["description"] = "tampered"
    (tmp_path / "exp.json").write_text(json.dumps(data, indent=2))

    et.vote_experiment(eid, "node1", True)
    assert et.get_experiment(eid)["status"] == "digest_mismatch"


def test_duplicate_vote_prevented(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    eid = et.propose_experiment(
        "risky",
        "conditions",
        "expected",
        proposer="node0",
        requires_consensus=True,
        quorum_k=2,
    )

    assert et.vote_experiment(eid, "node1", True) is True
    assert et.vote_experiment(eid, "node1", True) is False
    info = et.get_experiment(eid)
    assert sum(1 for v in info["votes"].values() if v == "up") == 1
