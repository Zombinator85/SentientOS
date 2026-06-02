from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.future_live_memory_commit_execution_gate import (
    FAIL_STATUSES,
    INVARIANTS,
    NON_NOOP_METADATA_FIELDS,
    evaluate_future_live_memory_commit_execution_gate,
    validate_policy,
)

FIXTURE = Path("tests/fixtures/future_live_memory_commit_execution_gate/ready_future_execution_gate_candidate.json")
NOOP_FIXTURE = Path("tests/fixtures/future_live_memory_commit_execution_gate/noop_future_execution_gate_candidate.json")
MIXED_FIXTURE = Path("tests/fixtures/future_live_memory_commit_execution_gate/mixed_future_execution_gate_candidate.json")


def load_ready() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def assert_blocked(payload: dict, code: str) -> None:
    result = evaluate_future_live_memory_commit_execution_gate(payload)
    assert result.status in FAIL_STATUSES
    assert result.packet is None
    assert result.report.findings[0].code == code


def test_validate_policy_is_default_deny_and_non_authoritative() -> None:
    validation = validate_policy()
    assert validation["status"] == "valid"
    assert validation["invariants"] == INVARIANTS
    assert validation["policy"]["real_executor_enabled"] is False
    assert validation["policy"]["future_live_commit_execution_packet_required"] is True


def test_ready_packet_is_metadata_only_and_keeps_executor_disabled() -> None:
    result = evaluate_future_live_memory_commit_execution_gate(load_ready())
    assert result.status == "future_execution_gate_ready"
    assert result.packet is not None
    packet = result.packet
    assert packet.future_execution_gate_is_not_live_commit_execution is True
    assert packet.future_execution_gate_is_not_executor_enablement is True
    assert packet.future_execution_gate_is_not_executor_invocation is True
    assert packet.future_execution_gate_is_not_executor_activation is True
    assert packet.future_execution_gate_is_not_lock_acquisition is True
    assert packet.future_execution_gate_is_not_lockfile_creation is True
    assert packet.future_execution_gate_is_not_memory_write is True
    assert packet.prompt_materialization_enabled is False
    assert packet.live_context_retrieval_enabled is False
    assert packet.action_execution_enabled is False
    assert packet.external_disclosure_enabled is False
    assert packet.future_live_commit_execution_packet_required is True
    record = packet.records[0]
    assert record.future_execution_gate_decision == "future_execution_gate_ready_for_later_live_commit_execution_packet"
    assert record.constrained_enablement_path_decision == "constrained_enable_path_ready_for_future_live_execution_gate"
    assert record.executor_enablement_gate_decision == "executor_enablement_ready_for_later_constrained_enable_path"
    assert record.real_executor_enabled is False
    assert record.real_executor_enablement_enabled is False
    assert record.executor_invoked is False
    assert record.executor_activated is False
    assert record.lock_acquired is False
    assert record.lockfile_created is False
    for records in (
        record.execution_readiness_records,
        record.constrained_path_confirmation_records,
        record.operator_execution_acknowledgement_records,
        record.emergency_stop_confirmation_records,
        record.verification_readiness_records,
        record.rollback_readiness_records,
        record.audit_readiness_records,
    ):
        assert records[0]["metadata_only"] is True
        assert records[0]["executor_enabled"] is False
        assert records[0]["real_memory_mutation_performed"] is False


def test_output_is_deterministic() -> None:
    payload = load_ready()
    first = evaluate_future_live_memory_commit_execution_gate(payload).to_dict()
    second = evaluate_future_live_memory_commit_execution_gate(payload).to_dict()
    assert first == second


def test_missing_or_invalid_constrained_enablement_path_packet_blocks() -> None:
    payload = load_ready()
    payload.pop("constrained_executor_enablement_path_packet")
    assert_blocked(payload, "missing_constrained_enablement_path_packet")
    payload = load_ready()
    payload["constrained_executor_enablement_path_packet"] = {"records": []}
    assert_blocked(payload, "invalid_constrained_enablement_path_packet")


def test_missing_or_invalid_candidate_blocks() -> None:
    payload = load_ready()
    payload["future_execution_gate_candidates"] = []
    assert_blocked(payload, "missing_future_execution_gate_candidate")
    payload = load_ready()
    payload["future_execution_gate_candidates"] = [{"candidate_id": "bad", "candidate_type": "unknown"}]
    assert_blocked(payload, "invalid_future_execution_gate_candidate")


def test_constrained_enablement_path_not_ready_blocks_by_default() -> None:
    payload = load_ready()
    payload["constrained_executor_enablement_path_packet"]["records"][0]["constrained_enable_path_decision"] = "constrained_enable_path_rejected"
    payload["future_execution_gate_candidates"][0]["claimed_constrained_enablement_path_decision"] = "constrained_enable_path_rejected"
    assert_blocked(payload, "constrained_enablement_path_not_ready")


