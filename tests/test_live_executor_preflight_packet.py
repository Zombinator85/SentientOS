from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.live_executor_preflight_packet import (
    INVARIANTS,
    PreflightPolicy,
    evaluate_live_executor_preflight_packet,
    validate_policy,
)

FIXTURE = Path("tests/fixtures/live_executor_preflight_packet/valid_ai_capsule_preflight_candidate.json")
NOOP_FIXTURE = Path("tests/fixtures/live_executor_preflight_packet/noop_preflight_candidate.json")


def load_valid() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def candidate(payload: dict) -> dict:
    return payload["preflight_candidates"][0]


def lock_record(payload: dict) -> dict:
    return payload["live_executor_lock_lease_gate_packet"]["records"][0]


def assert_blocked(payload: dict, code: str) -> None:
    result = evaluate_live_executor_preflight_packet(payload)
    assert result.status == "preflight_blocked"
    assert result.packet is None
    assert result.report.findings[0].code == code


def test_valid_preflight_packet_is_deterministic_metadata_only() -> None:
    payload = load_valid()
    first = evaluate_live_executor_preflight_packet(payload)
    second = evaluate_live_executor_preflight_packet(payload)
    assert first.to_dict() == second.to_dict()
    assert first.status == "preflight_ready"
    packet = first.packet
    assert packet is not None
    packet_dict = packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert packet_dict[key] is expected
    record = packet.records[0]
    assert record.preflight_decision == "preflight_ready_for_later_live_executor"
    assert record.preflight_execution_performed is False
    assert record.lock_acquired is False
    assert record.lockfile_created is False
    assert record.live_commit_executed is False
    assert record.live_execution_permission_granted is False
    assert record.operation_inventory_records[0]["metadata_only"] is True
    assert record.operation_inventory_records[0]["operation_intents_only"] is True
    assert record.final_preflight_readiness_records[0]["metadata_only"] is True
    assert record.safety_checklist_records[0]["metadata_only"] is True
    assert record.verification_checklist_records[0]["metadata_only"] is True
    assert record.abort_readiness_records[0]["metadata_only"] is True
    assert record.rollback_readiness_records[0]["metadata_only"] is True
    assert record.audit_readiness_records[0]["metadata_only"] is True
    assert record.verification_checklist_records[0]["receipt_targets_are_metadata_only"] is True
    assert record.rollback_readiness_records[0]["rollback_targets_are_metadata_only"] is True
    assert "invoke_direct_live_executor_now" in record.forbidden_next_steps


def test_policy_validation_blocks_authority_enabling() -> None:
    result = validate_policy(PreflightPolicy(default_posture="allow", real_lock_acquisition_enabled=True, lockfile_creation_enabled=True, live_executor_enabled=True))
    assert result["status"] == "invalid"
    codes = {finding["code"] for finding in result["findings"]}
    assert {"default_posture_not_deny", "real_lock_acquisition_enabled", "lockfile_creation_enabled", "live_executor_enabled"} <= codes


def test_missing_or_invalid_lock_lease_gate_packet_blocks() -> None:
    payload = load_valid(); payload.pop("live_executor_lock_lease_gate_packet")
    assert_blocked(payload, "missing_lock_lease_gate_packet")
    payload = load_valid(); payload["live_executor_lock_lease_gate_packet"] = {"records": []}
    assert_blocked(payload, "invalid_lock_lease_gate_packet")


def test_missing_or_invalid_preflight_candidate_blocks() -> None:
    payload = load_valid(); payload["preflight_candidates"] = []
    assert_blocked(payload, "missing_preflight_candidate")
    payload = load_valid(); candidate(payload)["candidate_type"] = "unknown"
    assert_blocked(payload, "invalid_preflight_candidate")


def test_lock_lease_not_ready_blocks_by_default() -> None:
    payload = load_valid(); lock_record(payload)["lock_lease_decision"] = "lock_lease_blocked"
    assert_blocked(payload, "lock_lease_gate_not_ready")


MISMATCH_CASES = [
    ("claimed_lock_lease_gate_packet_digest", "wrong", "lock_lease_gate_digest_mismatch"),
    ("claimed_lock_lease_gate_decision", "wrong", "lock_lease_gate_decision_mismatch"),
    ("claimed_executor_plan_packet_digest", "wrong", "executor_plan_digest_mismatch"),
    ("claimed_executor_plan_decision", "wrong", "executor_plan_decision_mismatch"),
    ("claimed_runtime_execution_gate_digest", "wrong", "runtime_execution_gate_digest_mismatch"),
    ("claimed_runtime_execution_gate_decision", "wrong", "runtime_execution_gate_decision_mismatch"),
    ("claimed_readiness_envelope_digest", "wrong", "readiness_envelope_digest_mismatch"),
    ("claimed_readiness_envelope_decision", "wrong", "readiness_envelope_decision_mismatch"),
    ("claimed_final_review_digest", "wrong", "final_review_digest_mismatch"),
    ("claimed_final_review_decision", "wrong", "final_review_decision_mismatch"),
    ("claimed_real_root_admission_digest", "wrong", "real_root_admission_digest_mismatch"),
    ("claimed_real_root_admission_decision", "wrong", "real_root_admission_decision_mismatch"),
    ("claimed_sandbox_commit_digest", "wrong", "sandbox_commit_digest_mismatch"),
    ("claimed_sandbox_commit_decision", "wrong", "sandbox_commit_decision_mismatch"),
]


