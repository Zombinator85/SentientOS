from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.live_executor_invocation_harness import (
    FAIL_STATUSES,
    evaluate_live_executor_invocation_harness,
    validate_policy,
)

FIXTURE = Path("tests/fixtures/live_executor_invocation_harness/ready_invocation_harness_candidate.json")
NOOP_FIXTURE = Path("tests/fixtures/live_executor_invocation_harness/noop_invocation_harness_candidate.json")


def load_ready() -> dict:
    return json.loads(FIXTURE.read_text())


def evaluate(payload: dict) -> dict:
    return evaluate_live_executor_invocation_harness(payload).to_dict()


def first_code(result: dict) -> str:
    return result["report"]["findings"][0]["code"]


def candidate(payload: dict) -> dict:
    return payload["invocation_harness_candidates"][0]


def record(payload: dict) -> dict:
    return payload["live_executor_activation_record"]["records"][0]


def test_ready_invocation_record_is_deterministic_metadata_only_and_non_authoritative() -> None:
    payload = load_ready()
    one = evaluate(payload)
    two = evaluate(copy.deepcopy(payload))
    assert one == two
    assert one["status"] == "invocation_harness_ready"
    packet = one["packet"]
    assert packet["invocation_harness_is_not_executor_invocation"] is True
    assert packet["invocation_harness_is_not_executor_activation"] is True
    assert packet["invocation_harness_is_not_lock_acquisition"] is True
    assert packet["invocation_harness_is_not_lockfile_creation"] is True
    assert packet["invocation_harness_is_not_memory_write"] is True
    assert packet["invocation_harness_is_not_memory_deletion"] is True
    assert packet["invocation_harness_is_not_memory_purge"] is True
    assert packet["invocation_harness_is_not_index_mutation"] is True
    assert packet["invocation_harness_is_not_capsule_persistence"] is True
    assert packet["invocation_harness_is_not_tomb_completion"] is True
    assert packet["invocation_harness_is_not_prompt_assembly"] is True
    assert packet["invocation_harness_is_not_live_context_retrieval"] is True
    assert packet["invocation_harness_is_not_action_execution"] is True
    assert packet["invocation_harness_is_not_external_disclosure"] is True
    assert packet["invocation_harness_is_not_live_commit_execution"] is True
    assert packet["invocation_harness_is_not_truth"] is True
    assert packet["invocation_harness_is_not_policy"] is True
    assert packet["invocation_harness_is_not_authority"] is True
    assert packet["invocation_harness_is_not_consent"] is True
    assert packet["invocation_readiness_is_metadata_only"] is True
    assert packet["operator_handoff_is_metadata_only"] is True
    assert packet["invocation_scope_is_metadata_only"] is True
    assert packet["invocation_handoff_is_metadata_only"] is True
    assert packet["abort_readiness_is_metadata_only"] is True
    assert packet["rollback_readiness_is_metadata_only"] is True
    assert packet["audit_readiness_is_metadata_only"] is True
    for disabled in (
        "real_executor_invocation_enabled", "real_executor_activation_enabled", "real_lock_acquisition_enabled", "lockfile_creation_enabled",
        "real_memory_root_write_enabled", "live_memory_write_enabled", "live_memory_deletion_enabled",
        "live_memory_purge_enabled", "live_index_mutation_enabled", "capsule_persistence_enabled",
        "tomb_completion_enabled", "prompt_materialization_enabled", "live_context_retrieval_enabled",
        "action_execution_enabled", "external_disclosure_enabled", "external_service_enabled", "live_executor_enabled",
    ):
        assert packet[disabled] is False
    assert packet["future_real_live_memory_commit_executor_required"] is True
    assert packet["future_live_executor_implementation_required"] is True
    assert packet["future_post_execution_audit_required"] is True
    rec = packet["records"][0]
    assert rec["invocation_decision"] == "invocation_harness_ready_for_later_live_executor"
    assert rec["executor_invoked"] is False
    assert rec["lock_acquired"] is False
    assert rec["lockfile_created"] is False
    assert rec["live_commit_executed"] is False
    assert rec["live_execution_permission_granted"] is False
    for key in (
        "invocation_readiness_records", "operator_handoff_records", "invocation_scope_records",
        "invocation_handoff_records", "abort_readiness_records", "rollback_readiness_records", "audit_readiness_records",
    ):
        assert rec[key][0]["metadata_only"] is True
        assert rec[key][0]["executor_invoked"] is False
        assert rec[key][0]["real_memory_root_access_performed"] is False


