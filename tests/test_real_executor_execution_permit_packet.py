from __future__ import annotations

import json
from pathlib import Path

from sentientos.real_executor_execution_permit_packet import (
    INVARIANTS,
    RealExecutorExecutionPermitPacketResult,
    build_default_policy,
    evaluate_real_executor_execution_permit_packet,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/real_executor_execution_permit_packet")
READY = FIXTURE_ROOT / "ready_real_executor_execution_permit_packet_candidate.json"
NOOP = FIXTURE_ROOT / "noop_real_executor_execution_permit_packet_candidate.json"
MIXED = FIXTURE_ROOT / "mixed_real_executor_execution_permit_packet_candidate.json"


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ready_execution_permit_packet_is_deterministic_metadata_only() -> None:
    first = evaluate_real_executor_execution_permit_packet(load(READY))
    second = evaluate_real_executor_execution_permit_packet(load(READY))

    assert isinstance(first, RealExecutorExecutionPermitPacketResult)
    assert first.to_dict() == second.to_dict()
    assert first.status == "real_executor_execution_permit_packet_ready"
    assert first.packet is not None
    assert first.packet.digest.startswith("sha256:")
    packet = first.packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert packet[key] is expected
    record = packet["records"][0]
    assert record["real_executor_execution_permit_packet_decision"] == "real_executor_execution_permit_packet_ready_for_later_real_executor_execution_permit_gate"
    assert record["real_executor_execution_authorization_gate_digest"] == load(READY)["real_executor_execution_authorization_gate"]["digest"]
    assert record["authorization_gate_confirmation_records"][0]["metadata_only"] is True
    assert record["permit_packet_readiness_records"][0]["metadata_only"] is True
    assert record["execution_permit_denial_records"][0]["permission_granted"] is False
    assert record["final_permit_hold_point_records"][0]["executed"] is False
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
    noop = evaluate_real_executor_execution_permit_packet(load(NOOP))
    mixed = evaluate_real_executor_execution_permit_packet(load(MIXED))

    assert noop.status == "real_executor_execution_permit_packet_noop"
    assert noop.packet is not None
    assert noop.packet.records[0].real_executor_execution_permit_packet_decision == "real_executor_execution_permit_packet_noop"
    assert mixed.status == "real_executor_execution_permit_packet_ready_with_warnings"
    assert mixed.packet is not None
    assert mixed.packet.records[0].real_executor_execution_permit_packet_decision == "real_executor_execution_permit_packet_ready_with_warnings"
    assert mixed.report.findings[0].code == "mixed_scope_diagnostic"


def test_blocks_missing_mismatched_or_forbidden_evidence() -> None:
    missing = evaluate_real_executor_execution_permit_packet({"real_executor_execution_permit_packet_candidates": []})
    assert missing.status == "real_executor_execution_permit_packet_blocked"
    assert missing.report.findings[0].code == "missing_real_executor_execution_authorization_gate"

    payload = load(READY)
    payload["real_executor_execution_permit_packet_candidates"][0]["claimed_real_executor_execution_gate_digest"] = "sha256:wrong"
    mismatch = evaluate_real_executor_execution_permit_packet(payload)
    assert mismatch.status == "real_executor_execution_permit_packet_blocked"
    assert mismatch.report.findings[0].code == "real_executor_execution_gate_digest_mismatch"

    payload = load(READY)
    payload["real_executor_execution_permit_packet_candidates"][0]["operator_scope_keys"] = ["different"]
    scope = evaluate_real_executor_execution_permit_packet(payload)
    assert scope.status == "real_executor_execution_permit_packet_blocked"
    assert scope.report.findings[0].code == "scope_mismatch"

    payload = load(READY)
    payload["real_executor_execution_permit_packet_candidates"][0]["real_executor_execution_permit_packet_claims"] = {"live_commit_executed": True}
    forbidden = evaluate_real_executor_execution_permit_packet(payload)
    assert forbidden.status == "real_executor_execution_permit_packet_blocked"
    assert forbidden.report.findings[0].code == "live_execution_claim"


def test_requires_non_noop_metadata_and_valid_policy() -> None:
    policy_result = validate_policy(build_default_policy())
    assert policy_result["status"] == "valid"

    payload = load(READY)
    del payload["real_executor_execution_permit_packet_candidates"][0]["permit_packet_readiness_metadata"]
    blocked = evaluate_real_executor_execution_permit_packet(payload)
    assert blocked.status == "real_executor_execution_permit_packet_blocked"
    assert blocked.report.findings[0].code == "missing_permit_packet_readiness_metadata"

    invalid_policy = build_default_policy()
    object.__setattr__(invalid_policy, "metadata_only", False)
    invalid = validate_policy(invalid_policy)
    assert invalid["status"] == "invalid"