UPSTREAM_MISMATCH_CASES = [
    ("constrained_enablement_path_packet", "claimed_constrained_enablement_path_packet_digest", "claimed_constrained_enablement_path_decision"),
    ("executor_enablement_gate", "claimed_executor_enablement_gate_digest", "claimed_executor_enablement_gate_decision"),
    ("executor_skeleton", "claimed_executor_skeleton_digest", "claimed_executor_skeleton_decision"),
    ("invocation_harness", "claimed_invocation_harness_digest", "claimed_invocation_harness_decision"),
    ("activation_record", "claimed_activation_record_digest", "claimed_activation_record_decision"),
    ("preflight_packet", "claimed_preflight_packet_digest", "claimed_preflight_packet_decision"),
    ("lock_lease_gate", "claimed_lock_lease_gate_digest", "claimed_lock_lease_gate_decision"),
    ("executor_plan_packet", "claimed_executor_plan_packet_digest", "claimed_executor_plan_decision"),
    ("runtime_execution_gate", "claimed_runtime_execution_gate_digest", "claimed_runtime_execution_gate_decision"),
    ("readiness_envelope", "claimed_readiness_envelope_digest", "claimed_readiness_envelope_decision"),
    ("final_review", "claimed_final_review_digest", "claimed_final_review_decision"),
    ("real_root_admission", "claimed_real_root_admission_digest", "claimed_real_root_admission_decision"),
    ("sandbox_commit", "claimed_sandbox_commit_digest", "claimed_sandbox_commit_decision"),
]


def test_upstream_digest_mismatches_block() -> None:
    for label, digest_field, _decision_field in UPSTREAM_MISMATCH_CASES:
        payload = load_ready()
        payload["future_execution_gate_candidates"][0][digest_field] = "sha256:mismatch"
        assert_blocked(payload, f"{label}_digest_mismatch")


def test_upstream_decision_mismatches_block() -> None:
    for label, _digest_field, decision_field in UPSTREAM_MISMATCH_CASES:
        payload = load_ready()
        payload["future_execution_gate_candidates"][0][decision_field] = "wrong_decision"
        assert_blocked(payload, f"{label}_decision_mismatch")


def test_missing_required_non_noop_metadata_blocks() -> None:
    for field in NON_NOOP_METADATA_FIELDS:
        payload = load_ready()
        payload["future_execution_gate_candidates"][0].pop(field, None)
        assert_blocked(payload, f"missing_{field}")


def test_noop_behavior_is_deterministic_and_non_mutating() -> None:
    payload = json.loads(NOOP_FIXTURE.read_text(encoding="utf-8"))
    result = evaluate_future_live_memory_commit_execution_gate(payload)
    assert result.status == "future_execution_gate_noop"
    assert result.packet is not None
    assert result.packet.records[0].future_execution_gate_decision == "future_execution_gate_noop"
    assert result.packet.records[0].real_executor_enabled is False
    assert evaluate_future_live_memory_commit_execution_gate(payload).to_dict() == result.to_dict()


def test_mixed_diagnostics_warn_only_when_policy_allows() -> None:
    payload = json.loads(MIXED_FIXTURE.read_text(encoding="utf-8"))
    result = evaluate_future_live_memory_commit_execution_gate(payload)
    assert result.status == "future_execution_gate_ready_with_warnings"
    assert any(f.code == "mixed_scope_diagnostic" for f in result.report.findings)


def test_scope_mismatch_blocks_for_non_mixed_candidate() -> None:
    payload = load_ready()
    payload["future_execution_gate_candidates"][0]["operator_scope_keys"] = ["other"]
    assert_blocked(payload, "scope_mismatch")


FORBIDDEN_CLAIMS = [
    ("executor_enabled", "executor_enablement_claim"),
    ("executor_invoked", "executor_invocation_claim"),
    ("executor_activated", "executor_activation_claim"),
    ("live_commit_executed", "live_commit_execution_claim"),
    ("permission_to_execute_now", "executor_permission_claim"),
    ("receipt_envelope_is_live_receipt", "live_receipt_claim"),
    ("rollback_envelope_applied", "applied_rollback_claim"),
    ("live_memory_write_claimed", "live_write_claim"),
    ("live_memory_delete_claimed", "live_delete_claim"),
    ("live_memory_purge_claimed", "live_purge_claim"),
    ("live_index_mutation_claimed", "index_mutation_claim"),
    ("capsule_persistence_claimed", "capsule_persistence_claim"),
    ("tomb_completion_claimed", "tomb_completion_claim"),
    ("protection_application_claimed", "protection_application_claim"),
    ("merge_application_claimed", "merge_application_claim"),
    ("prompt_assembly_claimed", "prompt_materialization"),
    ("live_context_retrieval_claimed", "live_context_retrieval"),
    ("action_execution_claimed", "action_execution"),
    ("external_disclosure_claimed", "external_disclosure"),
    ("remote_service_called", "remote_service_call"),
    ("authority_granted", "authority_smuggling"),
    ("consent_granted", "consent_smuggling"),
    ("policy_created", "policy_smuggling"),
    ("truth_asserted", "truth_smuggling"),
    ("lockfile_created", "lockfile_creation_claim"),
    ("real_lock_acquired", "real_lock_acquisition_claim"),
    ("real_memory_root_access_claimed", "real_memory_root_access_claim"),
]


def test_forbidden_claims_block() -> None:
    for claim, code in FORBIDDEN_CLAIMS:
        payload = load_ready()
        payload["future_execution_gate_candidates"][0]["future_execution_gate_claims"] = {claim: True}
        assert_blocked(payload, code)


def test_raw_payload_leakage_blocks() -> None:
    payload = load_ready()
    payload["future_execution_gate_candidates"][0]["raw_private_payload"] = "secret: do not include"
    assert_blocked(payload, "raw_payload_leakage")
