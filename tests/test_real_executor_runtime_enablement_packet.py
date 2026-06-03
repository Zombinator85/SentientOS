from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sentientos.real_executor_runtime_enablement_packet import (
    EVIDENCE_MATCH_FIELDS,
    INVARIANTS,
    NON_NOOP_METADATA_FIELDS,
    build_default_policy,
    evaluate_real_executor_runtime_enablement_packet,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURE = Path("tests/fixtures/real_executor_runtime_enablement_packet/ready_runtime_enablement_candidate.json")
NOOP_FIXTURE = Path("tests/fixtures/real_executor_runtime_enablement_packet/noop_runtime_enablement_candidate.json")
MIXED_FIXTURE = Path("tests/fixtures/real_executor_runtime_enablement_packet/mixed_runtime_enablement_candidate.json")


def load_ready() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def candidate(payload: dict[str, object]) -> dict[str, object]:
    return payload["runtime_enablement_candidates"][0]  # type: ignore[index,return-value]


def assert_blocked(payload: dict[str, object], code: str) -> None:
    result = evaluate_real_executor_runtime_enablement_packet(payload)
    assert result.status == "runtime_enablement_packet_blocked"
    assert any(f.code == code for f in result.report.findings), result.to_dict()
    assert result.packet is None


def test_policy_defaults_are_metadata_only_and_default_deny() -> None:
    policy = build_default_policy()
    assert policy.default_deny is True
    assert policy.metadata_only is True
    assert policy.real_executor_enabled is False
    assert policy.real_executor_runtime_enablement_enabled is False
    assert validate_policy()["status"] == "valid"


def test_ready_packet_is_deterministic_metadata_only_and_disabled() -> None:
    payload = load_ready()
    first = evaluate_real_executor_runtime_enablement_packet(payload)
    second = evaluate_real_executor_runtime_enablement_packet(payload)
    assert first.to_dict() == second.to_dict()
    assert first.status == "runtime_enablement_packet_ready"
    assert first.packet is not None
    packet = first.packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert packet[key] is expected
    record = first.packet.records[0]
    assert record.runtime_enablement_packet_decision == "runtime_enablement_packet_ready_for_later_real_executor_runtime_gate"
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
    assert record.runtime_enable_readiness_records[0].metadata_only is True
    assert record.disabled_to_enabled_transition_requirement_records[0].runtime_enabled is False
    assert record.runtime_flag_precondition_records[0].runtime_flag_flipped is False
    assert record.runtime_flag_target_state_records[0].active_runtime_state is False
    assert record.operator_runtime_acknowledgement_records[0].permission_granted is False
    assert record.emergency_stop_confirmation_records[0].executed is False
    assert record.rollback_readiness_records[0].rollback_applied is False
    assert record.verification_readiness_records[0].executed is False
    assert record.audit_readiness_records[0].authoritative is False
    assert record.future_real_executor_runtime_gate_required is True
    assert record.future_real_live_memory_commit_execution_required is True
    assert record.future_post_execution_audit_required is True


def test_missing_or_invalid_live_commit_execution_packet_blocks() -> None:
    payload = load_ready()
    payload.pop("live_commit_execution_packet")
    assert_blocked(payload, "missing_live_commit_execution_packet")
    payload = load_ready()
    payload["live_commit_execution_packet"] = {"records": []}
    assert_blocked(payload, "invalid_live_commit_execution_packet")


def test_missing_or_invalid_runtime_enablement_candidate_blocks() -> None:
    payload = load_ready()
    payload["runtime_enablement_candidates"] = []
    assert_blocked(payload, "missing_runtime_enablement_candidate")
    payload = load_ready()
    candidate(payload)["candidate_type"] = "bad"
    assert_blocked(payload, "invalid_runtime_enablement_candidate")


def test_live_commit_execution_packet_not_ready_blocks_by_default() -> None:
    payload = load_ready()
    packet = payload["live_commit_execution_packet"]  # type: ignore[assignment]
    packet["records"][0]["live_commit_execution_packet_decision"] = "live_commit_execution_packet_rejected"  # type: ignore[index]
    candidate(payload)["claimed_live_commit_execution_packet_decision"] = "live_commit_execution_packet_rejected"
    assert_blocked(payload, "live_commit_execution_packet_not_ready")


def test_upstream_digest_mismatches_block() -> None:
    for label, digest_field, _record_digest_field, _decision_field in EVIDENCE_MATCH_FIELDS:
        payload = load_ready()
        candidate(payload)[digest_field] = "sha256:mismatch"
        assert_blocked(payload, f"{label}_digest_mismatch")


def test_upstream_decision_mismatches_block() -> None:
    for label, _digest_field, _record_digest_field, decision_field in EVIDENCE_MATCH_FIELDS:
        payload = load_ready()
        candidate(payload)[decision_field] = "wrong_decision"
        assert_blocked(payload, f"{label}_decision_mismatch")


def test_missing_required_non_noop_metadata_blocks() -> None:
    for field in NON_NOOP_METADATA_FIELDS:
        payload = load_ready()
        candidate(payload).pop(field, None)
        assert_blocked(payload, f"missing_{field}")


def test_noop_behavior_is_deterministic_and_non_mutating() -> None:
    payload = json.loads(NOOP_FIXTURE.read_text(encoding="utf-8"))
    result = evaluate_real_executor_runtime_enablement_packet(payload)
    assert result.status == "runtime_enablement_packet_noop"
    assert result.packet is not None
    assert result.packet.records[0].runtime_enablement_packet_decision == "runtime_enablement_packet_noop"
    assert result.packet.records[0].real_executor_enabled is False
    assert evaluate_real_executor_runtime_enablement_packet(payload).to_dict() == result.to_dict()


def test_mixed_diagnostics_warn_only_when_policy_allows() -> None:
    payload = json.loads(MIXED_FIXTURE.read_text(encoding="utf-8"))
    result = evaluate_real_executor_runtime_enablement_packet(payload)
    assert result.status == "runtime_enablement_packet_ready_with_warnings"
    assert any(f.code == "mixed_scope_diagnostic" for f in result.report.findings)


def test_scope_mismatch_blocks_for_non_mixed_candidate() -> None:
    payload = load_ready()
    candidate(payload)["operator_scope_keys"] = ["other"]
    assert_blocked(payload, "scope_mismatch")


FORBIDDEN_CLAIMS = [
    ("runtime_enablement_claimed", "runtime_enablement_claim"),
    ("runtime_flags_flipped", "runtime_flag_flipping_claim"),
    ("runtime_flag_target_state_active", "runtime_flag_active_state_claim"),
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
    candidate(payload)["runtime_enablement_claims"] = {claim: True}
    assert_blocked(payload, code)


def test_raw_private_payload_leakage_blocks() -> None:
    payload = load_ready()
    candidate(payload)["runtime_enablement_claims"] = {"secret_payload_included": True}
    assert_blocked(payload, "raw_payload_leakage")


def test_evaluate_does_not_mutate_input() -> None:
    payload = load_ready()
    before = copy.deepcopy(payload)
    result = evaluate_real_executor_runtime_enablement_packet(payload)
    assert result.status == "runtime_enablement_packet_ready"
    assert payload == before
