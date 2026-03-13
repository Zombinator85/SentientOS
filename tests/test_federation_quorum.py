from __future__ import annotations

from datetime import datetime, timezone

from sentientos.federated_governance import get_controller, reset_controller


def test_quorum_artifacts_written(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "g"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "f"))
    reset_controller()
    c = get_controller()
    c.set_trusted_peers({"p1", "p2"})
    e = {"timestamp": datetime.now(timezone.utc).isoformat(), "event_type": "restart_request", "payload": {"action": "restart_daemon"}, "governance_digest": c.local_governance_digest().to_dict()}
    c.evaluate_peer_event("p1", e)
    assert (tmp_path / "f/quorum_status.json").exists()
    assert (tmp_path / "f/quorum_decisions.jsonl").exists()
