from __future__ import annotations

import copy
import json
from pathlib import Path

from sentientos.live_executor_lock_lease_gate import (
    INVARIANTS,
    evaluate_live_executor_lock_lease_gate,
    validate_policy,
)

FIXTURE_ROOT = Path("tests/fixtures/live_executor_lock_lease_gate")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _base() -> dict:
    return _fixture("valid_ai_capsule_lock_lease_candidate.json")


def _candidate(payload: dict) -> dict:
    return payload["lock_lease_candidates"][0]


def _codes(result) -> set[str]:
    return {f.code for f in result.report.findings}


def test_valid_candidate_produces_metadata_only_packet() -> None:
    result = evaluate_live_executor_lock_lease_gate(_base())
    assert result.status == "lock_lease_ready"
    packet = result.packet
    assert packet is not None
    data = packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert data[key] is expected
    record = packet.records[0]
    assert record.lock_lease_decision == "lock_lease_ready_for_later_live_executor"
    assert record.lock_acquired is False
    assert record.lockfile_created is False
    assert record.live_commit_executed is False
    for collection_name in (
        "lock_readiness_records", "lease_readiness_records", "contention_records", "timeout_records",
        "stale_lease_records", "abort_readiness_records", "rollback_readiness_records", "audit_readiness_records",
    ):
        records = getattr(record, collection_name)
        assert records and records[0]["metadata_only"] is True
        assert records[0]["lock_acquired"] is False
        assert records[0]["lockfile_created"] is False
        assert records[0]["live_commit_executed"] is False


def test_missing_or_invalid_inputs_block() -> None:
    assert evaluate_live_executor_lock_lease_gate({}).status == "lock_lease_blocked"
    payload = _base(); payload.pop("lock_lease_candidates")
    result = evaluate_live_executor_lock_lease_gate(payload)
    assert result.status == "lock_lease_blocked"
    assert "missing_lock_lease_candidate" in _codes(result)
    payload = _base(); _candidate(payload)["candidate_type"] = "unknown"
    assert "invalid_lock_lease_candidate" in _codes(evaluate_live_executor_lock_lease_gate(payload))
    payload = _base(); payload["real_live_memory_commit_executor_plan_packet"] = {"records": []}
    assert "invalid_executor_plan_packet" in _codes(evaluate_live_executor_lock_lease_gate(payload))


def test_executor_plan_not_ready_blocks_by_default() -> None:
    payload = _base()
    payload["real_live_memory_commit_executor_plan_packet"]["records"][0]["executor_plan_decision"] = "executor_plan_blocked"
    _candidate(payload)["claimed_executor_plan_decision"] = "executor_plan_blocked"
    assert "executor_plan_not_ready" in _codes(evaluate_live_executor_lock_lease_gate(payload))


def test_evidence_mismatch_blockers() -> None:
    cases = [
        ("claimed_executor_plan_packet_digest", "sha256:bad", "executor_plan_digest_mismatch"),
        ("claimed_executor_plan_decision", "executor_plan_blocked", "executor_plan_decision_mismatch"),
        ("claimed_runtime_execution_gate_digest", "sha256:bad", "runtime_execution_gate_digest_mismatch"),
        ("claimed_runtime_execution_gate_decision", "bad", "runtime_execution_gate_decision_mismatch"),
        ("claimed_readiness_envelope_digest", "sha256:bad", "readiness_envelope_digest_mismatch"),
        ("claimed_readiness_envelope_decision", "bad", "readiness_envelope_decision_mismatch"),
        ("claimed_final_review_digest", "sha256:bad", "final_review_digest_mismatch"),
        ("claimed_final_review_decision", "bad", "final_review_decision_mismatch"),
        ("claimed_real_root_admission_digest", "sha256:bad", "real_root_admission_digest_mismatch"),
        ("claimed_real_root_admission_decision", "bad", "real_root_admission_decision_mismatch"),
        ("claimed_sandbox_commit_digest", "sha256:bad", "sandbox_commit_digest_mismatch"),
        ("claimed_sandbox_commit_decision", "bad", "sandbox_commit_decision_mismatch"),
    ]
    for key, value, code in cases:
        payload = _base(); _candidate(payload)[key] = value
        assert code in _codes(evaluate_live_executor_lock_lease_gate(payload)), key


