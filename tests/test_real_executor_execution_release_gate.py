from __future__ import annotations

import json

import pytest
from pathlib import Path

pytestmark = pytest.mark.no_legacy_skip

from sentientos.real_executor_execution_release_gate import (
    INVARIANTS,
    RealExecutorExecutionReleaseGateResult,
    build_default_policy,
    evaluate_real_executor_execution_release_gate,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/real_executor_execution_release_gate")
READY = FIXTURE_ROOT / "ready_real_executor_execution_release_gate_candidate.json"
NOOP = FIXTURE_ROOT / "noop_real_executor_execution_release_gate_candidate.json"
MIXED = FIXTURE_ROOT / "mixed_real_executor_execution_release_gate_candidate.json"


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ready_execution_release_gate_is_deterministic_metadata_only() -> None:
    first = evaluate_real_executor_execution_release_gate(load(READY))
    second = evaluate_real_executor_execution_release_gate(load(READY))

    assert isinstance(first, RealExecutorExecutionReleaseGateResult)
    assert first.to_dict() == second.to_dict()
    assert first.status == "real_executor_execution_release_gate_ready"
    assert first.packet is not None
    assert first.packet.digest.startswith("sha256:")
    packet = first.packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert packet[key] is expected
    record = packet["records"][0]
    assert record["real_executor_execution_release_gate_decision"] == "real_executor_execution_release_gate_ready_for_later_real_executor_execution_activation_packet"
    assert record["real_executor_execution_release_packet_digest"] == load(READY)["real_executor_execution_release_packet"]["digest"]
    assert record["release_packet_confirmation_records"][0]["metadata_only"] is True
    assert record["release_gate_readiness_records"][0]["metadata_only"] is True
    assert record["execution_release_denial_records"][0]["permission_granted"] is False
    assert record["final_release_hold_point_records"][0]["executed"] is False
    assert record["emergency_stop_confirmation_records"][0]["metadata_only"] is True
    assert record["rollback_readiness_records"][0]["rollback_applied"] is False
    assert record["verification_readiness_records"][0]["metadata_only"] is True
    assert record["audit_readiness_records"][0]["metadata_only"] is True
    assert record["real_executor_enabled"] is False
    assert record["real_executor_run_enabled"] is False
    assert record["real_executor_execution_enabled"] is False
    assert record["lockfile_created"] is False
    assert record["live_commit_executed"] is False


def test_noop_and_mixed_statuses() -> None:
    noop = evaluate_real_executor_execution_release_gate(load(NOOP))
    mixed = evaluate_real_executor_execution_release_gate(load(MIXED))

    assert noop.status == "real_executor_execution_release_gate_noop"
    assert noop.packet is not None
    assert noop.packet.records[0].real_executor_execution_release_gate_decision == "real_executor_execution_release_gate_noop"
    assert mixed.status == "real_executor_execution_release_gate_ready_with_warnings"
    assert mixed.packet is not None
    assert mixed.packet.records[0].real_executor_execution_release_gate_decision == "real_executor_execution_release_gate_ready_with_warnings"
    assert mixed.report.findings[0].code == "mixed_scope_diagnostic"


def test_blocks_missing_mismatched_or_forbidden_evidence() -> None:
    missing = evaluate_real_executor_execution_release_gate({"real_executor_execution_release_gate_candidates": []})
    assert missing.status == "real_executor_execution_release_gate_blocked"
    assert missing.report.findings[0].code == "missing_real_executor_execution_release_packet"

    payload = load(READY)
    payload["real_executor_execution_release_gate_candidates"][0]["claimed_real_executor_execution_gate_digest"] = "sha256:wrong"
    mismatch = evaluate_real_executor_execution_release_gate(payload)
    assert mismatch.status == "real_executor_execution_release_gate_blocked"
    assert mismatch.report.findings[0].code == "real_executor_execution_gate_digest_mismatch"

    payload = load(READY)
    payload["real_executor_execution_release_gate_candidates"][0]["operator_scope_keys"] = ["different"]
    scope = evaluate_real_executor_execution_release_gate(payload)
    assert scope.status == "real_executor_execution_release_gate_blocked"
    assert scope.report.findings[0].code == "scope_mismatch"

    payload = load(READY)
    payload["real_executor_execution_release_gate_candidates"][0]["real_executor_execution_release_gate_claims"] = {"live_commit_executed": True}
    forbidden = evaluate_real_executor_execution_release_gate(payload)
    assert forbidden.status == "real_executor_execution_release_gate_blocked"
    assert forbidden.report.findings[0].code == "live_execution_claim"


def test_requires_non_noop_metadata_and_valid_policy() -> None:
    policy_result = validate_policy(build_default_policy())
    assert policy_result["status"] == "valid"

    payload = load(READY)
    del payload["real_executor_execution_release_gate_candidates"][0]["release_gate_readiness_metadata"]
    blocked = evaluate_real_executor_execution_release_gate(payload)
    assert blocked.status == "real_executor_execution_release_gate_blocked"
    assert blocked.report.findings[0].code == "missing_release_gate_readiness_metadata"

    invalid_policy = build_default_policy()
    object.__setattr__(invalid_policy, "metadata_only", False)
    invalid = validate_policy(invalid_policy)
    assert invalid["status"] == "invalid"
