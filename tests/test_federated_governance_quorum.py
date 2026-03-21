from __future__ import annotations

import base64
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from sentientos.daemons import pulse_bus, pulse_federation
from sentientos.federated_governance import get_controller, reset_controller
from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "glow/governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    monkeypatch.setenv("SENTIENTOS_FEDERATION_QUORUM_HIGH", "2")
    (tmp_path / "vow").mkdir(parents=True, exist_ok=True)
    (tmp_path / "vow/immutable_manifest.json").write_text('{"files":{},"manifest_sha256":"m"}\n', encoding="utf-8")
    (tmp_path / "vow/invariants.yaml").write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_IMMUTABLE_MANIFEST", str(tmp_path / "vow/immutable_manifest.json"))
    monkeypatch.setenv("SENTIENTOS_INVARIANTS_PATH", str(tmp_path / "vow/invariants.yaml"))
    key_dir = tmp_path / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PULSE_FEDERATION_KEYS_DIR", str(key_dir))
    pulse_bus.reset()
    pulse_federation.reset()
    reset_controller()
    reset_runtime_governor()
    yield
    pulse_bus.reset()
    pulse_federation.reset()
    reset_controller()
    reset_runtime_governor()


def _sign_event(signing_key: SigningKey, event: dict) -> dict:
    payload = pulse_bus.apply_pulse_defaults(copy.deepcopy(event))
    payload.setdefault("priority", "critical")
    signature = signing_key.sign(pulse_bus._serialize_for_signature(payload)).signature
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    return payload


def _base_event(local_digest: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "remote",
        "event_type": "coordination_update",
        "priority": "info",
        "payload": {"action": "synchronize", "scope": "federated"},
        "governance_digest": local_digest,
        "pulse_protocol": pulse_federation._local_protocol_identity(),
    }


def test_digest_compatibility_classification() -> None:
    controller = get_controller()
    controller.set_trusted_peers({"peer-a", "peer-b"})
    local = controller.local_governance_digest().to_dict()

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "restart_request",
        "payload": {"action": "restart_daemon", "daemon_name": "x"},
        "governance_digest": local,
    }
    ok = controller.evaluate_peer_event("peer-a", event)
    assert ok.digest_status == "compatible"

    bad = copy.deepcopy(event)
    bad["governance_digest"] = {"digest": "deadbeef", "components": {}}
    mismatch = controller.evaluate_peer_event("peer-b", bad)
    assert mismatch.digest_status == "incompatible"
    assert mismatch.denial_cause == "digest_mismatch"


def test_high_impact_quorum_requires_multiple_peers(tmp_path) -> None:
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    key_a = SigningKey.generate()
    key_b = SigningKey.generate()
    (key_dir / "peer-a.pub").write_bytes(key_a.verify_key.encode())
    (key_dir / "peer-b.pub").write_bytes(key_b.verify_key.encode())
    pulse_federation.configure(enabled=True, peers=["peer-a", "peer-b"])

    local_digest = get_controller().local_governance_digest().to_dict()
    base = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "remote",
        "event_type": "restart_request",
        "priority": "critical",
        "payload": {"action": "restart_daemon", "daemon_name": "alpha", "scope": "federated"},
        "governance_digest": local_digest,
    }

    first = _sign_event(key_a, base)
    with pytest.raises(ValueError):
        pulse_federation.ingest_remote_event(first, "peer-a")

    second = _sign_event(key_b, base)
    ingested = pulse_federation.ingest_remote_event(second, "peer-b")
    assert ingested["source_peer"] == "peer-b"


def test_deterministic_digest_stable_for_same_state() -> None:
    controller = get_controller()
    d1 = controller.local_governance_digest().digest
    d2 = controller.local_governance_digest().digest
    assert d1 == d2


def test_local_posture_overrides_valid_quorum(monkeypatch) -> None:
    controller = get_controller()
    controller.set_trusted_peers({"peer-a", "peer-b"})
    local = controller.local_governance_digest().to_dict()

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "restart_request",
        "payload": {"action": "restart_daemon", "daemon_name": "x"},
        "governance_digest": local,
    }
    controller.evaluate_peer_event("peer-a", event)
    controller.evaluate_peer_event("peer-b", event)

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CRITICAL_LIMIT", "1")
    reset_runtime_governor()
    governor = get_runtime_governor()
    critical = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "net",
        "event_type": "crit",
        "priority": "critical",
        "payload": {},
    }
    governor.observe_pulse_event(critical)
    governor.observe_pulse_event(critical)
    decision = governor.admit_action(
        "federated_control",
        "peer-a",
        "corr-1",
        metadata={"scope": "federated", "subject": "peer-a:x", "federated_governance": {
            "digest_status": "compatible",
            "digest_reasons": [],
            "epoch_status": "expected",
            "denial_cause": "none",
            "quorum_required": 2,
            "quorum_present": 2,
            "quorum_satisfied": True,
        }},
    )
    assert decision.allowed is False
    assert decision.reason == "critical_event_storm_detected"