def test_required_non_noop_metadata_blocks() -> None:
    keys = {
        "operation_list_digest_metadata": "missing_operation_list_digest_metadata",
        "lock_lease_expectation_metadata": "missing_lock_lease_expectation_metadata",
        "lease_duration_metadata": "missing_lease_duration_metadata",
        "lock_owner_metadata": "missing_lock_owner_metadata",
        "operator_identity_role_metadata": "missing_operator_identity_role_metadata",
        "execution_window_metadata": "missing_execution_window_metadata",
        "idempotency_key_metadata": "missing_idempotency_key_metadata",
        "atomicity_boundary_metadata": "missing_atomicity_boundary_metadata",
        "contention_policy_metadata": "missing_contention_policy_metadata",
        "stale_lease_policy_metadata": "missing_stale_lease_policy_metadata",
        "timeout_policy_metadata": "missing_timeout_policy_metadata",
        "abort_condition_metadata": "missing_abort_condition_metadata",
        "rollback_target_metadata": "missing_rollback_target_metadata",
        "post_execution_audit_metadata": "missing_post_execution_audit_metadata",
    }
    for key, code in keys.items():
        payload = _base(); _candidate(payload)[key] = {}
        assert code in _codes(evaluate_live_executor_lock_lease_gate(payload)), key


def test_forbidden_claims_block() -> None:
    claims = {
        "lock_acquired": "real_lock_acquisition_claim",
        "lockfile_created": "lockfile_creation_claim",
        "live_memory_write_claimed": "live_write_claim",
        "live_memory_delete_claimed": "live_delete_claim",
        "live_memory_purge_claimed": "live_purge_claim",
        "live_index_mutation_claimed": "index_mutation_claim",
        "capsule_persistence_claimed": "capsule_persistence_claim",
        "tomb_completion_claimed": "tomb_completion_claim",
        "protection_application_claimed": "protection_application_claim",
        "merge_application_claimed": "merge_application_claim",
        "real_memory_root_access_claimed": "real_memory_root_access_claim",
        "prompt_assembly_claimed": "prompt_materialization",
        "live_context_retrieval_claimed": "live_context_retrieval",
        "action_execution_claimed": "action_execution",
        "external_disclosure_claimed": "external_disclosure",
        "authority_claimed": "authority_smuggling",
        "consent_claimed": "consent_smuggling",
        "policy_claimed": "policy_smuggling",
        "truth_claimed": "truth_smuggling",
        "permission_to_execute_now": "executor_permission_claim",
    }
    for claim, code in claims.items():
        payload = _base(); _candidate(payload)["lock_lease_claims"] = {claim: True}
        assert code in _codes(evaluate_live_executor_lock_lease_gate(payload)), claim
    payload = _base(); _candidate(payload)["private_payload"] = "secret: no"
    assert "raw_payload_leak" in _codes(evaluate_live_executor_lock_lease_gate(payload))


def test_scope_noop_mixed_and_determinism() -> None:
    payload = _base(); _candidate(payload)["operator_scope_keys"] = ["different"]
    assert "scope_mismatch" in _codes(evaluate_live_executor_lock_lease_gate(payload))
    payload = _base(); _candidate(payload)["candidate_type"] = "mixed_lock_lease_candidate"; _candidate(payload)["operator_scope_keys"] = ["different"]; _candidate(payload)["metadata"] = {"diagnostic_warning": True}
    assert evaluate_live_executor_lock_lease_gate(payload).status == "lock_lease_ready_with_warnings"
    payload["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    assert "scope_mismatch" in _codes(evaluate_live_executor_lock_lease_gate(payload))
    noop = _fixture("noop_lock_lease_candidate.json")
    assert evaluate_live_executor_lock_lease_gate(noop).status == "lock_lease_noop"
    assert evaluate_live_executor_lock_lease_gate(noop).to_dict() == evaluate_live_executor_lock_lease_gate(copy.deepcopy(noop)).to_dict()
    assert evaluate_live_executor_lock_lease_gate(_base()).to_dict() == evaluate_live_executor_lock_lease_gate(copy.deepcopy(_base())).to_dict()


def test_policy_validation_keeps_live_surfaces_disabled() -> None:
    assert validate_policy()["status"] == "valid"
    payload = _base(); payload["policy"] = {"real_lock_acquisition_enabled": True}
    assert "real_lock_acquisition_enabled" in _codes(evaluate_live_executor_lock_lease_gate(payload))
    payload = _base(); payload["policy"] = {"lockfile_creation_enabled": True}
    assert "lockfile_creation_enabled" in _codes(evaluate_live_executor_lock_lease_gate(payload))
