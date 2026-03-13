from __future__ import annotations

from nacl.signing import SigningKey

from sentientos.pulse_trust_epoch import get_manager, reset_manager


def test_retired_epoch_rejected_without_replay_window(monkeypatch, tmp_path):
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust/epoch_state.json"))
    monkeypatch.setenv("SENTIENTOS_PULSE_RETIRED_REPLAY_SECONDS", "0")
    reset_manager()
    manager = get_manager()
    state = manager.load_state()
    active = str(state["active_epoch_id"])
    k2 = SigningKey.generate()
    pub = tmp_path / "k2.pub"
    priv = tmp_path / "k2.key"
    pub.write_bytes(k2.verify_key.encode())
    priv.write_bytes(k2.encode())
    manager.transition_epoch(new_epoch_id="epoch-0002", verify_key_path=str(pub), signing_key_path=str(priv), actor="t", reason="r")
    result = manager.classify_epoch({"pulse_epoch_id": active}, actor="test", peer_name="peer")
    assert result.classification == "retired_epoch"
    assert result.trusted is False
