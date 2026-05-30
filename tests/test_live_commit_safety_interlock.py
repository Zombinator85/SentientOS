from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.live_commit_safety_interlock import (
    FORBIDDEN_NEXT_STEPS,
    LiveCommitSafetyInterlockPolicy,
    build_default_policy,
    evaluate_live_commit_safety_interlock,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/live_commit_safety_interlock")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_is_default_deny_and_interlock_only() -> None:
    policy = build_default_policy()
    assert policy.default_interlock_posture == "deny"
    assert policy.allow_future_adapter_consideration is True
    assert policy.allow_warning_consideration is True
    assert policy.allow_operator_review_deferrals is True
    assert policy.allow_noop_consideration is True
    assert policy.allow_mixed_scope_diagnostic_packet is False
    assert policy.require_dry_run_ready is True
    assert policy.require_execution_gate_ready is True
    assert policy.require_matching_dry_run_digest is True
    assert policy.require_matching_execution_gate_digest is True
    assert policy.require_matching_dry_run_decision is True
    assert policy.require_matching_execution_gate_decision is True
    assert policy.require_operation_preview is True
    assert policy.require_receipt_preview is True
    assert policy.require_rollback_preview is True
    assert policy.require_safety_preconditions is True
    assert policy.require_scope_alignment is True
    assert policy.block_live_write_claims is True
    assert policy.block_live_delete_claims is True
    assert policy.block_index_mutation_claims is True
    assert policy.block_capsule_persistence_claims is True
    assert policy.block_tomb_completion_claims is True
    assert policy.block_hard_override_attempts is True
    assert validate_policy(policy)["status"] == "valid"


def test_valid_candidate_fixtures_are_ready_or_expected_terminal_states() -> None:
    expected = {
        "valid_ai_capsule_commit_interlock_candidate.json": ("live_commit_safety_interlock_ready", "live_commit_adapter_consideration_eligible"),
        "valid_human_summary_commit_interlock_candidate.json": ("live_commit_safety_interlock_ready", "live_commit_adapter_consideration_eligible"),
        "valid_dual_capsule_commit_interlock_candidate.json": ("live_commit_safety_interlock_ready", "live_commit_adapter_consideration_eligible"),
        "valid_protect_receipt_commit_interlock_candidate.json": ("live_commit_safety_interlock_ready", "live_commit_adapter_consideration_eligible"),
        "valid_merge_receipt_commit_interlock_candidate.json": ("live_commit_safety_interlock_ready", "live_commit_adapter_consideration_eligible"),
        "valid_tomb_archive_commit_interlock_candidate.json": ("live_commit_safety_interlock_ready", "live_commit_adapter_consideration_eligible"),
        "valid_tomb_deferred_commit_interlock_candidate.json": ("live_commit_safety_interlock_deferred_for_operator_review", "live_commit_adapter_consideration_deferred_for_operator_review"),
        "valid_operator_review_commit_interlock_candidate.json": ("live_commit_safety_interlock_deferred_for_operator_review", "live_commit_adapter_consideration_deferred_for_operator_review"),
        "valid_noop_commit_interlock_candidate.json": ("live_commit_safety_interlock_noop", "live_commit_adapter_consideration_noop"),
        "valid_warning_commit_interlock_candidate.json": ("live_commit_safety_interlock_ready_with_warnings", "live_commit_adapter_consideration_eligible_with_warnings"),
        "valid_mixed_scope_diagnostic_warning.json": ("live_commit_safety_interlock_ready_with_warnings", "live_commit_adapter_consideration_eligible_with_warnings"),
    }
    for fixture, (status, decision) in expected.items():
        result = evaluate_live_commit_safety_interlock(_fixture(fixture))
        assert result.status == status, fixture
        assert result.packet is not None
        record = result.packet.records[0]
        assert record.interlock_decision == decision
        assert record.interlock_future_consideration_only is True
        assert record.future_adapter_eligibility_record["live_commit_performed"] is False
        assert record.future_adapter_eligibility_record["final_live_commit_review_required"] is True
        if decision != "live_commit_adapter_consideration_noop":
            assert record.operation_preview["hypothetical_only"] is True
            assert record.receipt_preview["receipt_emitted"] is False
            assert record.rollback_preview["rollback_applied"] is False
            assert record.safety_preconditions[0].satisfied is True


def test_blocker_fixtures_return_expected_statuses() -> None:
    expected = {
        "missing_dry_run_packet_blocked.json": "live_commit_safety_interlock_blocked_missing_dry_run_packet",
        "invalid_dry_run_packet_blocked.json": "live_commit_safety_interlock_blocked_invalid_dry_run_packet",
        "missing_execution_gate_packet_blocked.json": "live_commit_safety_interlock_blocked_missing_execution_gate_packet",
        "invalid_execution_gate_packet_blocked.json": "live_commit_safety_interlock_blocked_invalid_execution_gate_packet",
        "missing_interlock_candidate_blocked.json": "live_commit_safety_interlock_blocked_missing_interlock_candidate",
        "invalid_interlock_candidate_blocked.json": "live_commit_safety_interlock_blocked_invalid_interlock_candidate",
        "dry_run_not_ready_blocked.json": "live_commit_safety_interlock_blocked_dry_run_not_ready",
        "execution_gate_not_ready_blocked.json": "live_commit_safety_interlock_blocked_execution_gate_not_ready",
        "dry_run_digest_mismatch_blocked.json": "live_commit_safety_interlock_blocked_dry_run_digest_mismatch",
        "execution_gate_digest_mismatch_blocked.json": "live_commit_safety_interlock_blocked_execution_gate_digest_mismatch",
        "dry_run_decision_mismatch_blocked.json": "live_commit_safety_interlock_blocked_dry_run_decision_mismatch",
        "execution_gate_decision_mismatch_blocked.json": "live_commit_safety_interlock_blocked_execution_gate_decision_mismatch",
        "missing_operation_preview_blocked.json": "live_commit_safety_interlock_blocked_missing_operation_preview",
        "missing_receipt_preview_blocked.json": "live_commit_safety_interlock_blocked_missing_receipt_preview",
        "missing_rollback_preview_blocked.json": "live_commit_safety_interlock_blocked_missing_rollback_preview",
        "missing_safety_precondition_blocked.json": "live_commit_safety_interlock_blocked_missing_safety_precondition",
        "safety_precondition_mismatch_blocked.json": "live_commit_safety_interlock_blocked_safety_precondition_mismatch",
        "live_write_claim_blocked.json": "live_commit_safety_interlock_blocked_live_write_claim",
        "live_delete_claim_blocked.json": "live_commit_safety_interlock_blocked_live_delete_claim",
        "index_mutation_claim_blocked.json": "live_commit_safety_interlock_blocked_index_mutation_claim",
        "capsule_persistence_claim_blocked.json": "live_commit_safety_interlock_blocked_capsule_persistence_claim",
        "tomb_completion_claim_blocked.json": "live_commit_safety_interlock_blocked_tomb_completion_claim",
        "prompt_materialization_blocked.json": "live_commit_safety_interlock_blocked_prompt_materialization",
        "action_execution_blocked.json": "live_commit_safety_interlock_blocked_action_execution",
        "external_disclosure_blocked.json": "live_commit_safety_interlock_blocked_external_disclosure",
        "authority_smuggling_blocked.json": "live_commit_safety_interlock_blocked_authority_smuggling",
        "raw_payload_leak_blocked.json": "live_commit_safety_interlock_blocked_raw_payload_leak",
        "scope_mismatch_blocked.json": "live_commit_safety_interlock_blocked_scope_mismatch",
    }
    for fixture, status in expected.items():
        assert evaluate_live_commit_safety_interlock(_fixture(fixture)).status == status, fixture


def test_packet_invariants_and_forbidden_next_steps() -> None:
    result = evaluate_live_commit_safety_interlock(_fixture("valid_ai_capsule_commit_interlock_candidate.json"))
    assert result.packet is not None
    packet = result.packet.to_dict()
    for key in [
        "interlock_is_not_memory_write", "interlock_is_not_memory_deletion", "interlock_is_not_index_mutation",
        "interlock_is_not_capsule_persistence", "interlock_is_not_prompt_assembly", "interlock_is_not_execution",
        "interlock_is_not_live_commit", "interlock_is_not_truth", "interlock_is_not_policy", "interlock_is_not_authority",
        "interlock_is_not_consent", "interlock_does_not_execute_action", "interlock_does_not_disclose_externally",
        "default_deny_live_commit", "future_commit_adapter_required", "final_live_commit_review_required",
        "dry_run_adapter_required", "execution_gate_required", "receipt_preview_required", "rollback_preview_required", "safety_preconditions_required",
    ]:
        assert packet[key] is True
    for key in ["live_memory_write_enabled", "live_memory_deletion_enabled", "live_index_mutation_enabled", "capsule_persistence_enabled", "prompt_materialization_enabled", "external_disclosure_enabled", "remote_service_enabled"]:
        assert packet[key] is False
    required = {"write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "execute_interlock_as_commit", "execute_dry_run_as_commit", "run_live_commit_now", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "infer_truth_from_interlock", "infer_authority_from_interlock", "infer_consent_from_interlock", "convert_interlock_to_policy", "convert_interlock_to_action", "bypass_dry_run_adapter", "bypass_execution_gate", "bypass_operator_approval_packet", "bypass_commit_plan_packet", "bypass_live_boundary_admission", "bypass_governed_writer_adapter", "bypass_tomb_verifier", "bypass_receipt_gate", "bypass_distillation_contract", "bypass_operator_review", "enable_external_disclosure"}
    assert required.issubset(set(FORBIDDEN_NEXT_STEPS))
    assert required.issubset(set(packet["forbidden_next_steps"]))


def test_deterministic_json_digest_and_mixed_packet_counts() -> None:
    payload = _fixture("mixed_live_commit_safety_interlock_packet.json")
    first = evaluate_live_commit_safety_interlock(payload)
    second = evaluate_live_commit_safety_interlock(payload)
    assert first.to_dict() == second.to_dict()
    assert first.packet is not None
    assert first.report.summary_counts["candidate_count"] == 2
    assert first.report.summary_counts["live_commit_adapter_consideration_eligible"] == 1
    assert first.report.summary_counts["live_commit_adapter_consideration_noop"] == 1
    assert first.digest.startswith("sha256:")


def test_fixtures_are_metadata_only() -> None:
    forbidden = ["data:image", "data:audio", "data:video", "begin private", "provider prompt text", "real operator home", "/home/"]
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert not any(marker in text for marker in forbidden), path


def test_no_unsafe_surfaces_are_introduced() -> None:
    text = Path("sentientos/live_commit_safety_interlock.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler"]
    assert not any(marker in text for marker in forbidden)


def test_invalid_policy_rejected() -> None:
    result = validate_policy(LiveCommitSafetyInterlockPolicy(default_interlock_posture="allow"))
    assert result["status"] == "invalid"
