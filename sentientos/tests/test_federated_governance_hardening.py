from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.emit_contract_status import emit_contract_status
from sentientos.federated_governance import get_controller, reset_controller
from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor
from sentientos.trust_ledger import reset_trust_ledger

pytestmark = pytest.mark.no_legacy_skip


@pytest.fixture(autouse=True)
def _federation_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_QUORUM_HIGH", "2")
    monkeypatch.setenv("SENTIENTOS_ENFORCEMENT_PROFILE", "federation-enforce")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    reset_controller()
    reset_runtime_governor()
    reset_trust_ledger()


def _event(
    *,
    action: str,
    digest: dict[str, object],
    epoch_id: str = "legacy",
    event_type: str = "federated_observation",
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "pulse_epoch_id": epoch_id,
        "payload": {"action": action, "daemon": "integrity_daemon"},
        "governance_digest": digest,
    }


def test_digest_exact_match_is_deterministic() -> None:
    controller = get_controller()
    first = controller.local_governance_digest()
    second = controller.local_governance_digest()
    assert first == second


def test_high_impact_requires_quorum() -> None:
    controller = get_controller()
    controller.set_trusted_peers({"peer-a", "peer-b"})
    digest = controller.local_governance_digest().to_dict()

    first = controller.evaluate_peer_event(
        "peer-a", _event(action="restart_daemon", digest=digest, event_type="federated_control")
    )
    second = controller.evaluate_peer_event(
        "peer-b", _event(action="restart_daemon", digest=digest, event_type="federated_control")
    )

    assert first.denial_cause == "quorum_failure"
    assert second.denial_cause == "none"
    assert second.quorum_satisfied is True


def test_high_impact_incompatible_digest_denied() -> None:
    controller = get_controller()
    controller.set_trusted_peers({"peer-a"})
    digest = controller.local_governance_digest().to_dict()
    bad = dict(digest)
    bad["digest"] = "deadbeef"

    evaluation = controller.evaluate_peer_event(
        "peer-a", _event(action="restart_daemon", digest=bad, event_type="federated_control")
    )
    assert evaluation.denial_cause == "digest_mismatch"
    assert evaluation.compatibility_category in {"incompatible", "patch_drift"}


def test_epoch_mismatch_classification() -> None:
    controller = get_controller()
    controller.set_trusted_peers({"peer-a"})
    digest = controller.local_governance_digest().to_dict()
    event = _event(action="restart_daemon", digest=digest, epoch_id="unexpected-epoch", event_type="federated_control")
    evaluation = controller.evaluate_peer_event("peer-a", event)
    assert evaluation.epoch_status == "unexpected"
    assert evaluation.compatibility_category == "epoch_mismatch"
    assert evaluation.denial_cause == "trust_epoch"


def test_low_impact_allows_single_peer() -> None:
    controller = get_controller()
    controller.set_trusted_peers({"peer-a", "peer-b"})
    digest = controller.local_governance_digest().to_dict()
    evaluation = controller.evaluate_peer_event("peer-a", _event(action="advisory", digest=digest))
    assert evaluation.action_impact == "low_impact_advisory"
    assert evaluation.denial_cause == "none"
    assert evaluation.quorum_satisfied is True


def test_runtime_governor_blocks_locally_restricted_even_with_quorum() -> None:
    governor = get_runtime_governor()
    decision = governor.admit_action(
        "federated_control",
        "peer-a",
        "corr-1",
        metadata={
            "scope": "federated",
            "federated_governance": {
                "denial_cause": "none",
                "digest_status": "compatible",
                "compatibility_category": "locally_restricted",
                "epoch_status": "expected",
                "quorum_required": 2,
                "quorum_present": 2,
                "quorum_satisfied": True,
            },
        },
    )
    assert decision.allowed is False
    assert decision.reason == "federated_locally_restricted"


def test_contract_status_includes_digest_and_quorum_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "glow/federation").mkdir(parents=True, exist_ok=True)
    (repo / "glow/federation/governance_digest.json").write_text("{}", encoding="utf-8")
    (repo / "glow/federation/federation_quorum_policy.json").write_text("{}", encoding="utf-8")
    (repo / "glow/federation/peer_governance_digests.json").write_text("{}", encoding="utf-8")
    output = repo / "glow/contracts/contract_status.json"
    payload = emit_contract_status(output)
    domain_names = {str(item.get("domain_name")) for item in payload.get("contracts", []) if isinstance(item, dict)}
    assert "governance_digest_status" in domain_names
    assert "federation_quorum_policy" in domain_names
    assert "peer_governance_digests" in domain_names
    assert "protected_mutation_proof" in domain_names

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == 1
    protected = next(
        (item for item in loaded.get("contracts", []) if isinstance(item, dict) and item.get("domain_name") == "protected_mutation_proof"),
        None,
    )
    assert isinstance(protected, dict)
    assert protected["mode"] == "baseline-aware"
    assert protected["covered_scope"] == "protected_mutation_proof:v1:kernel_admission"
    assert (repo / "glow/contracts/protected_mutation_proof_status.json").exists()