def test_artifacts_include_digest_and_quorum_decision() -> None:
    controller = get_controller()
    controller.set_trusted_peers({"peer-a", "peer-b"})
    local = controller.local_governance_digest().to_dict()
    controller.evaluate_peer_event(
        "peer-a",
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "restart_request",
            "payload": {"action": "restart_daemon", "daemon_name": "x"},
            "governance_digest": local,
        },
    )
    root = Path(os.environ["SENTIENTOS_GOVERNOR_ROOT"])
    assert (root / "governance_digest.json").exists()
    assert (root / "peer_governance_digests.json").exists()
    lines = (root / "federation_quorum_decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert lines
    payload = json.loads(lines[-1])
    assert payload["quorum_required"] >= 1


def test_protocol_compatibility_classifications(tmp_path) -> None:
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    key = SigningKey.generate()
    (key_dir / "peer-a.pub").write_bytes(key.verify_key.encode())
    pulse_federation.configure(enabled=True, peers=["peer-a"])
    controller = get_controller()
    controller.set_trusted_peers({"peer-a"})
    local_digest = controller.local_governance_digest().to_dict()

    exact = _sign_event(key, _base_event(local_digest))
    pulse_federation.ingest_remote_event(exact, "peer-a")
    posture = json.loads((tmp_path / "glow/federation/pulse_protocol_posture.json").read_text(encoding="utf-8"))
    assert posture["peers"][0]["protocol_compatibility"] == "exact_protocol_match"

    patch = _base_event(local_digest)
    patch_claim = dict(patch["pulse_protocol"])
    patch_claim["protocol_version"] = "2.1.7"
    patch_claim["protocol_fingerprint"] = "patch-drift"
    patch["pulse_protocol"] = patch_claim
    pulse_federation.ingest_remote_event(_sign_event(key, patch), "peer-a")
    posture = json.loads((tmp_path / "glow/federation/pulse_protocol_posture.json").read_text(encoding="utf-8"))
    assert posture["peers"][0]["protocol_compatibility"] == "patch_compatible"

    incompatible = _base_event(local_digest)
    incompatible_claim = dict(incompatible["pulse_protocol"])
    incompatible_claim["protocol_version"] = "3.0.0"
    incompatible_claim["protocol_fingerprint"] = "v3"
    incompatible["pulse_protocol"] = incompatible_claim
    with pytest.raises(ValueError, match="protocol incompatible"):
        pulse_federation.ingest_remote_event(_sign_event(key, incompatible), "peer-a")


def test_deprecated_protocol_accepted_when_enabled() -> None:
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    key = SigningKey.generate()
    (key_dir / "peer-a.pub").write_bytes(key.verify_key.encode())
    pulse_federation.configure(enabled=True, peers=["peer-a"])
    controller = get_controller()
    controller.set_trusted_peers({"peer-a"})
    local_digest = controller.local_governance_digest().to_dict()
    event = _base_event(local_digest)
    claim = dict(event["pulse_protocol"])
    claim["protocol_version"] = "1.9.9"
    claim["protocol_fingerprint"] = "deprecated"
    event["pulse_protocol"] = claim

    ingested = pulse_federation.ingest_remote_event(_sign_event(key, event), "peer-a")
    assert ingested["source_peer"] == "peer-a"


def test_replay_window_harmonization_drops_historical_signed(tmp_path) -> None:
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    key = SigningKey.generate()
    (key_dir / "peer-a.pub").write_bytes(key.verify_key.encode())
    pulse_federation.configure(enabled=True, peers=["peer-a"])
    controller = get_controller()
    controller.set_trusted_peers({"peer-a"})
    local_digest = controller.local_governance_digest().to_dict()

    stale = _base_event(local_digest)
    stale["timestamp"] = "2020-01-01T00:00:00+00:00"
    out = pulse_federation.ingest_remote_event(_sign_event(key, stale), "peer-a")
    assert out["timestamp"] == "2020-01-01T00:00:00+00:00"
    lines = (tmp_path / "glow/federation/ingest_classifications.jsonl").read_text(encoding="utf-8").splitlines()
    assert any("dropped_historical_signed" in line for line in lines)


def test_equivocation_detects_conflicting_correlation_hashes(tmp_path) -> None:
    key_dir = Path(os.environ["PULSE_FEDERATION_KEYS_DIR"])
    key = SigningKey.generate()
    (key_dir / "peer-a.pub").write_bytes(key.verify_key.encode())
    pulse_federation.configure(enabled=True, peers=["peer-a"])
    controller = get_controller()
    controller.set_trusted_peers({"peer-a"})
    local_digest = controller.local_governance_digest().to_dict()

    first = _base_event(local_digest)
    first["correlation_id"] = "same-correlation"
    first["payload"] = {"action": "synchronize", "nonce": "a"}
    pulse_federation.ingest_remote_event(_sign_event(key, first), "peer-a")

    second = _base_event(local_digest)
    second["correlation_id"] = "same-correlation"
    second["payload"] = {"action": "synchronize", "nonce": "b"}
    with pytest.raises(ValueError, match="equivocation denied"):
        pulse_federation.ingest_remote_event(_sign_event(key, second), "peer-a")
    summary = json.loads((tmp_path / "glow/federation/equivocation_summary.json").read_text(encoding="utf-8"))
    assert summary["peer_summaries"][0]["latest_classification"] == "confirmed_equivocation"
