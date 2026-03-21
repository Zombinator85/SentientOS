from __future__ import annotations

import base64
import copy
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest
from nacl.signing import SigningKey

from sentientos.daemons import pulse_bus, pulse_federation
from sentientos.pulse_trust_epoch import reset_manager


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    pulse_bus.reset()
    pulse_federation.reset()
    reset_manager()
    trust_root = tmp_path / "pulse_trust"
    trust_root.mkdir(parents=True, exist_ok=True)
    pulse_key_dir = tmp_path / "pulse_keys"
    pulse_key_dir.mkdir(parents=True, exist_ok=True)
    pulse_signing = SigningKey.generate()
    (pulse_key_dir / "ed25519_private.key").write_bytes(pulse_signing.encode())
    (pulse_key_dir / "ed25519_public.key").write_bytes(pulse_signing.verify_key.encode())
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(trust_root))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(trust_root / "epoch_state.json"))
    monkeypatch.setenv("PULSE_SIGNING_KEY", str(pulse_key_dir / "ed25519_private.key"))
    monkeypatch.setenv("PULSE_VERIFY_KEY", str(pulse_key_dir / "ed25519_public.key"))
    reset_manager()
    key_dir = tmp_path / "federation_keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PULSE_FEDERATION_KEYS_DIR", str(key_dir))
    yield
    pulse_bus.reset()
    pulse_federation.reset()


def _sign_event(signing_key: SigningKey, event: dict) -> dict:
    payload = pulse_bus.apply_pulse_defaults(copy.deepcopy(event))
    payload.setdefault("priority", "info")
    signature = signing_key.sign(pulse_bus._serialize_for_signature(payload)).signature
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    return payload


def test_local_publish_forwarded_with_signature(monkeypatch):
    captured: List[tuple[str, dict]] = []

    def fake_post(url: str, *, json: dict, timeout: int) -> None:  # noqa: A002 - matching signature
        captured.append((url, json))

    monkeypatch.setattr(pulse_federation, "_http_post", fake_post)

    pulse_federation.configure(enabled=True, peers=["peer-alpha"])

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "network",
        "event_type": "status",
        "payload": {"ok": True},
    }
    published = pulse_bus.publish(event)

    assert published["source_peer"] == "local"
    assert captured, "Publishing should forward the event to peers"
    url, payload = captured[0]
    assert url == "http://peer-alpha/pulse/federation"
    assert payload["signature"]
    assert payload["source_peer"] == "local"
    assert pulse_bus.verify(payload) is True


def test_tampered_signature_rejected():
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    signing_key = SigningKey.generate()
    (key_dir / "peer-alpha.pub").write_bytes(signing_key.verify_key.encode())

    pulse_federation.configure(enabled=True, peers=["peer-alpha"])

    base_event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "remote",
        "event_type": "metric",
        "payload": {"value": 1},
    }
    signed = _sign_event(signing_key, base_event)
    ingested = pulse_federation.ingest_remote_event(copy.deepcopy(signed), "peer-alpha")
    assert ingested["source_peer"] == "peer-alpha"
    assert pulse_bus.verify(ingested) is True

    tampered = copy.deepcopy(signed)
    tampered["payload"]["value"] = 999

    with pytest.raises(ValueError):
        pulse_federation.ingest_remote_event(tampered, "peer-alpha")
    ingested_metrics = [
        evt for evt in pulse_bus.pending_events() if str(evt.get("event_type")) == "metric"
    ]
    assert len(ingested_metrics) == 1
    classifications = Path(os.environ["SENTIENTOS_FEDERATION_ROOT"]) / "ingest_classifications.jsonl"
    assert classifications.exists()
    rows = classifications.read_text(encoding="utf-8")
    assert '"classification": "accepted_verified"' in rows
    assert '"classification": "rejected_signature"' in rows


