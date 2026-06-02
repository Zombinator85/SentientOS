from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sentientos.real_live_memory_commit_executor_enablement_gate import (
    INVARIANTS,
    build_default_policy,
    evaluate_real_live_memory_commit_executor_enablement_gate as evaluate,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/real_live_memory_commit_executor_enablement_gate")
READY_FIXTURE = FIXTURE_ROOT / "ready_executor_enablement_candidate.json"
NOOP_FIXTURE = FIXTURE_ROOT / "noop_executor_enablement_candidate.json"


def load_ready() -> dict:
    return json.loads(READY_FIXTURE.read_text())


def candidate(payload: dict) -> dict:
    return payload["executor_enablement_candidates"][0]


def skeleton_packet(payload: dict) -> dict:
    return payload["real_live_memory_commit_executor_implementation_skeleton"]


def skeleton_record(payload: dict) -> dict:
    return skeleton_packet(payload)["records"][0]


def first_code(result) -> str:
    return result.report.findings[0].code


def test_ready_enablement_gate_is_metadata_only_and_default_disabled() -> None:
    payload = load_ready()
    before = copy.deepcopy(payload)
    result = evaluate(payload)
    data = result.to_dict()
    assert payload == before
    assert data["status"] == "executor_enablement_ready"
    assert data["packet"]["records"][0]["executor_enablement_decision"] == "executor_enablement_ready_for_later_constrained_enable_path"
    for key, expected in INVARIANTS.items():
        assert data["packet"][key] is expected
    record = data["packet"]["records"][0]
    assert record["real_executor_enabled"] is False
    assert record["real_executor_enablement_enabled"] is False
    assert record["executor_invoked"] is False
    assert record["executor_activated"] is False
    assert record["lock_acquired"] is False
    assert record["lockfile_created"] is False
    assert record["live_commit_executed"] is False
    assert record["live_execution_permission_granted"] is False
    for collection in (
        "enablement_readiness_records",
        "disabled_posture_confirmation_records",
        "operator_enable_acknowledgement_records",
        "enablement_scope_records",
        "abort_readiness_records",
        "rollback_readiness_records",
        "post_enable_verification_records",
        "audit_readiness_records",
    ):
        assert record[collection][0]["metadata_only"] is True
        assert record[collection][0]["executor_enabled"] is False
        assert record[collection][0]["real_memory_mutation_performed"] is False


def test_validate_policy_defaults_to_deny_and_blocks_enabled_flags() -> None:
    assert validate_policy()["status"] == "valid"
    policy = build_default_policy().__class__(real_executor_enablement_enabled=True)
    result = validate_policy(policy)
    assert result["status"] == "invalid"
    assert result["findings"][0]["code"] == "real_executor_enablement_enabled"


def test_missing_or_invalid_executor_skeleton_packet_blocks() -> None:
    payload = load_ready()
    payload.pop("real_live_memory_commit_executor_implementation_skeleton")
    assert first_code(evaluate(payload)) == "missing_executor_skeleton_packet"

    payload = load_ready()
    skeleton_packet(payload)["records"] = []
    assert first_code(evaluate(payload)) == "invalid_executor_skeleton_packet"


def test_missing_or_invalid_enablement_candidate_blocks() -> None:
    payload = load_ready()
    payload["executor_enablement_candidates"] = []
    assert first_code(evaluate(payload)) == "missing_executor_enablement_candidate"

    payload = load_ready()
    candidate(payload)["candidate_type"] = "bad"
    assert first_code(evaluate(payload)) == "invalid_executor_enablement_candidate"


def test_executor_skeleton_not_ready_blocks_by_default() -> None:
    payload = load_ready()
    skeleton_record(payload)["executor_skeleton_decision"] = "executor_skeleton_blocked"
    assert first_code(evaluate(payload)) == "executor_skeleton_not_ready"


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("executor_skeleton", "executor_skeleton_digest_mismatch"),
        ("invocation_harness", "invocation_harness_digest_mismatch"),
        ("activation_record", "activation_record_digest_mismatch"),
        ("preflight_packet", "preflight_packet_digest_mismatch"),
        ("lock_lease_gate", "lock_lease_gate_digest_mismatch"),
        ("executor_plan_packet", "executor_plan_packet_digest_mismatch"),
        ("runtime_execution_gate", "runtime_execution_gate_digest_mismatch"),
        ("readiness_envelope", "readiness_envelope_digest_mismatch"),
        ("final_review", "final_review_digest_mismatch"),
        ("real_root_admission", "real_root_admission_digest_mismatch"),
        ("sandbox_commit", "sandbox_commit_digest_mismatch"),
    ],
)
def test_upstream_digest_mismatches_block(field: str, code: str) -> None:
    payload = load_ready()
    candidate(payload)[f"claimed_{field}_digest"] = "sha256:bad"
    result = evaluate(payload)
    assert result.status == "executor_enablement_blocked"
    assert first_code(result) == code


