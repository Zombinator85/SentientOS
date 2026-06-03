from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.real_executor_runtime_gate import (
    EVIDENCE_MATCH_FIELDS,
    INVARIANTS,
    NON_NOOP_METADATA_FIELDS,
    evaluate_real_executor_runtime_gate,
)

FIXTURE_ROOT = Path("tests/fixtures/real_executor_runtime_gate")
READY_FIXTURE = FIXTURE_ROOT / "ready_runtime_gate_candidate.json"
NOOP_FIXTURE = FIXTURE_ROOT / "noop_runtime_gate_candidate.json"
MIXED_FIXTURE = FIXTURE_ROOT / "mixed_runtime_gate_candidate.json"


def load_ready() -> dict:
    return json.loads(READY_FIXTURE.read_text(encoding="utf-8"))


def candidate(payload: dict) -> dict:
    return payload["runtime_gate_candidates"][0]


def assert_blocked(payload: dict, code: str) -> None:
    result = evaluate_real_executor_runtime_gate(payload)
    assert result.status == "runtime_gate_blocked"
    assert result.packet is None
    assert any(f.code == code for f in result.report.findings), result.to_dict()


def test_ready_runtime_gate_packet_is_metadata_only_and_default_deny() -> None:
    result = evaluate_real_executor_runtime_gate(load_ready())
    assert result.status == "runtime_gate_ready"
    assert result.packet is not None
    record = result.packet.records[0]
    assert record.runtime_gate_decision == "runtime_gate_ready_for_later_guarded_executor_path"
    for key, expected in INVARIANTS.items():
        assert result.packet.to_dict()[key] is expected
    assert record.real_executor_enabled is False
    assert record.real_executor_runtime_enablement_enabled is False
    assert record.real_executor_enablement_enabled is False
    assert record.real_executor_invocation_enabled is False
    assert record.real_executor_activation_enabled is False
    assert record.real_lock_acquisition_enabled is False
    assert record.lockfile_created is False
    assert record.runtime_flags_flipped is False
    assert record.live_commit_executed is False
    assert record.runtime_flag_target_state_is_active_runtime_state is False
    assert record.guarded_executor_path_prerequisites_are_executor_invocation is False
    assert record.future_guarded_executor_path_required is True
    assert record.future_real_live_memory_commit_execution_required is True
    assert record.future_post_execution_audit_required is True
    assert record.runtime_gate_readiness_records[0].metadata_only is True
    assert record.runtime_enable_confirmation_records[0].runtime_enabled is False
    assert record.runtime_flag_confirmation_records[0].active_runtime_state is False
    assert record.guarded_executor_path_prerequisite_records[0].executor_invoked is False
    assert record.emergency_stop_confirmation_records[0].permission_granted is False
    assert record.rollback_readiness_records[0].rollback_applied is False
    assert record.verification_readiness_records[0].executed is False
    assert record.audit_readiness_records[0].authoritative is False


def test_missing_or_invalid_runtime_enablement_packet_blocks() -> None:
    payload = load_ready()
    payload.pop("runtime_enablement_packet")
    assert_blocked(payload, "missing_runtime_enablement_packet")
    payload = load_ready()
    payload["runtime_enablement_packet"] = {"records": []}
    assert_blocked(payload, "invalid_runtime_enablement_packet")


def test_missing_or_invalid_runtime_gate_candidate_blocks() -> None:
    payload = load_ready()
    payload["runtime_gate_candidates"] = []
    assert_blocked(payload, "missing_runtime_gate_candidate")
    payload = load_ready()
    candidate(payload)["candidate_type"] = "bad"
    assert_blocked(payload, "invalid_runtime_gate_candidate")


def test_runtime_enablement_packet_not_ready_blocks_by_default() -> None:
    payload = load_ready()
    packet = payload["runtime_enablement_packet"]
    packet["records"][0]["runtime_enablement_packet_decision"] = "runtime_enablement_packet_rejected"
    candidate(payload)["claimed_runtime_enablement_packet_decision"] = "runtime_enablement_packet_rejected"
    assert_blocked(payload, "runtime_enablement_packet_not_ready")


