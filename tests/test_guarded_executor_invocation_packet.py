from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.guarded_executor_invocation_packet import (
    EVIDENCE_MATCH_FIELDS,
    INVARIANTS,
    NON_NOOP_METADATA_FIELDS,
    evaluate_guarded_executor_invocation_packet,
)

FIXTURE_ROOT = Path("tests/fixtures/guarded_executor_invocation_packet")
READY_FIXTURE = FIXTURE_ROOT / "ready_guarded_executor_invocation_candidate.json"
NOOP_FIXTURE = FIXTURE_ROOT / "noop_guarded_executor_invocation_candidate.json"
MIXED_FIXTURE = FIXTURE_ROOT / "mixed_guarded_executor_invocation_candidate.json"


def load_ready() -> dict:
    return json.loads(READY_FIXTURE.read_text(encoding="utf-8"))


def candidate(payload: dict) -> dict:
    return payload["guarded_executor_invocation_candidates"][0]


def assert_blocked(payload: dict, code: str) -> None:
    result = evaluate_guarded_executor_invocation_packet(payload)
    assert result.status == "guarded_invocation_packet_blocked"
    assert result.packet is None
    assert any(f.code == code for f in result.report.findings)


def test_ready_packet_is_deterministic_metadata_only_and_disabled() -> None:
    payload = load_ready()
    first = evaluate_guarded_executor_invocation_packet(payload)
    second = evaluate_guarded_executor_invocation_packet(copy.deepcopy(payload))
    assert first.to_dict() == second.to_dict()
    assert first.status == "guarded_executor_invocation_ready"
    assert first.packet is not None
    record = first.packet.records[0]
    assert record.guarded_executor_invocation_decision == "guarded_invocation_packet_ready_for_later_real_executor_invocation_gate"
    assert record.guarded_executor_path_packet_digest == payload["guarded_executor_path_packet"]["digest"]
    assert record.guarded_executor_path_packet_decision == payload["guarded_executor_path_packet"]["records"][0]["guarded_executor_path_decision"]
    packet_dict = first.packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert packet_dict[key] is expected
    assert record.real_executor_enabled is False
    assert record.real_executor_runtime_enablement_enabled is False
    assert record.real_executor_enablement_enabled is False
    assert record.real_executor_invocation_enabled is False
    assert record.real_executor_activation_enabled is False
    assert record.real_lock_acquisition_enabled is False
    assert record.lockfile_created is False
    assert record.live_commit_executed is False
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
        assert records
        for metadata_record in records:
            assert metadata_record.metadata_only is True
            assert metadata_record.authoritative is False
            assert metadata_record.executed is False
            assert metadata_record.executor_invoked is False
            assert metadata_record.live_receipt is False
            assert metadata_record.rollback_applied is False


def test_missing_or_invalid_path_packet_and_candidate_block() -> None:
    payload = load_ready(); payload.pop("guarded_executor_path_packet")
    assert_blocked(payload, "missing_guarded_executor_path_packet")
    payload = load_ready(); payload["guarded_executor_path_packet"] = {"records": []}
    assert_blocked(payload, "invalid_guarded_executor_path_packet")
    payload = load_ready(); payload.pop("guarded_executor_invocation_candidates")
    assert_blocked(payload, "missing_guarded_executor_invocation_candidate")
    payload = load_ready(); candidate(payload)["candidate_type"] = "unsupported"
    assert_blocked(payload, "invalid_guarded_executor_invocation_candidate")


def test_guarded_executor_path_not_ready_blocks_by_default() -> None:
    payload = load_ready()
    candidate(payload)["claimed_guarded_executor_path_packet_decision"] = "guarded_executor_path_blocked"
    payload["guarded_executor_path_packet"]["records"][0]["guarded_executor_path_decision"] = "guarded_executor_path_blocked"
    assert_blocked(payload, "guarded_executor_path_packet_not_ready")


@pytest.mark.parametrize(("label", "digest_field", "_record_digest", "decision_field"), EVIDENCE_MATCH_FIELDS)
def test_evidence_digest_and_decision_mismatches_block(label: str, digest_field: str, _record_digest: str, decision_field: str) -> None:
    payload = load_ready(); candidate(payload)[digest_field] = "sha256:mismatch"
    assert_blocked(payload, f"{label}_digest_mismatch")
    payload = load_ready(); candidate(payload)[decision_field] = "mismatch_decision"
    assert_blocked(payload, f"{label}_decision_mismatch")


@pytest.mark.parametrize("field", NON_NOOP_METADATA_FIELDS)
def test_missing_required_non_noop_metadata_blocks(field: str) -> None:
    payload = load_ready(); candidate(payload).pop(field)
    assert_blocked(payload, f"missing_{field}")


def test_scope_mismatch_blocks() -> None:
    payload = load_ready(); candidate(payload)["operator_scope_keys"] = ["other"]
    assert_blocked(payload, "scope_mismatch")


def test_noop_behavior_is_deterministic_and_non_mutating() -> None:
    payload = json.loads(NOOP_FIXTURE.read_text(encoding="utf-8"))
    before = copy.deepcopy(payload)
    first = evaluate_guarded_executor_invocation_packet(payload)
    second = evaluate_guarded_executor_invocation_packet(copy.deepcopy(payload))
    assert payload == before
    assert first.to_dict() == second.to_dict()
    assert first.status == "guarded_invocation_packet_noop"
    assert first.packet is not None
    assert first.packet.records[0].guarded_executor_invocation_decision == "guarded_invocation_packet_noop"


def test_mixed_diagnostics_warn_only_when_policy_allows() -> None:
    payload = json.loads(MIXED_FIXTURE.read_text(encoding="utf-8"))
    result = evaluate_guarded_executor_invocation_packet(payload)
    assert result.status == "guarded_invocation_packet_ready_with_warnings"
    assert any(f.code == "mixed_scope_diagnostic" for f in result.report.findings)


FORBIDDEN_CLAIMS = [
    ("guarded_executor_invocation_invoked", "guarded_executor_invocation_claim"),
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
    ("authority_granted", "authority_smuggling"),
    ("consent_granted", "consent_smuggling"),
    ("policy_created", "policy_smuggling"),
    ("truth_asserted", "truth_smuggling"),
    ("raw_payload_included", "raw_payload_leakage"),
    ("lockfile_creation_claimed", "lockfile_creation_claim"),
    ("real_lock_acquisition_claimed", "real_lock_acquisition_claim"),
    ("real_memory_root_access_claimed", "real_memory_root_access_claim"),
]


@pytest.mark.parametrize(("claim", "code"), FORBIDDEN_CLAIMS)
def test_forbidden_claims_block(claim: str, code: str) -> None:
    payload = load_ready(); candidate(payload)["guarded_executor_invocation_claims"] = {claim: True}
    assert_blocked(payload, code)
