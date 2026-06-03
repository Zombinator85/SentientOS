from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sentientos.guarded_executor_path_packet import (
    EVIDENCE_MATCH_FIELDS,
    INVARIANTS,
    NON_NOOP_METADATA_FIELDS,
    evaluate_guarded_executor_path_packet,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURE_ROOT = Path("tests/fixtures/guarded_executor_path_packet")
READY_FIXTURE = FIXTURE_ROOT / "ready_guarded_executor_path_candidate.json"
NOOP_FIXTURE = FIXTURE_ROOT / "noop_guarded_executor_path_candidate.json"
MIXED_FIXTURE = FIXTURE_ROOT / "mixed_guarded_executor_path_candidate.json"


def load_ready() -> dict[str, object]:
    return json.loads(READY_FIXTURE.read_text(encoding="utf-8"))


def candidate(payload: dict[str, object]) -> dict[str, object]:
    return payload["guarded_executor_path_candidates"][0]  # type: ignore[index,return-value]


def assert_blocked(payload: dict[str, object], code: str) -> None:
    result = evaluate_guarded_executor_path_packet(payload)
    assert result.status == "guarded_executor_path_blocked"
    assert result.packet is None
    assert any(f.code == code for f in result.report.findings)


def test_ready_packet_is_metadata_only_and_disabled() -> None:
    result = evaluate_guarded_executor_path_packet(load_ready())
    assert result.status == "guarded_executor_path_ready"
    assert result.packet is not None
    packet = result.packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert packet[key] is expected
    record = result.packet.records[0]
    assert record.guarded_executor_path_decision == "guarded_executor_path_ready_for_later_guarded_invocation_packet"
    assert record.runtime_gate_decision == "runtime_gate_ready_for_later_guarded_executor_path"
    assert record.real_executor_enabled is False
    assert record.real_executor_runtime_enablement_enabled is False
    assert record.real_executor_enablement_enabled is False
    assert record.real_executor_invocation_enabled is False
    assert record.real_executor_activation_enabled is False
    assert record.real_lock_acquisition_enabled is False
    assert record.lockfile_created is False
    assert record.guarded_executor_prerequisites_are_executor_invocation is False
    assert record.invocation_hold_points_are_live_invocation is False
    assert record.future_guarded_invocation_packet_required is True
    assert record.future_real_live_memory_commit_execution_required is True
    assert record.future_post_execution_audit_required is True
    for records in (
        record.guarded_path_readiness_records,
        record.guarded_executor_prerequisite_records,
        record.invocation_hold_point_records,
        record.runtime_guard_confirmation_records,
        record.emergency_stop_confirmation_records,
        record.rollback_readiness_records,
        record.verification_readiness_records,
        record.audit_readiness_records,
    ):
        assert records[0].metadata_only is True
        assert records[0].authoritative is False
        assert records[0].executed is False
        assert records[0].permission_granted is False
        assert records[0].runtime_enabled is False
        assert records[0].runtime_flag_flipped is False
        assert records[0].executor_invoked is False
        assert records[0].live_receipt is False
        assert records[0].rollback_applied is False


def test_missing_or_invalid_runtime_gate_packet_blocks() -> None:
    payload = load_ready(); payload.pop("runtime_gate_packet")
    assert_blocked(payload, "missing_runtime_gate_packet")
    payload = load_ready(); payload["runtime_gate_packet"] = {"records": []}
    assert_blocked(payload, "invalid_runtime_gate_packet")


def test_missing_or_invalid_guarded_executor_path_candidate_blocks() -> None:
    payload = load_ready(); payload["guarded_executor_path_candidates"] = []
    assert_blocked(payload, "missing_guarded_executor_path_candidate")
    payload = load_ready(); candidate(payload)["candidate_type"] = "bad"
    assert_blocked(payload, "invalid_guarded_executor_path_candidate")


def test_runtime_gate_not_ready_blocks_by_default() -> None:
    payload = load_ready()
    packet = payload["runtime_gate_packet"]  # type: ignore[assignment]
    packet["records"][0]["runtime_gate_decision"] = "runtime_gate_rejected"  # type: ignore[index]
    candidate(payload)["claimed_runtime_gate_decision"] = "runtime_gate_rejected"
    assert_blocked(payload, "runtime_gate_not_ready")


@pytest.mark.parametrize(("label", "digest_field", "record_digest_field", "decision_field"), EVIDENCE_MATCH_FIELDS)
def test_upstream_digest_mismatches_block(label: str, digest_field: str, record_digest_field: str, decision_field: str) -> None:
    payload = load_ready(); candidate(payload)[digest_field] = "sha256:mismatch"
    assert_blocked(payload, f"{label}_digest_mismatch")


@pytest.mark.parametrize(("label", "digest_field", "record_digest_field", "decision_field"), EVIDENCE_MATCH_FIELDS)
def test_upstream_decision_mismatches_block(label: str, digest_field: str, record_digest_field: str, decision_field: str) -> None:
    payload = load_ready(); candidate(payload)[decision_field] = "wrong_decision"
    assert_blocked(payload, f"{label}_decision_mismatch")


@pytest.mark.parametrize("field", NON_NOOP_METADATA_FIELDS)
def test_missing_required_non_noop_metadata_blocks(field: str) -> None:
    payload = load_ready(); candidate(payload).pop(field, None)
    assert_blocked(payload, f"missing_{field}")


def test_noop_behavior_is_deterministic_and_non_mutating() -> None:
    payload = json.loads(NOOP_FIXTURE.read_text(encoding="utf-8"))
    before = copy.deepcopy(payload)
    result = evaluate_guarded_executor_path_packet(payload)
    assert result.status == "guarded_executor_path_noop"
    assert result.packet is not None
    assert result.packet.records[0].guarded_executor_path_decision == "guarded_executor_path_noop"
    assert evaluate_guarded_executor_path_packet(payload).to_dict() == result.to_dict()
    assert payload == before


def test_mixed_diagnostics_warn_only_when_policy_allows() -> None:
    result = evaluate_guarded_executor_path_packet(json.loads(MIXED_FIXTURE.read_text(encoding="utf-8")))
    assert result.status == "guarded_executor_path_ready_with_warnings"
    assert any(f.code == "mixed_scope_diagnostic" for f in result.report.findings)


def test_scope_mismatch_blocks_for_non_mixed_candidate() -> None:
    payload = load_ready(); candidate(payload)["operator_scope_keys"] = ["other"]
    assert_blocked(payload, "scope_mismatch")


FORBIDDEN_CLAIMS = [
    ("guarded_executor_path_invoked", "guarded_executor_invocation_claim"),
    ("runtime_enablement_claimed", "runtime_enablement_claim"),
    ("runtime_flags_flipped", "runtime_flag_flipping_claim"),
    ("runtime_flag_target_state_active", "runtime_flag_active_state_claim"),
    ("executor_enabled", "executor_enablement_claim"),
    ("executor_invoked", "executor_invocation_claim"),
    ("executor_activated", "executor_activation_claim"),
    ("live_commit_executed", "live_execution_claim"),
    ("permission_to_execute_now", "executor_permission_claim"),
    ("guarded_executor_prerequisites_are_invocation", "guarded_executor_prerequisite_invocation_claim"),
    ("invocation_hold_points_are_live_invocation", "invocation_hold_point_live_invocation_claim"),
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
]


@pytest.mark.parametrize(("claim", "code"), FORBIDDEN_CLAIMS)
def test_forbidden_claims_block(claim: str, code: str) -> None:
    payload = load_ready(); candidate(payload)["guarded_executor_path_claims"] = {claim: True}
    assert_blocked(payload, code)
