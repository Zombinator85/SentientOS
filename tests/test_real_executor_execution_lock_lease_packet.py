from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sentientos.real_executor_execution_lock_lease_packet import (
    BOUNDARY_INVARIANTS,
    build_default_policy,
    evaluate_real_executor_execution_lock_lease_packet,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURE_ROOT = Path("tests/fixtures/real_executor_execution_lock_lease_packet")
READY = FIXTURE_ROOT / "ready_real_executor_execution_lock_lease_packet_candidate.json"
NOOP = FIXTURE_ROOT / "noop_real_executor_execution_lock_lease_packet_candidate.json"
MIXED = FIXTURE_ROOT / "mixed_real_executor_execution_lock_lease_packet_candidate.json"


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ready_packet_is_deterministic_metadata_only() -> None:
    first = evaluate_real_executor_execution_lock_lease_packet(load(READY))
    second = evaluate_real_executor_execution_lock_lease_packet(load(READY))

    assert first.to_dict() == second.to_dict()
    assert first.status == "real_executor_execution_lock_lease_packet_ready"
    assert first.packet is not None
    packet = first.packet.to_dict()
    record = packet["records"][0]
    assert packet["metadata_only"] is True
    assert packet["default_deny"] is True
    assert packet["not_permission_to_execute"] is True
    assert record["real_executor_execution_lock_lease_packet_decision"] == "real_executor_execution_lock_lease_packet_ready_for_later_real_executor_execution_lock_lease_gate"
    assert record["real_executor_execution_preflight_gate_decision"] == "real_executor_execution_preflight_gate_ready_for_later_real_executor_execution_lock_lease_packet"
    assert record["boundary_invariants"] == dict(sorted(BOUNDARY_INVARIANTS.items()))
    assert record["boundary_invariants"]["real_executor_execution_lock_lease_packet_does_not_acquire_locks"] is True
    assert record["boundary_invariants"]["real_executor_execution_lock_lease_packet_does_not_create_lockfiles"] is True
    assert record["boundary_invariants"]["real_executor_execution_lock_lease_packet_is_not_permission_to_execute"] is True
    assert record["boundary_invariants"]["real_lock_acquired"] is False
    assert record["boundary_invariants"]["lockfile_created"] is False
    assert record["boundary_invariants"]["future_real_executor_execution_lock_lease_gate_required"] is True
    assert "lock_acquisition" in record["forbidden_next_steps"]
    assert "lock_lease_creation" in record["forbidden_next_steps"]


def test_noop_and_mixed_statuses() -> None:
    noop = evaluate_real_executor_execution_lock_lease_packet(load(NOOP))
    mixed = evaluate_real_executor_execution_lock_lease_packet(load(MIXED))

    assert noop.status == "real_executor_execution_lock_lease_packet_noop"
    assert noop.packet is not None
    assert noop.packet.records[0].real_executor_execution_lock_lease_packet_decision == "real_executor_execution_lock_lease_packet_noop"
    assert mixed.status == "real_executor_execution_lock_lease_packet_ready_with_warnings"
    assert mixed.packet is not None
    assert mixed.packet.records[0].real_executor_execution_lock_lease_packet_decision == "real_executor_execution_lock_lease_packet_ready_with_warnings"
    assert mixed.report.findings[0].code == "mixed_scope_diagnostic"


def test_blocks_missing_mismatched_or_forbidden_evidence() -> None:
    missing = evaluate_real_executor_execution_lock_lease_packet({"real_executor_execution_lock_lease_packet_candidates": []})
    assert missing.status == "real_executor_execution_lock_lease_packet_blocked"
    assert missing.report.findings[0].code == "missing_real_executor_execution_preflight_gate"

    payload = load(READY)
    payload["real_executor_execution_lock_lease_packet_candidates"][0]["claimed_real_executor_execution_preflight_gate_digest"] = "sha256:wrong"  # type: ignore[index]
    mismatch = evaluate_real_executor_execution_lock_lease_packet(payload)
    assert mismatch.status == "real_executor_execution_lock_lease_packet_blocked"
    assert mismatch.report.findings[0].code == "real_executor_execution_preflight_gate_digest_mismatch"

    payload = load(READY)
    payload["real_executor_execution_lock_lease_packet_candidates"][0]["operator_scope_keys"] = ["different"]  # type: ignore[index]
    scope = evaluate_real_executor_execution_lock_lease_packet(payload)
    assert scope.status == "real_executor_execution_lock_lease_packet_blocked"
    assert scope.report.findings[0].code == "scope_mismatch"

    payload = load(READY)
    payload["real_executor_execution_lock_lease_packet_candidates"][0]["real_executor_execution_lock_lease_packet_claims"] = {"real_lock_acquired": True}  # type: ignore[index]
    forbidden = evaluate_real_executor_execution_lock_lease_packet(payload)
    assert forbidden.status == "real_executor_execution_lock_lease_packet_blocked"
    assert forbidden.report.findings[0].code == "lock_acquisition_claim"


def test_requires_non_noop_metadata_and_valid_policy() -> None:
    policy_result = validate_policy(build_default_policy())
    assert policy_result["status"] == "valid"

    payload = load(READY)
    del payload["real_executor_execution_lock_lease_packet_candidates"][0]["lock_lease_packet_readiness_metadata"]  # type: ignore[index]
    blocked = evaluate_real_executor_execution_lock_lease_packet(payload)
    assert blocked.status == "real_executor_execution_lock_lease_packet_blocked"
    assert blocked.report.findings[0].code == "missing_lock_lease_packet_readiness_metadata"

    invalid_policy = build_default_policy()
    object.__setattr__(invalid_policy, "metadata_only", False)
    invalid = validate_policy(invalid_policy)
    assert invalid["status"] == "invalid"