@pytest.mark.parametrize(("label", "digest_field", "record_digest_field", "decision_field"), EVIDENCE_MATCH_FIELDS)
def test_upstream_digest_mismatches_block(label: str, digest_field: str, record_digest_field: str, decision_field: str) -> None:
    payload = load_ready()
    candidate(payload)[digest_field] = "sha256:mismatch"
    assert_blocked(payload, f"{label}_digest_mismatch")


@pytest.mark.parametrize(("label", "digest_field", "record_digest_field", "decision_field"), EVIDENCE_MATCH_FIELDS)
def test_upstream_decision_mismatches_block(label: str, digest_field: str, record_digest_field: str, decision_field: str) -> None:
    payload = load_ready()
    candidate(payload)[decision_field] = "wrong_decision"
    assert_blocked(payload, f"{label}_decision_mismatch")


@pytest.mark.parametrize("field", NON_NOOP_METADATA_FIELDS)
def test_missing_required_non_noop_metadata_blocks(field: str) -> None:
    payload = load_ready()
    candidate(payload).pop(field, None)
    assert_blocked(payload, f"missing_{field}")


def test_noop_behavior_is_deterministic_and_non_mutating() -> None:
    payload = json.loads(NOOP_FIXTURE.read_text(encoding="utf-8"))
    before = copy.deepcopy(payload)
    result = evaluate_real_executor_runtime_gate(payload)
    assert result.status == "runtime_gate_noop"
    assert result.packet is not None
    assert result.packet.records[0].runtime_gate_decision == "runtime_gate_noop"
    assert result.packet.records[0].real_executor_enabled is False
    assert evaluate_real_executor_runtime_gate(payload).to_dict() == result.to_dict()
    assert payload == before


def test_mixed_diagnostics_warn_only_when_policy_allows() -> None:
    payload = json.loads(MIXED_FIXTURE.read_text(encoding="utf-8"))
    result = evaluate_real_executor_runtime_gate(payload)
    assert result.status == "runtime_gate_ready_with_warnings"
    assert any(f.code == "mixed_scope_diagnostic" for f in result.report.findings)


def test_scope_mismatch_blocks_for_non_mixed_candidate() -> None:
    payload = load_ready()
    candidate(payload)["operator_scope_keys"] = ["other"]
    assert_blocked(payload, "scope_mismatch")


FORBIDDEN_CLAIMS = [
    ("runtime_enablement_claimed", "runtime_enablement_claim"),
    ("runtime_flags_flipped", "runtime_flag_flipping_claim"),
    ("runtime_flag_target_state_active", "runtime_flag_active_state_claim"),
    ("guarded_executor_path_invoked", "guarded_executor_invocation_claim"),
    ("executor_enabled", "executor_enablement_claim"),
    ("executor_invoked", "executor_invocation_claim"),
    ("executor_activated", "executor_activation_claim"),
    ("live_commit_executed", "live_execution_claim"),
    ("permission_to_execute_now", "executor_permission_claim"),
    ("operation_bundle_executed", "operation_bundle_execution_claim"),
    ("receipt_envelope_is_live_receipt", "live_receipt_claim"),
    ("rollback_readiness_applied", "applied_rollback_claim"),
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
    ("external_service_called", "external_service_call"),
    ("lockfile_creation_claimed", "lockfile_creation_claim"),
    ("real_lock_acquisition_claimed", "real_lock_acquisition_claim"),
    ("real_memory_root_access_claimed", "real_memory_root_access_claim"),
    ("authority_granted", "authority_smuggling"),
    ("consent_granted", "consent_smuggling"),
    ("policy_created", "policy_smuggling"),
    ("truth_asserted", "truth_smuggling"),
    ("raw_payload_included", "raw_payload_leakage"),
    ("private_payload_included", "raw_payload_leakage"),
    ("media_payload_included", "raw_payload_leakage"),
    ("secret_payload_included", "raw_payload_leakage"),
]


@pytest.mark.parametrize(("claim", "code"), FORBIDDEN_CLAIMS)
def test_forbidden_claims_block(claim: str, code: str) -> None:
    payload = load_ready()
    candidate(payload)["runtime_gate_claims"] = {claim: True}
    assert_blocked(payload, code)