@pytest.mark.parametrize(
    ("field", "decision_key", "code"),
    [
        ("executor_skeleton", "executor_skeleton", "executor_skeleton_decision_mismatch"),
        ("invocation_harness", "invocation_harness", "invocation_harness_decision_mismatch"),
        ("activation_record", "activation_record", "activation_record_decision_mismatch"),
        ("preflight_packet", "preflight_packet", "preflight_packet_decision_mismatch"),
        ("lock_lease_gate", "lock_lease_gate", "lock_lease_gate_decision_mismatch"),
        ("executor_plan", "executor_plan", "executor_plan_packet_decision_mismatch"),
        ("runtime_execution_gate", "runtime_execution_gate", "runtime_execution_gate_decision_mismatch"),
        ("readiness_envelope", "readiness_envelope", "readiness_envelope_decision_mismatch"),
        ("final_review", "final_review", "final_review_decision_mismatch"),
        ("real_root_admission", "real_root_admission", "real_root_admission_decision_mismatch"),
        ("sandbox_commit", "sandbox_commit", "sandbox_commit_decision_mismatch"),
    ],
)
def test_upstream_decision_mismatches_block(field: str, decision_key: str, code: str) -> None:
    payload = load_ready()
    candidate(payload)[f"claimed_{decision_key}_decision"] = "bad"
    result = evaluate(payload)
    assert result.status == "executor_enablement_blocked"
    assert first_code(result) == code


@pytest.mark.parametrize(
    "field",
    [
        "executor_api_metadata",
        "disabled_execution_posture_metadata",
        "receipt_envelope_schema_metadata",
        "rollback_envelope_schema_metadata",
        "abort_envelope_schema_metadata",
        "verification_envelope_schema_metadata",
        "audit_readiness_metadata",
        "invocation_readiness_metadata",
        "invocation_scope_metadata",
        "invocation_handoff_metadata",
        "invocation_disablement_metadata",
        "activation_readiness_metadata",
        "operator_acknowledgement_metadata",
        "operator_enablement_acknowledgement_metadata",
        "activation_scope_metadata",
        "execution_handoff_metadata",
        "final_preflight_readiness_metadata",
        "operation_inventory_digest_metadata",
        "safety_checklist_digest_metadata",
        "verification_checklist_digest_metadata",
        "abort_readiness_metadata",
        "rollback_readiness_metadata",
        "lock_lease_readiness_metadata",
        "operator_identity_role_metadata",
        "execution_window_metadata",
        "idempotency_key_metadata",
        "atomicity_boundary_metadata",
        "dry_run_to_live_equivalence_metadata",
        "rollback_rehearsal_metadata",
        "post_execution_audit_metadata",
        "constrained_enable_path_metadata",
        "future_live_execution_gate_metadata",
        "emergency_stop_metadata",
        "post_enable_verification_metadata",
    ],
)
def test_non_noop_metadata_is_required(field: str) -> None:
    payload = load_ready()
    candidate(payload)[field] = {}
    result = evaluate(payload)
    assert result.status == "executor_enablement_blocked"
    assert first_code(result) == f"missing_{field}"


