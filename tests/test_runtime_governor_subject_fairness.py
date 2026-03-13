from __future__ import annotations

from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor


def test_subject_metadata_priority(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_SUBJECT_STATE_CAP", "2")
    reset_runtime_governor()
    gov = get_runtime_governor()
    d = gov.admit_action("federated_control", "actor", "c1", metadata={"peer": "peer-a", "scope": "federated"})
    assert d.subject == "peer-a"


def test_subject_state_bounded(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_SUBJECT_STATE_CAP", "2")
    reset_runtime_governor()
    gov = get_runtime_governor()
    for idx in range(10):
        gov.admit_action("federated_control", "actor", f"c{idx}", metadata={"subject": f"s{idx}", "scope": "federated"})
    roll = gov.rollup()
    per = roll["subject_fairness"]["per_class"].get("federated_control", {})
    assert per.get("subject_count", 0) <= 2