def test_policy_validation_keeps_executor_lock_and_lockfile_disabled() -> None:
    validation = validate_policy()
    assert validation["status"] == "valid"
    assert validation["policy"]["real_executor_invocation_enabled"] is False
    assert validation["policy"]["real_executor_activation_enabled"] is False
    assert validation["policy"]["real_lock_acquisition_enabled"] is False
    assert validation["policy"]["lockfile_creation_enabled"] is False


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda p: p.pop("live_executor_activation_record"), "missing_activation_record"),
        (lambda p: p.__setitem__("live_executor_activation_record", {"digest": "sha256:x", "records": []}), "invalid_activation_record"),
        (lambda p: p.pop("invocation_harness_candidates"), "missing_invocation_harness_candidate"),
        (lambda p: candidate(p).__setitem__("candidate_type", "bad"), "invalid_invocation_harness_candidate"),
        (lambda p: record(p).__setitem__("activation_decision", "activation_blocked"), "activation_record_not_ready"),
        (lambda p: candidate(p).__setitem__("claimed_activation_record_digest", "sha256:mismatch"), "activation_record_digest_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_activation_record_decision", "activation_noop"), "activation_record_decision_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_preflight_packet_digest", "sha256:mismatch"), "preflight_packet_digest_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_preflight_packet_decision", "preflight_noop"), "preflight_packet_decision_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_lock_lease_gate_digest", "sha256:mismatch"), "lock_lease_gate_digest_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_lock_lease_gate_decision", "lock_lease_noop"), "lock_lease_gate_decision_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_executor_plan_packet_digest", "sha256:mismatch"), "executor_plan_packet_digest_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_executor_plan_decision", "executor_plan_noop"), "executor_plan_decision_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_runtime_execution_gate_digest", "sha256:mismatch"), "runtime_execution_gate_digest_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_runtime_execution_gate_decision", "runtime_execution_noop"), "runtime_execution_gate_decision_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_readiness_envelope_digest", "sha256:mismatch"), "readiness_envelope_digest_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_readiness_envelope_decision", "readiness_noop"), "readiness_envelope_decision_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_final_review_digest", "sha256:mismatch"), "final_review_digest_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_final_review_decision", "review_noop"), "final_review_decision_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_real_root_admission_digest", "sha256:mismatch"), "real_root_admission_digest_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_real_root_admission_decision", "admission_noop"), "real_root_admission_decision_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_sandbox_commit_digest", "sha256:mismatch"), "sandbox_commit_digest_mismatch"),
        (lambda p: candidate(p).__setitem__("claimed_sandbox_commit_decision", "sandbox_noop"), "sandbox_commit_decision_mismatch"),
    ],
)
def test_required_evidence_blocks(mutation, code: str) -> None:
    payload = load_ready()
    mutation(payload)
    result = evaluate(payload)
    assert result["status"] == "invocation_harness_blocked"
    assert first_code(result) == code


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("activation_readiness_metadata", "missing_activation_readiness_metadata"),
        ("operator_acknowledgement_metadata", "missing_operator_acknowledgement_metadata"),
        ("activation_scope_metadata", "missing_activation_scope_metadata"),
        ("execution_handoff_metadata", "missing_execution_handoff_metadata"),
        ("final_preflight_readiness_metadata", "missing_final_preflight_readiness_metadata"),
        ("operation_inventory_digest_metadata", "missing_operation_inventory_digest_metadata"),
        ("safety_checklist_digest_metadata", "missing_safety_checklist_digest_metadata"),
        ("verification_checklist_digest_metadata", "missing_verification_checklist_digest_metadata"),
        ("abort_readiness_metadata", "missing_abort_readiness_metadata"),
        ("rollback_readiness_metadata", "missing_rollback_readiness_metadata"),
        ("audit_readiness_metadata", "missing_audit_readiness_metadata"),
        ("lock_lease_readiness_metadata", "missing_lock_lease_readiness_metadata"),
        ("operator_identity_role_metadata", "missing_operator_identity_role_metadata"),
        ("execution_window_metadata", "missing_execution_window_metadata"),
        ("idempotency_key_metadata", "missing_idempotency_key_metadata"),
        ("atomicity_boundary_metadata", "missing_atomicity_boundary_metadata"),
        ("dry_run_to_live_equivalence_metadata", "missing_dry_run_to_live_equivalence_metadata"),
        ("rollback_rehearsal_metadata", "missing_rollback_rehearsal_metadata"),
        ("post_execution_audit_metadata", "missing_post_execution_audit_metadata"),
        ("invocation_scope_metadata", "missing_invocation_scope_metadata"),
        ("invocation_handoff_metadata", "missing_invocation_handoff_metadata"),
        ("invocation_disablement_metadata", "missing_invocation_disablement_metadata"),
        ("future_executor_requirement_metadata", "missing_future_executor_requirement_metadata"),
    ],
)
def test_non_noop_metadata_is_required(field: str, code: str) -> None:
    payload = load_ready()
    candidate(payload)[field] = {}
    result = evaluate(payload)
    assert result["status"] == "invocation_harness_blocked"
    assert first_code(result) == code


