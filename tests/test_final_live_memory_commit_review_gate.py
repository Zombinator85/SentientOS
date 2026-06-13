from __future__ import annotations

import json

import pytest
from pathlib import Path

from sentientos.final_live_memory_commit_review_gate import (
    FALSE_FLAGS,
    FUTURE_FLAGS,
    INVARIANTS,
    FINAL_LIVE_MEMORY_COMMIT_REVIEW_GATE_CANDIDATE_TYPES,
    build_default_policy,
    evaluate_final_live_memory_commit_review_gate,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURE_ROOT = Path("tests/fixtures/final_live_memory_commit_review_gate")


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_ready_final_live_memory_commit_review_gate_is_metadata_only() -> None:
    result = evaluate_final_live_memory_commit_review_gate(load("ready_final_live_memory_commit_review_gate_candidate.json"))
    assert result.status == "final_live_memory_commit_review_gate_ready"
    assert result.gate is not None
    record = result.gate.records[0].to_dict()
    assert record["final_live_memory_commit_review_gate_decision"] == "final_live_memory_commit_review_gate_ready_for_later_real_memory_root_admission_gate"
    assert record["real_live_memory_commit_adapter_readiness_envelope_digest"].startswith("sha256:")
    assert record["real_live_memory_commit_adapter_readiness_envelope_decision"] == "real_live_memory_commit_adapter_readiness_envelope_ready_for_later_final_live_memory_commit_review_gate"
    assert record["adapter_readiness_envelope_confirmation_records"][0]["metadata_only"] is True
    assert record["adapter_readiness_gate_confirmation_records"][0]["metadata_only"] is True
    assert record["adapter_admission_packet_confirmation_records"][0]["metadata_only"] is True
    assert record["adapter_admission_gate_confirmation_records"][0]["metadata_only"] is True
    assert record["live_memory_commit_execution_packet_confirmation_records"][0]["metadata_only"] is True
    assert record["live_memory_commit_execution_gate_confirmation_records"][0]["metadata_only"] is True
    assert record["commit_window_packet_confirmation_records"][0]["metadata_only"] is True
    assert record["commit_plan_gate_confirmation_records"][0]["metadata_only"] is True
    assert record["commit_plan_packet_confirmation_records"][0]["metadata_only"] is True
    assert record["lock_lease_gate_confirmation_records"][0]["metadata_only"] is True
    assert record["live_commit_execution_denial_records"][0]["permission_granted"] is False
    assert record["live_memory_write_denial_records"][0]["executed"] is False
    assert record["real_memory_root_admission_deferral_records"][0]["metadata_only"] is True
    for name in INVARIANTS:
        assert record[name] is True
    for name in FALSE_FLAGS:
        assert record[name] is False
    for name in FUTURE_FLAGS:
        assert record[name] is True


def test_noop_and_mixed_statuses_are_deterministic() -> None:
    noop = evaluate_final_live_memory_commit_review_gate(load("noop_final_live_memory_commit_review_gate_candidate.json"))
    mixed = evaluate_final_live_memory_commit_review_gate(load("mixed_final_live_memory_commit_review_gate_candidate.json"))
    assert noop.status == "final_live_memory_commit_review_gate_noop"
    assert noop.gate is not None
    assert noop.gate.records[0].final_live_memory_commit_review_gate_decision == "final_live_memory_commit_review_gate_noop"
    assert mixed.status == "final_live_memory_commit_review_gate_ready_with_warnings"
    assert mixed.report.findings[0].code == "mixed_scope_diagnostic"
    assert evaluate_final_live_memory_commit_review_gate(load("ready_final_live_memory_commit_review_gate_candidate.json")).to_dict() == evaluate_final_live_memory_commit_review_gate(load("ready_final_live_memory_commit_review_gate_candidate.json")).to_dict()


def test_expected_candidate_types_are_registered() -> None:
    assert {
        "ai_capsule_final_live_memory_commit_review_gate_candidate",
        "human_summary_final_live_memory_commit_review_gate_candidate",
        "dual_capsule_final_live_memory_commit_review_gate_candidate",
        "protect_receipt_final_live_memory_commit_review_gate_candidate",
        "merge_receipt_final_live_memory_commit_review_gate_candidate",
        "tomb_archive_final_live_memory_commit_review_gate_candidate",
        "tomb_deferred_final_live_memory_commit_review_gate_candidate",
        "operator_review_final_live_memory_commit_review_gate_candidate",
        "noop_final_live_memory_commit_review_gate_candidate",
        "mixed_final_live_memory_commit_review_gate_candidate",
    } <= FINAL_LIVE_MEMORY_COMMIT_REVIEW_GATE_CANDIDATE_TYPES


def test_blocks_digest_mismatch_forbidden_claims_and_missing_metadata() -> None:
    cases = {
        "digest_mismatch_blocked.json": "real_live_memory_commit_adapter_readiness_envelope_digest_mismatch",
        "live_commit_execution_blocked.json": "live_commit_executed",
        "missing_audit_readiness_metadata_blocked.json": "missing_audit_readiness_metadata",
    }
    for fixture, code in cases.items():
        result = evaluate_final_live_memory_commit_review_gate(load(fixture))
        assert result.status == "final_live_memory_commit_review_gate_blocked"
        assert result.report.findings[0].code == code
        assert result.gate is None


def test_policy_validation_and_no_unsafe_runtime_surfaces() -> None:
    assert validate_policy()["status"] == "valid"
    policy = build_default_policy()
    object.__setattr__(policy, "metadata_only", False)
    assert validate_policy(policy)["status"] == "invalid"
    text = Path("sentientos/final_live_memory_commit_review_gate.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler", "write_text(", "open("]
    assert not any(marker in text for marker in forbidden)
