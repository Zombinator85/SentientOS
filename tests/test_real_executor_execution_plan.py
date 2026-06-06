from __future__ import annotations

import json
from pathlib import Path

from sentientos.real_executor_execution_plan import (
    INVARIANTS,
    RealExecutorExecutionPlanResult,
    build_default_policy,
    evaluate_real_executor_execution_plan,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/real_executor_execution_plan")
READY = FIXTURE_ROOT / "ready_real_executor_execution_plan_candidate.json"
NOOP = FIXTURE_ROOT / "noop_real_executor_execution_plan_candidate.json"
MIXED = FIXTURE_ROOT / "mixed_real_executor_execution_plan_candidate.json"


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ready_execution_plan_is_deterministic_metadata_only() -> None:
    first = evaluate_real_executor_execution_plan(load(READY))
    second = evaluate_real_executor_execution_plan(load(READY))

    assert isinstance(first, RealExecutorExecutionPlanResult)
    assert first.to_dict() == second.to_dict()
    assert first.status == "real_executor_execution_plan_ready"
    assert first.packet is not None
    assert first.packet.digest.startswith("sha256:")
    packet = first.packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert packet[key] is expected
    record = packet["records"][0]
    assert record["real_executor_execution_plan_decision"] == "real_executor_execution_plan_ready_for_later_real_executor_execution_gate"
    assert record["real_executor_run_gate_digest"] == load(READY)["real_executor_run_gate"]["digest"]
    assert record["run_gate_confirmation_records"][0]["metadata_only"] is True
    assert record["execution_plan_readiness_records"][0]["metadata_only"] is True
    assert record["execution_authority_denial_records"][0]["permission_granted"] is False
    assert record["final_execution_hold_point_records"][0]["executed"] is False
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
    noop = evaluate_real_executor_execution_plan(load(NOOP))
    mixed = evaluate_real_executor_execution_plan(load(MIXED))

    assert noop.status == "real_executor_execution_plan_noop"
    assert noop.packet is not None
    assert noop.packet.records[0].real_executor_execution_plan_decision == "real_executor_execution_plan_noop"
    assert mixed.status == "real_executor_execution_plan_ready_with_warnings"
    assert mixed.packet is not None
    assert mixed.packet.records[0].real_executor_execution_plan_decision == "real_executor_execution_plan_ready_with_warnings"
    assert mixed.report.findings[0].code == "mixed_scope_diagnostic"


def test_blocks_missing_mismatched_or_forbidden_evidence() -> None:
    missing = evaluate_real_executor_execution_plan({"real_executor_execution_plan_candidates": []})
    assert missing.status == "real_executor_execution_plan_blocked"
    assert missing.report.findings[0].code == "missing_real_executor_run_gate"

    payload = load(READY)
    payload["real_executor_execution_plan_candidates"][0]["claimed_real_executor_run_gate_digest"] = "sha256:wrong"
    mismatch = evaluate_real_executor_execution_plan(payload)
    assert mismatch.status == "real_executor_execution_plan_blocked"
    assert mismatch.report.findings[0].code == "real_executor_run_gate_digest_mismatch"

    payload = load(READY)
    payload["real_executor_execution_plan_candidates"][0]["operator_scope_keys"] = ["different"]
    scope = evaluate_real_executor_execution_plan(payload)
    assert scope.status == "real_executor_execution_plan_blocked"
    assert scope.report.findings[0].code == "scope_mismatch"

    payload = load(READY)
    payload["real_executor_execution_plan_candidates"][0]["real_executor_execution_plan_claims"] = {"live_commit_executed": True}
    forbidden = evaluate_real_executor_execution_plan(payload)
    assert forbidden.status == "real_executor_execution_plan_blocked"
    assert forbidden.report.findings[0].code == "live_execution_claim"


def test_requires_non_noop_metadata_and_valid_policy() -> None:
    policy_result = validate_policy(build_default_policy())
    assert policy_result["status"] == "valid"

    payload = load(READY)
    del payload["real_executor_execution_plan_candidates"][0]["execution_plan_readiness_metadata"]
    blocked = evaluate_real_executor_execution_plan(payload)
    assert blocked.status == "real_executor_execution_plan_blocked"
    assert blocked.report.findings[0].code == "missing_execution_plan_readiness_metadata"

    invalid_policy = build_default_policy()
    object.__setattr__(invalid_policy, "metadata_only", False)
    invalid = validate_policy(invalid_policy)
    assert invalid["status"] == "invalid"