@pytest.mark.parametrize(
    ("claim", "code"),
    [
        ({"executor_invoked": True}, "executor_invocation_claim"),
        ({"activation_execution_performed": True}, "activation_execution_claim"),
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
        ({"runtime_execution_claimed": True}, "runtime_execution_claim"),
        ({"invocation_harness_grants_permission": True}, "executor_permission_claim"),
        ({"invocation_readiness_is_live_execution": True}, "readiness_conversion_claim"),
        ({"final_review_is_execution_permission": True}, "final_review_conversion_claim"),
        ({"sandbox_commit_is_real_commit": True}, "sandbox_conversion_claim"),
        ({"real_root_admission_is_memory_root_access": True}, "real_root_admission_conversion_claim"),
        ({"prompt_assembly_claimed": True}, "prompt_materialization"),
        ({"live_context_retrieval_claimed": True}, "live_context_retrieval"),
        ({"action_execution_claimed": True}, "action_execution"),
        ({"external_disclosure_claimed": True}, "external_disclosure"),
        ({"authority_granted": True}, "authority_smuggling"),
        ({"consent_granted": True}, "consent_smuggling"),
        ({"policy_created": True}, "policy_smuggling"),
        ({"truth_asserted": True}, "truth_smuggling"),
        ({"raw_secret_payload": "secret: no"}, "raw_payload_leakage"),
    ],
)
def test_forbidden_claims_block(claim: dict, code: str) -> None:
    payload = load_ready()
    candidate(payload)["invocation_claims"] = claim
    result = evaluate(payload)
    assert result["status"] == "invocation_harness_blocked"
    assert first_code(result) == code


def test_scope_mismatch_blocks_and_mixed_diagnostic_warns_when_allowed() -> None:
    payload = load_ready()
    candidate(payload)["operator_scope_keys"] = ["other"]
    result = evaluate(payload)
    assert result["status"] == "invocation_harness_blocked"
    assert first_code(result) == "scope_mismatch"

    payload = load_ready()
    candidate(payload)["operator_scope_keys"] = ["other"]
    candidate(payload)["candidate_type"] = "mixed_invocation_harness_candidate"
    candidate(payload)["metadata"] = {"diagnostic_warning": True}
    result = evaluate(payload)
    assert result["status"] == "invocation_harness_ready_with_warnings"
    assert any(f["code"] == "scope_mismatch_diagnostic" for f in result["report"]["findings"])


def test_noop_behavior_is_deterministic_and_non_mutating() -> None:
    payload = json.loads(NOOP_FIXTURE.read_text())
    before = copy.deepcopy(payload)
    one = evaluate(payload)
    two = evaluate(copy.deepcopy(payload))
    assert one == two
    assert payload == before
    assert one["status"] == "invocation_harness_noop"
    assert one["packet"]["records"][0]["invocation_decision"] == "invocation_harness_noop"
    assert one["packet"]["records"][0]["executor_invoked"] is False
