from __future__ import annotations

import base64
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from nacl.signing import SigningKey

from sentientos.daemons import pulse_bus, pulse_federation
from sentientos.federated_enforcement_policy import write_policy_snapshot
from sentientos.federated_enforcement_policy import resolve_policy
from sentientos.federated_governance import get_controller, reset_controller
from sentientos.repair_outcome import verify_repair_outcome
from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor
from scripts.emit_contract_status import emit_contract_status


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


def test_policy_resolution_is_deterministic_with_file_and_env_override(monkeypatch, tmp_path):
    override = tmp_path / "policy.json"
    override.write_text(
        json.dumps(
            {
                "postures": {
                    "federated_quorum": "shadow",
                    "governance_digest": "shadow",
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "federation-enforce")
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_POLICY_PATH", str(override))
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_GOVERNANCE_DIGEST", "advisory")
    first = resolve_policy().to_dict()
    second = resolve_policy().to_dict()
    assert first == second
    assert first["postures"]["federated_quorum"] == "shadow"
    assert first["postures"]["governance_digest"] == "advisory"


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
    assert evaluation.calibration_action == "warn"


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


def test_shadow_profile_observes_digest_without_blocking(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "glow/governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "local-dev-relaxed")
    reset_controller()
    controller = get_controller()
    controller.set_trusted_peers({"peer-a"})
    local = controller.local_governance_digest().to_dict()
    evaluation = controller.evaluate_peer_event(
        "peer-a",
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "restart_request",
            "payload": {"action": "restart_daemon", "daemon_name": "x"},
            "governance_digest": {"digest": "bad", "components": local.get("components", {})},
        },
    )
    assert evaluation.denial_cause == "digest_mismatch_observed"
    assert evaluation.calibration_action == "observe"


def test_enforce_profile_denies_quorum_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "glow/governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "glow/federation"))
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "federation-enforce")
    monkeypatch.setenv("SENTIENTOS_FEDERATION_QUORUM_HIGH", "2")
    reset_controller()
    controller = get_controller()
    controller.set_trusted_peers({"peer-a", "peer-b"})
    local = controller.local_governance_digest().to_dict()
    evaluation = controller.evaluate_peer_event(
        "peer-a",
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "restart_request",
            "payload": {"action": "restart_daemon", "daemon_name": "x"},
            "governance_digest": {"digest": local["digest"], "components": local.get("components", {})},
        },
    )
    assert evaluation.denial_cause == "quorum_failure"
    assert evaluation.calibration_action == "deny"


def test_repair_verification_closure_varies_by_posture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "local-dev-relaxed")
    shadow_outcome = verify_repair_outcome(anomaly_kind="checksum", pre_details={"symptom_cleared": False})
    assert shadow_outcome.closure_action == "observe"
    assert shadow_outcome.closure_allowed is True

    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "ci-advisory")
    advisory_outcome = verify_repair_outcome(anomaly_kind="checksum", pre_details={"symptom_cleared": False})
    assert advisory_outcome.closure_action == "warn"
    assert advisory_outcome.closure_allowed is True

    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "federation-enforce")
    enforce_outcome = verify_repair_outcome(anomaly_kind="checksum", pre_details={"symptom_cleared": False})
    assert enforce_outcome.closure_action == "deny"
    assert enforce_outcome.closure_allowed is False


def test_contract_status_includes_calibrated_policy_profile(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "ci-advisory")
    write_policy_snapshot(tmp_path / "glow/contracts/federated_enforcement_policy.json")
    payload = emit_contract_status(tmp_path / "glow/contracts/contract_status.json")
    calibrated = next(item for item in payload["contracts"] if item["domain_name"] == "federated_enforcement_calibration")
    assert payload["federated_enforcement_policy"]["profile"] == "ci-advisory"
    assert calibrated["profile"] == "ci-advisory"
    assert "governance_digest" in calibrated["postures"]