def test_remote_replay_ingests_events(monkeypatch):
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    signing_key = SigningKey.generate()
    (key_dir / "peer-alpha.pub").write_bytes(signing_key.verify_key.encode())

    pulse_federation.configure(enabled=True, peers=["peer-alpha"])

    replay_event = _sign_event(
        signing_key,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "remote",
            "event_type": "heartbeat",
            "payload": {"note": "synced"},
            "correlation_id": "corr-peer-alpha-sync",
        },
    )

    def fake_get(url: str, *, params: dict, timeout: int):  # noqa: ANN001 - params shape defined by caller
        assert params.get("minutes") == 15
        return [copy.deepcopy(replay_event)]

    monkeypatch.setattr(pulse_federation, "_http_get", fake_get)

    ingested = pulse_federation.request_recent_events(15)
    assert ingested and ingested[0]["source_peer"] == "peer-alpha"
    events = pulse_bus.pending_events()
    assert events and events[0]["event_type"] == "heartbeat"
    assert events[0]["source_peer"] == "peer-alpha"
    assert events[0]["correlation_id"] == "corr-peer-alpha-sync"
    assert pulse_bus.verify(events[0]) is True


def test_remote_events_do_not_echo(monkeypatch):
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    signing_key = SigningKey.generate()
    (key_dir / "peer-alpha.pub").write_bytes(signing_key.verify_key.encode())

    pulse_federation.configure(enabled=True, peers=["peer-alpha"])

    captured: List[tuple[str, dict]] = []

    def fake_post(url: str, *, json: dict, timeout: int) -> None:  # noqa: A002
        captured.append((url, json))

    monkeypatch.setattr(pulse_federation, "_http_post", fake_post)

    remote_event = _sign_event(
        signing_key,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "remote",
            "event_type": "alert",
            "payload": {"detail": "peer"},
        },
    )

    ingested = pulse_federation.ingest_remote_event(remote_event, "peer-alpha")
    assert ingested["source_peer"] == "peer-alpha"
    assert captured == []
    pending = pulse_bus.pending_events()
    assert pending and pending[0]["event_type"] == "alert"
    assert pending[0]["source_peer"] == "peer-alpha"


def test_duplicate_remote_events_suppressed(monkeypatch):
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    signing_key = SigningKey.generate()
    (key_dir / "peer-alpha.pub").write_bytes(signing_key.verify_key.encode())

    pulse_federation.configure(enabled=True, peers=["peer-alpha"])

    replay_event = _sign_event(
        signing_key,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "remote",
            "event_type": "heartbeat",
            "payload": {"note": "dup"},
        },
    )

    def fake_get(url: str, *, params: dict, timeout: int):  # noqa: ANN001
        return [copy.deepcopy(replay_event), copy.deepcopy(replay_event)]

    monkeypatch.setattr(pulse_federation, "_http_get", fake_get)

    ingested = pulse_federation.request_recent_events(15)
    assert len(ingested) == 2
    pending = pulse_bus.pending_events()
    assert len(pending) == 1
    assert pending[0]["payload"]["note"] == "dup"
    classifications = Path(os.environ["SENTIENTOS_FEDERATION_ROOT"]) / "ingest_classifications.jsonl"
    rows = classifications.read_text(encoding="utf-8")
    assert '"classification": "suppressed_replay"' in rows


def test_distinct_remote_events_are_not_suppressed(monkeypatch):
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    signing_key = SigningKey.generate()
    (key_dir / "peer-alpha.pub").write_bytes(signing_key.verify_key.encode())

    pulse_federation.configure(enabled=True, peers=["peer-alpha"])

    first = _sign_event(
        signing_key,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "remote",
            "event_type": "heartbeat",
            "payload": {"note": "a"},
        },
    )
    second = _sign_event(
        signing_key,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "remote",
            "event_type": "heartbeat",
            "payload": {"note": "b"},
        },
    )

    def fake_get(url: str, *, params: dict, timeout: int):  # noqa: ANN001
        return [copy.deepcopy(first), copy.deepcopy(second)]

    monkeypatch.setattr(pulse_federation, "_http_get", fake_get)
    pulse_federation.request_recent_events(15)

    pending = pulse_bus.pending_events()
    notes = sorted(str(evt["payload"]["note"]) for evt in pending)
    assert notes == ["a", "b"]
