from __future__ import annotations

from sentientos.trust_ledger import get_trust_ledger, reset_trust_ledger


def test_deterministic_trust_state_derivation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    reset_trust_ledger()
    ledger = get_trust_ledger()

    ledger.record_governance_evaluation(
        "peer-a",
        {
            "digest_status": "incompatible",
            "epoch_status": "unexpected",
            "quorum_satisfied": False,
            "denial_cause": "digest_mismatch",
        },
        actor="test",
    )
    ledger.record_governance_evaluation(
        "peer-a",
        {
            "digest_status": "incompatible",
            "epoch_status": "unexpected",
            "quorum_satisfied": False,
            "denial_cause": "trust_epoch",
        },
        actor="test",
    )
    ledger.record_governance_evaluation(
        "peer-a",
        {
            "digest_status": "incompatible",
            "epoch_status": "unexpected",
            "quorum_satisfied": False,
            "denial_cause": "quorum_failure",
        },
        actor="test",
    )

    snapshot = ledger.get_peer_trust("peer-a")
    assert snapshot.trust_state == "incompatible"
    assert snapshot.reconciliation_needed is True
    assert snapshot.digest_mismatch_events >= 3
    assert snapshot.epoch_mismatch_events >= 3


def test_probe_schedule_bounded_under_pressure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_TRUST_PROBE_PLAN_LIMIT", "4")
    monkeypatch.setenv("SENTIENTOS_TRUST_PROBE_PLAN_WARN_LIMIT", "2")
    monkeypatch.setenv("SENTIENTOS_TRUST_PROBE_PLAN_STORM_LIMIT", "1")
    reset_trust_ledger()
    ledger = get_trust_ledger()

    for peer in ("a", "b", "c", "d"):
        ledger.record_probe(peer, status="ok", actor="test", reason="baseline")

    warn = ledger.build_probe_schedule(
        peer_ids=["a", "b", "c", "d"],
        pressure_composite=0.8,
        scheduling_window_open=True,
        storm_active=False,
    )
    assert warn["probe_slots"] == 2
    assert len(warn["pending_actions"]) == 2

    storm = ledger.build_probe_schedule(
        peer_ids=["a", "b", "c", "d"],
        pressure_composite=0.8,
        scheduling_window_open=True,
        storm_active=True,
    )
    assert storm["probe_slots"] == 1
    assert len(storm["pending_actions"]) == 1


def test_digest_epoch_mismatch_pushes_from_watched_to_degraded(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    reset_trust_ledger()
    ledger = get_trust_ledger()

    watched = ledger.record_governance_evaluation(
        "peer-z",
        {
            "digest_status": "incompatible",
            "epoch_status": "expected",
            "quorum_satisfied": True,
            "denial_cause": "none",
        },
        actor="test",
    )
    assert watched.trust_state in {"watched", "degraded"}

    ledger.record_replay_signal("peer-z", actor="test", event_hash="h1")
    degraded = ledger.get_peer_trust("peer-z")
    assert degraded.trust_state in {"degraded", "quarantined", "incompatible"}


def test_quarantine_behavior_from_denied_controls(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    reset_trust_ledger()
    ledger = get_trust_ledger()

    ledger.record_control_attempt("peer-q", allowed=False, reason="federated_digest_mismatch_blocked", actor="test")
    ledger.record_control_attempt("peer-q", allowed=False, reason="federated_quorum_not_satisfied", actor="test")
    ledger.record_probe("peer-q", status="fail", actor="test", reason="probe_fail")
    ledger.record_probe("peer-q", status="fail", actor="test", reason="probe_fail")
    ledger.record_probe("peer-q", status="fail", actor="test", reason="probe_fail")

    snapshot = ledger.get_peer_trust("peer-q")
    assert snapshot.trust_state in {"quarantined", "incompatible"}
    assert snapshot.control_denied_events >= 2


def test_artifacts_are_bounded_and_deterministic_rollup(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_TRUST_LEDGER_EVENT_LOG_LIMIT", "5")
    reset_trust_ledger()
    ledger = get_trust_ledger()

    for idx in range(12):
        ledger.record_probe("peer-bounded", status="warn", actor="test", reason=f"r{idx}")

    state_path = tmp_path / "governor" / "trust_ledger_state.json"
    event_path = tmp_path / "governor" / "trust_ledger_events.jsonl"
    assert state_path.exists()
    assert event_path.exists()
    lines = event_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) <= 5
