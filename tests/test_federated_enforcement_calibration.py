from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone

from nacl.signing import SigningKey

from sentientos.daemons import pulse_bus, pulse_federation
from sentientos.federated_enforcement_policy import resolve_policy
from sentientos.federated_governance import get_controller, reset_controller
from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor


def _sign_event(signing_key: SigningKey, event: dict) -> dict:
    payload = pulse_bus.apply_pulse_defaults(copy.deepcopy(event))
    payload.setdefault("priority", "critical")
    signature = signing_key.sign(pulse_bus._serialize_for_signature(payload)).signature
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    return payload


def test_policy_profile_selection(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "ci-advisory")
    policy = resolve_policy()
    assert policy.profile == "ci-advisory"
    assert policy.federated_quorum == "advisory"
    assert policy.governance_digest == "advisory"


def test_advisory_digest_and_quorum_are_non_blocking(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "glow/governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "ci-advisory")
    reset_controller()
    controller = get_controller()
    controller.set_trusted_peers({"peer-a", "peer-b"})
    local = controller.local_governance_digest().to_dict()

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "restart_request",
        "payload": {"action": "restart_daemon", "daemon_name": "x"},
        "governance_digest": {"digest": "bad", "components": local.get("components", {})},
    }
    evaluation = controller.evaluate_peer_event("peer-a", event)
    assert evaluation.denial_cause == "digest_mismatch_advisory"


def test_subject_fairness_advisory_does_not_hard_block(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "glow/governor"))
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "ci-advisory")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.9")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CONTENTION_LIMIT", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_STARVATION_STREAK_THRESHOLD", "1")
    reset_runtime_governor()
    governor = get_runtime_governor()
    d = governor.admit_action("federated_control", "peer-a", "corr-1", metadata={"scope": "federated"})
    assert d.reason in {"fairness_starvation_warning", "pressure_block", "pressure_warn", "allowed"}


def test_enforce_profile_blocks_untrusted_epoch(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "glow/governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "federation-enforce")
    key_dir = tmp_path / "keys"
    key_dir.mkdir(parents=True)
    monkeypatch.setenv("PULSE_FEDERATION_KEYS_DIR", str(key_dir))

    key = SigningKey.generate()
    (key_dir / "peer-a.pub").write_bytes(key.verify_key.encode())
    pulse_federation.reset()
    pulse_federation.configure(enabled=True, peers=["peer-a"])

    event = _sign_event(
        key,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_daemon": "remote",
            "event_type": "restart_request",
            "payload": {"action": "restart_daemon", "daemon_name": "alpha", "scope": "federated"},
            "pulse_epoch_id": "legacy",
        },
    )
    try:
        pulse_federation.ingest_remote_event(event, "peer-a")
        assert False, "expected enforce profile to reject"
    except ValueError:
        pass
