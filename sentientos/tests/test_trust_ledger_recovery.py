from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.trust_ledger import FederationTrustLedger

pytestmark = pytest.mark.no_legacy_skip


@pytest.fixture
def ledger_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    return tmp_path


def _new_ledger() -> FederationTrustLedger:
    return FederationTrustLedger()


def test_restart_reload_from_state(ledger_env: Path) -> None:
    ledger = _new_ledger()
    ledger.record_probe("peer-a", status="fail", actor="test", reason="x")
    restarted = _new_ledger()
    snap = restarted.get_peer_trust("peer-a")
    assert snap.divergence_events == 1
    status = restarted.recovery_status()
    assert status["recovered_from_state"] is True


def test_replay_events_when_state_missing(ledger_env: Path) -> None:
    ledger = _new_ledger()
    ledger.record_replay_signal("peer-b", actor="test", event_hash="abc")
    state_file = ledger_env / "federation/trust_ledger_state.json"
    state_file.unlink()
    restarted = _new_ledger()
    snap = restarted.get_peer_trust("peer-b")
    assert snap.replay_events == 1
    assert restarted.recovery_status()["recovered_from_events"] is True


def test_malformed_state_fails_closed(ledger_env: Path) -> None:
    fed = ledger_env / "federation"
    fed.mkdir(parents=True, exist_ok=True)
    (fed / "trust_ledger_state.json").write_text("{not-json", encoding="utf-8")
    restarted = _new_ledger()
    assert restarted.get_peer_trust("peer-c").trust_state == "trusted"
    status = restarted.recovery_status()
    assert status["recovery_degraded"] is True
    assert "state_unreadable_or_invalid_json" in status["recovery_findings"]


def test_malformed_event_fails_closed(ledger_env: Path) -> None:
    fed = ledger_env / "federation"
    fed.mkdir(parents=True, exist_ok=True)
    (fed / "trust_ledger_events.jsonl").write_text("{bad}\n", encoding="utf-8")
    restarted = _new_ledger()
    status = restarted.recovery_status()
    assert status["recovery_degraded"] is True
    assert any(item.startswith("event_invalid_json_line") for item in status["recovery_findings"])


def test_schema_mismatch_degrades_and_uses_events(ledger_env: Path) -> None:
    fed = ledger_env / "federation"
    fed.mkdir(parents=True, exist_ok=True)
    (fed / "trust_ledger_state.json").write_text(json.dumps({"schema_version": 9, "peer_states": []}), encoding="utf-8")
    event = {"event": "control_attempt", "peer_id": "peer-d", "allowed": False, "reason": "nope"}
    (fed / "trust_ledger_events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    restarted = _new_ledger()
    snap = restarted.get_peer_trust("peer-d")
    assert snap.control_denied_events == 1
    assert "state_schema_mismatch" in restarted.recovery_status()["recovery_findings"]


def test_atomic_write_keeps_valid_json(ledger_env: Path) -> None:
    ledger = _new_ledger()
    ledger.record_control_attempt("peer-e", allowed=False, reason="r", actor="test")
    payload = json.loads((ledger_env / "federation/trust_ledger_state.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1


def test_recovery_status_inspectable_genesis(ledger_env: Path) -> None:
    ledger = _new_ledger()
    status = ledger.recovery_status()
    assert status["schema_version"] == 1
    assert "recovery_findings" in status


def test_state_event_contradiction_detected(ledger_env: Path) -> None:
    fed = ledger_env / "federation"
    fed.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "peer_states": [{"peer_id": "peer-f", "probe_history": {}, "divergence_events": 0, "epoch_mismatch_events": 0, "digest_mismatch_events": 0, "quorum_success_events": 0, "quorum_failure_events": 0, "replay_events": 0, "control_denied_events": 0}],
    }
    (fed / "trust_ledger_state.json").write_text(json.dumps(state), encoding="utf-8")
    event = {"event": "control_attempt", "peer_id": "peer-f", "allowed": False, "reason": "r", "trust_state": "incompatible"}
    (fed / "trust_ledger_events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    restarted = _new_ledger()
    assert any(item.startswith("state_event_contradiction:peer-f") for item in restarted.recovery_status()["recovery_findings"])