@pytest.mark.parametrize(
    ("claim", "code"),
    [
        ({"executor_enabled": True}, "executor_enablement_claim"),
        ({"executor_invoked": True}, "executor_invocation_claim"),
        ({"executor_activated": True}, "executor_activation_claim"),
        ({"live_commit_executed": True}, "live_commit_execution_claim"),
        ({"permission_to_execute_now": True}, "executor_permission_claim"),
        ({"receipt_envelope_is_live_receipt": True}, "live_receipt_claim"),
        ({"rollback_envelope_applied": True}, "applied_rollback_claim"),
        ({"lock_acquired": True}, "real_lock_acquisition_claim"),
        ({"lockfile_created": True}, "lockfile_creation_claim"),
        ({"real_memory_root_access_claimed": True}, "real_memory_root_access_claim"),
        ({"live_memory_write_claimed": True}, "live_write_claim"),
        ({"live_memory_delete_claimed": True}, "live_delete_claim"),
        ({"live_memory_purge_claimed": True}, "live_purge_claim"),
        ({"live_index_mutation_claimed": True}, "index_mutation_claim"),
        ({"capsule_persistence_claimed": True}, "capsule_persistence_claim"),
        ({"tomb_completion_claimed": True}, "tomb_completion_claim"),
        ({"protection_application_claimed": True}, "protection_application_claim"),
        ({"merge_application_claimed": True}, "merge_application_claim"),
        ({"prompt_assembly_claimed": True}, "prompt_materialization"),
        ({"live_context_retrieval_claimed": True}, "live_context_retrieval"),
        ({"action_execution_claimed": True}, "action_execution"),
        ({"external_disclosure_claimed": True}, "external_disclosure"),
        ({"remote_service_called": True}, "remote_service_call"),
        ({"authority_granted": True}, "authority_smuggling"),
        ({"consent_granted": True}, "consent_smuggling"),
        ({"policy_created": True}, "policy_smuggling"),
        ({"truth_asserted": True}, "truth_smuggling"),
        ({"raw_secret_payload": "secret: no"}, "raw_payload_leakage"),
    ],
)
def test_forbidden_claims_block(claim: dict, code: str) -> None:
    payload = load_ready()
    candidate(payload)["executor_enablement_claims"] = claim
    result = evaluate(payload)
    assert result.status == "executor_enablement_blocked"
    assert first_code(result) == code


def test_scope_mismatch_blocks_and_mixed_diagnostic_warns_when_allowed() -> None:
    payload = load_ready()
    candidate(payload)["operator_scope_keys"] = ["other"]
    result = evaluate(payload)
    assert result.status == "executor_enablement_blocked"
    assert first_code(result) == "scope_mismatch"

    payload = load_ready()
    candidate(payload)["operator_scope_keys"] = ["other"]
    candidate(payload)["candidate_type"] = "mixed_executor_enablement_candidate"
    candidate(payload)["metadata"] = {"diagnostic_warning": True}
    result = evaluate(payload).to_dict()
    assert result["status"] == "executor_enablement_ready_with_warnings"
    assert any(f["code"] == "scope_mismatch_diagnostic" for f in result["report"]["findings"])


def test_noop_behavior_is_deterministic_and_non_mutating() -> None:
    payload = json.loads(NOOP_FIXTURE.read_text())
    before = copy.deepcopy(payload)
    one = evaluate(payload).to_dict()
    two = evaluate(copy.deepcopy(payload)).to_dict()
    assert one == two
    assert payload == before
    assert one["status"] == "executor_enablement_noop"
    assert one["packet"]["records"][0]["executor_enablement_decision"] == "executor_enablement_noop"
    assert one["packet"]["records"][0]["real_executor_enablement_enabled"] is False


def test_evaluate_mode_writes_no_files_and_does_not_touch_memory_roots(tmp_path: Path) -> None:
    payload = load_ready()
    marker = tmp_path / "memory-root-marker"
    before = set(tmp_path.iterdir())
    result = evaluate(payload)
    after = set(tmp_path.iterdir())
    assert result.status == "executor_enablement_ready"
    assert before == after
    assert not marker.exists()