def test_evidence_matching_blocks_mismatches() -> None:
    for field, value, code in MISMATCH_CASES:
        payload = load_valid()
        candidate(payload)[field] = value
        assert_blocked(payload, code)


REQUIRED_METADATA = [
    ("operation_list_digest_metadata", "missing_operation_list_digest_metadata"),
    ("operation_inventory_metadata", "missing_operation_inventory_metadata"),
    ("operation_ordering_metadata", "missing_operation_ordering_metadata"),
    ("per_operation_precondition_metadata", "missing_per_operation_precondition_metadata"),
    ("per_operation_receipt_target_metadata", "missing_receipt_target_metadata"),
    ("per_operation_rollback_target_metadata", "missing_rollback_target_metadata"),
    ("lock_lease_readiness_metadata", "missing_lock_lease_readiness_metadata"),
    ("lease_duration_metadata", "missing_lease_duration_metadata"),
    ("lock_owner_metadata", "missing_lock_owner_metadata"),
    ("operator_identity_role_metadata", "missing_operator_identity_role_metadata"),
    ("execution_window_metadata", "missing_execution_window_metadata"),
    ("idempotency_key_metadata", "missing_idempotency_key_metadata"),
    ("atomicity_boundary_metadata", "missing_atomicity_boundary_metadata"),
    ("dry_run_to_live_equivalence_metadata", "missing_dry_run_to_live_equivalence_metadata"),
    ("rollback_rehearsal_metadata", "missing_rollback_rehearsal_metadata"),
    ("post_execution_audit_metadata", "missing_post_execution_audit_metadata"),
    ("verification_checklist_metadata", "missing_verification_checklist_metadata"),
    ("abort_panic_stop_condition_metadata", "missing_abort_panic_stop_condition_metadata"),
    ("contamination_check_metadata", "missing_contamination_check_metadata"),
    ("generated_artifact_cleanup_expectation_metadata", "missing_generated_artifact_cleanup_expectation_metadata"),
    ("final_clean_tree_expectation_metadata", "missing_final_clean_tree_expectation_metadata"),
    ("future_executor_requirement_metadata", "missing_future_executor_requirement_metadata"),
]


def test_non_noop_candidates_require_all_preflight_metadata() -> None:
    for field, code in REQUIRED_METADATA:
        payload = load_valid()
        candidate(payload)[field] = {}
        assert_blocked(payload, code)


CLAIM_CASES = [
    ({"preflight_execution_performed": True}, "preflight_execution_claim"),
    ({"lock_acquired": True}, "real_lock_acquisition_claim"),
    ({"lockfile_created": True}, "lockfile_creation_claim"),
    ({"live_memory_write_claimed": True}, "live_write_claim"),
    ({"live_memory_delete_claimed": True}, "live_delete_claim"),
    ({"live_memory_purge_claimed": True}, "live_purge_claim"),
    ({"live_index_mutation_claimed": True}, "index_mutation_claim"),
    ({"capsule_persistence_claimed": True}, "capsule_persistence_claim"),
    ({"tomb_completion_claimed": True}, "tomb_completion_claim"),
    ({"protection_application_claimed": True}, "protection_application_claim"),
    ({"merge_application_claimed": True}, "merge_application_claim"),
    ({"real_memory_root_access_claimed": True}, "real_memory_root_access_claim"),
    ({"prompt_assembly_claimed": True}, "prompt_materialization"),
    ({"live_context_retrieval_claimed": True}, "live_context_retrieval"),
    ({"action_execution_claimed": True}, "action_execution"),
    ({"external_disclosure_claimed": True}, "external_disclosure"),
    ({"authority_granted": True}, "authority_smuggling"),
    ({"consent_granted": True}, "consent_smuggling"),
    ({"policy_created": True}, "policy_smuggling"),
    ({"truth_created": True}, "truth_smuggling"),
    ({"sandbox_commit_is_real_commit": True}, "sandbox_conversion_claim"),
    ({"real_root_admission_is_memory_root_access": True}, "real_root_admission_conversion_claim"),
]


def test_forbidden_claims_block() -> None:
    for claims, code in CLAIM_CASES:
        payload = load_valid()
        candidate(payload)["preflight_claims"] = claims
        assert_blocked(payload, code)


def test_raw_payload_leakage_blocks() -> None:
    payload = load_valid()
    candidate(payload)["metadata"] = {"raw_private_payload": "secret: no"}
    assert_blocked(payload, "raw_payload_leak")


def test_scope_mismatch_blocks_and_mixed_diagnostic_warns_when_allowed() -> None:
    payload = load_valid()
    candidate(payload)["operator_scope_keys"] = ["different"]
    assert_blocked(payload, "scope_mismatch")

    payload = load_valid()
    candidate(payload)["candidate_type"] = "mixed_preflight_candidate"
    candidate(payload)["operator_scope_keys"] = ["different"]
    candidate(payload)["metadata"] = {"diagnostic_warning": True}
    result = evaluate_live_executor_preflight_packet(payload)
    assert result.status == "preflight_ready_with_warnings"
    assert any(f.code == "scope_mismatch_diagnostic" for f in result.report.findings)


def test_noop_behavior_is_deterministic_and_non_mutating() -> None:
    payload = json.loads(NOOP_FIXTURE.read_text(encoding="utf-8"))
    original = copy.deepcopy(payload)
    result = evaluate_live_executor_preflight_packet(payload)
    assert payload == original
    assert result.status == "preflight_noop"
    assert result.packet is not None
    assert result.packet.records[0].preflight_decision == "preflight_noop"
    assert result.packet.records[0].lock_acquired is False
