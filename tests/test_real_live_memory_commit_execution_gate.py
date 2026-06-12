from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.real_live_memory_commit_execution_gate import (
    INVARIANTS,
    RealLiveMemoryCommitExecutionGateResult,
    build_default_policy,
    evaluate_real_live_memory_commit_execution_gate,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/real_live_memory_commit_execution_gate")
READY = FIXTURE_ROOT / "ready_real_live_memory_commit_execution_gate_candidate.json"
NOOP = FIXTURE_ROOT / "noop_real_live_memory_commit_execution_gate_candidate.json"
MIXED = FIXTURE_ROOT / "mixed_real_live_memory_commit_execution_gate_candidate.json"


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ready_execution_live_memory_commit_execution_gate_is_deterministic_metadata_only() -> None:
    first = evaluate_real_live_memory_commit_execution_gate(load(READY))
    second = evaluate_real_live_memory_commit_execution_gate(load(READY))

    assert isinstance(first, RealLiveMemoryCommitExecutionGateResult)
    assert first.to_dict() == second.to_dict()
    assert first.status == "real_live_memory_commit_execution_gate_ready"
    assert first.packet is not None
    assert first.packet.digest.startswith("sha256:")
    packet = first.packet.to_dict()
    assert packet["metadata_only"] is True
    assert packet["default_deny"] is True
    assert packet["not_permission_to_execute"] is True
    record = packet["records"][0]
    for key, expected in INVARIANTS.items():
        assert record[key] is expected
    upstream_packet = load(READY)["real_executor_execution_commit_window_packet"]
    upstream_record = upstream_packet["records"][0]
    assert record["real_live_memory_commit_execution_gate_decision"] == "real_live_memory_commit_execution_gate_ready_for_later_live_execution_packet_or_adapter_admission"
    assert record["real_executor_execution_commit_window_packet_digest"] == upstream_packet["digest"]
    assert record["real_executor_execution_commit_window_packet_decision"] == upstream_record["real_executor_execution_commit_window_packet_decision"]
    assert record["real_executor_execution_commit_plan_packet_digest"] == upstream_record["real_executor_execution_commit_plan_packet_digest"]
    assert record["carried_evidence"]["real_executor_execution_invocation_gate"]["digest"] == upstream_record["carried_evidence"]["real_executor_execution_invocation_gate"]["digest"]
    assert record["live_memory_commit_execution_gate_readiness_records"][0]["metadata_only"] is True
    assert record["lock_lease_gate_confirmation_records"][0]["metadata_only"] is True
    assert record["live_commit_execution_denial_records"][0]["permission_granted"] is False
    assert record["adapter_admission_deferral_records"][0]["executed"] is False
    assert record["emergency_stop_confirmation_records"][0]["metadata_only"] is True
    assert record["rollback_readiness_records"][0]["rollback_applied"] is False
    assert record["verification_readiness_records"][0]["metadata_only"] is True
    assert record["audit_readiness_records"][0]["metadata_only"] is True


def test_noop_and_mixed_statuses() -> None:
    noop = evaluate_real_live_memory_commit_execution_gate(load(NOOP))
    mixed = evaluate_real_live_memory_commit_execution_gate(load(MIXED))

    assert noop.status == "real_live_memory_commit_execution_gate_noop"
    assert noop.packet is not None
    assert noop.packet.records[0].real_live_memory_commit_execution_gate_decision == "real_live_memory_commit_execution_gate_noop"
    assert mixed.status == "real_live_memory_commit_execution_gate_ready_with_warnings"
    assert mixed.packet is not None
    assert mixed.packet.records[0].real_live_memory_commit_execution_gate_decision == "real_live_memory_commit_execution_gate_ready_with_warnings"
    assert mixed.report.findings[0].code == "mixed_scope_diagnostic"


def test_blocks_missing_mismatched_or_forbidden_evidence() -> None:
    missing = evaluate_real_live_memory_commit_execution_gate({"real_live_memory_commit_execution_gate_candidates": []})
    assert missing.status == "real_live_memory_commit_execution_gate_blocked"
    assert missing.report.findings[0].code == "missing_real_executor_execution_commit_window_packet"

    payload = load(READY)
    payload["real_live_memory_commit_execution_gate_candidates"][0]["claimed_real_executor_execution_commit_window_packet_digest"] = "sha256:wrong"
    mismatch = evaluate_real_live_memory_commit_execution_gate(payload)
    assert mismatch.status == "real_live_memory_commit_execution_gate_blocked"
    assert mismatch.report.findings[0].code == "real_executor_execution_commit_window_packet_digest_mismatch"

    payload = load(READY)
    payload["real_live_memory_commit_execution_gate_candidates"][0]["operator_scope_keys"] = ["different"]
    scope = evaluate_real_live_memory_commit_execution_gate(payload)
    assert scope.status == "real_live_memory_commit_execution_gate_blocked"
    assert scope.report.findings[0].code == "scope_mismatch"

    payload = load(READY)
    payload["real_live_memory_commit_execution_gate_candidates"][0]["real_live_memory_commit_execution_gate_claims"] = {"live_commit_executed": True}
    forbidden = evaluate_real_live_memory_commit_execution_gate(payload)
    assert forbidden.status == "real_live_memory_commit_execution_gate_blocked"
    assert forbidden.report.findings[0].code == "live_execution_claim"


def test_requires_non_noop_metadata_and_valid_policy() -> None:
    policy_result = validate_policy(build_default_policy())
    assert policy_result["status"] == "valid"

    payload = load(READY)
    del payload["real_live_memory_commit_execution_gate_candidates"][0]["live_memory_commit_execution_gate_readiness_metadata"]
    blocked = evaluate_real_live_memory_commit_execution_gate(payload)
    assert blocked.status == "real_live_memory_commit_execution_gate_blocked"
    assert blocked.report.findings[0].code == "missing_live_memory_commit_execution_gate_readiness_metadata"

    invalid_policy = build_default_policy()
    object.__setattr__(invalid_policy, "metadata_only", False)
    invalid = validate_policy(invalid_policy)
    assert invalid["status"] == "invalid"
