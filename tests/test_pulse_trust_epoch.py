from __future__ import annotations

import base64
import copy
import json
from datetime import datetime, timezone
import os
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from sentientos.daemons import pulse_bus, pulse_federation
from sentientos.pulse_trust_epoch import get_manager, reset_manager
from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor


def _signed(event: dict[str, object], key: SigningKey) -> dict[str, object]:
    payload = pulse_bus.apply_pulse_defaults(copy.deepcopy(event))
    payload.setdefault("priority", "info")
    signature = key.sign(pulse_bus._serialize_for_signature(payload)).signature
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    return payload


@pytest.fixture(autouse=True)
def trust_epoch_env(tmp_path, monkeypatch):
    root = tmp_path / "pulse_trust"
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(root))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(root / "epoch_state.json"))
    reset_manager()
    pulse_bus.reset()
    pulse_federation.reset()
    reset_runtime_governor()
    yield
    reset_manager()
    pulse_bus.reset()
    pulse_federation.reset()
    reset_runtime_governor()


def test_clean_epoch_transition_preserves_historical_validation(tmp_path, monkeypatch):
    manager = get_manager()
    state = manager.load_state()
    first = str(state["active_epoch_id"])

    key2 = SigningKey.generate()
    pub2 = tmp_path / "epoch2.pub"
    priv2 = tmp_path / "epoch2.key"
    pub2.write_bytes(key2.verify_key.encode())
    priv2.write_bytes(key2.encode())

    manager.transition_epoch(
        new_epoch_id="epoch-0002",
        verify_key_path=str(pub2),
        signing_key_path=str(priv2),
        actor="test",
        reason="scheduled_rotation",
        compromise_response_mode=False,
    )

    legacy_event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "remote",
        "event_type": "heartbeat",
        "payload": {"ok": True},
        "pulse_epoch_id": first,
    }
    legacy_signed = _signed(legacy_event, SigningKey(Path(os.environ["PULSE_SIGNING_KEY"]).read_bytes()))
    result = manager.verify_event_signature(
        legacy_signed,
        serialized_payload=pulse_bus._serialize_for_signature(legacy_signed),
        signature=str(legacy_signed["signature"]),
        actor="test",
    )
    assert result.signature_valid is True
    assert result.classification == "historical_closed_epoch"


def test_revoked_epoch_is_structurally_valid_but_untrusted(tmp_path):
    manager = get_manager()
    state = manager.load_state()
    active = str(state["active_epoch_id"])

    key = SigningKey(Path(os.environ["PULSE_SIGNING_KEY"]).read_bytes())
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "remote",
        "event_type": "heartbeat",
        "payload": {"ok": True},
        "pulse_epoch_id": active,
    }
    signed = _signed(event, key)
    manager.revoke_epoch(epoch_id=active, actor="test", reason="compromise")

    result = manager.verify_event_signature(
        signed,
        serialized_payload=pulse_bus._serialize_for_signature(signed),
        signature=str(signed["signature"]),
        actor="test",
    )
    assert result.signature_valid is True
    assert result.trusted is False
    assert result.classification == "revoked_epoch"


def test_federated_epoch_mismatch_rejected(tmp_path, monkeypatch):
    key_dir = tmp_path / "federation"
    key_dir.mkdir()
    peer_key = SigningKey.generate()
    (key_dir / "peer-alpha.pub").write_bytes(peer_key.verify_key.encode())
    monkeypatch.setenv("PULSE_FEDERATION_KEYS_DIR", str(key_dir))

    pulse_federation.configure(enabled=True, peers=["peer-alpha"])

    manager = get_manager()
    manager.transition_epoch(
        new_epoch_id="epoch-0002",
        verify_key_path=Path(os.environ["PULSE_VERIFY_KEY"]).as_posix(),
        signing_key_path=Path(os.environ["PULSE_SIGNING_KEY"]).as_posix(),
        actor="test",
        reason="rotate",
        compromise_response_mode=False,
    )

    remote = _signed(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "peer",
            "event_type": "heartbeat",
            "payload": {"ok": True},
            "pulse_epoch_id": "epoch-0001",
        },
        peer_key,
    )

    with pytest.raises(ValueError):
        pulse_federation.ingest_remote_event(remote, "peer-alpha")


def test_governor_restricts_during_compromise_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")

    get_manager().transition_epoch(
        new_epoch_id="epoch-0002",
        verify_key_path=Path(os.environ["PULSE_VERIFY_KEY"]).as_posix(),
        signing_key_path=Path(os.environ["PULSE_SIGNING_KEY"]).as_posix(),
        actor="test",
        reason="compromise_response",
        compromise_response_mode=True,
    )

    reset_runtime_governor()
    governor = get_runtime_governor()
    decision = governor.admit_action("federated_control", "peer-a", "corr", metadata={"subject": "peer-a:daemon", "scope": "federated"})
    assert decision.allowed is False
    assert decision.reason == "pulse_epoch_compromise_restricted"


def test_bounded_telemetry_counters(tmp_path):
    manager = get_manager()
    state = manager.load_state()
    path = Path(os.environ["PULSE_SIGNING_KEY"])
    key = SigningKey(path.read_bytes())
    for idx in range(90):
        event = _signed(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_daemon": "local",
                "event_type": "tick",
                "payload": {"n": idx},
                "pulse_epoch_id": str(state["active_epoch_id"]),
            },
            key,
        )
        manager.verify_event_signature(
            event,
            serialized_payload=pulse_bus._serialize_for_signature(event),
            signature=str(event["signature"]),
            actor="test",
        )
    reloaded = json.loads(Path(os.environ["PULSE_TRUST_EPOCH_STATE"]).read_text(encoding="utf-8"))
    counters = reloaded.get("decision_counters", {})
    assert isinstance(counters, dict)
    assert len(counters) <= 64
