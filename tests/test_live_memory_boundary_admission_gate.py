from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.live_memory_boundary_admission_gate import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_live_memory_boundary_admission_gate,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/live_memory_boundary_admission_gate")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_validates() -> None:
    result = validate_policy(build_default_policy())
    assert result["ok"] is True
    assert result["digest"]


def test_missing_and_invalid_inputs_block() -> None:
    expected = {
        "missing_distillation_packet_blocked.json": "live_memory_boundary_admission_blocked_missing_distillation_packet",
        "invalid_distillation_packet_blocked.json": "live_memory_boundary_admission_blocked_invalid_distillation_packet",
        "missing_receipt_gate_packet_blocked.json": "live_memory_boundary_admission_blocked_missing_receipt_gate_packet",
        "invalid_receipt_gate_packet_blocked.json": "live_memory_boundary_admission_blocked_invalid_receipt_gate_packet",
        "missing_tomb_verifier_packet_blocked.json": "live_memory_boundary_admission_blocked_missing_tomb_verifier_packet",
        "invalid_tomb_verifier_packet_blocked.json": "live_memory_boundary_admission_blocked_invalid_tomb_verifier_packet",
        "missing_writer_packet_blocked.json": "live_memory_boundary_admission_blocked_missing_writer_packet",
        "invalid_writer_packet_blocked.json": "live_memory_boundary_admission_blocked_invalid_writer_packet",
        "missing_admission_candidate_blocked.json": "live_memory_boundary_admission_blocked_missing_admission_candidate",
        "invalid_admission_candidate_blocked.json": "live_memory_boundary_admission_blocked_invalid_admission_candidate",
    }
    for fixture, status in expected.items():
        assert evaluate_live_memory_boundary_admission_gate(_fixture(fixture)).status == status


def test_valid_candidate_types_map_to_decisions() -> None:
    expected = {
        "valid_ai_capsule_boundary_candidate.json": ("live_memory_boundary_admission_ready", "boundary_review_candidate_ready"),
        "valid_human_summary_boundary_candidate.json": ("live_memory_boundary_admission_ready", "boundary_review_candidate_ready"),
        "valid_dual_capsule_boundary_candidate.json": ("live_memory_boundary_admission_ready", "boundary_review_candidate_ready"),
        "valid_protect_receipt_boundary_candidate.json": ("live_memory_boundary_admission_ready", "boundary_review_candidate_ready"),
        "valid_merge_receipt_boundary_candidate.json": ("live_memory_boundary_admission_ready", "boundary_review_candidate_ready"),
        "valid_tomb_receipt_boundary_candidate.json": ("live_memory_boundary_admission_ready", "boundary_review_candidate_ready"),
        "valid_tomb_deferred_boundary_candidate.json": ("live_memory_boundary_admission_deferred_for_operator_review", "boundary_review_deferred_for_operator_review"),
        "valid_operator_review_boundary_candidate.json": ("live_memory_boundary_admission_deferred_for_operator_review", "boundary_review_deferred_for_operator_review"),
        "valid_noop_boundary_candidate.json": ("live_memory_boundary_admission_ready", "boundary_review_noop"),
        "valid_warning_boundary_candidate.json": ("live_memory_boundary_admission_ready_with_warnings", "boundary_review_candidate_ready_with_warnings"),
        "valid_mixed_scope_diagnostic_warning.json": ("live_memory_boundary_admission_ready_with_warnings", "boundary_review_candidate_ready_with_warnings"),
    }
    for fixture, (status, decision) in expected.items():
        result = evaluate_live_memory_boundary_admission_gate(_fixture(fixture))
        assert result.status == status
        assert result.packet is not None
        assert result.packet.records[0].admission_decision == decision
        assert result.packet.digest


def test_blocker_statuses() -> None:
    expected = {
        "digest_mismatch_blocked.json": "live_memory_boundary_admission_blocked_digest_mismatch",
        "decision_mismatch_blocked.json": "live_memory_boundary_admission_blocked_decision_mismatch",
        "writer_not_ready_blocked.json": "live_memory_boundary_admission_blocked_writer_not_ready",
        "tomb_not_verified_blocked.json": "live_memory_boundary_admission_blocked_tomb_not_verified",
        "live_write_claim_blocked.json": "live_memory_boundary_admission_blocked_live_write_claim",
        "live_delete_claim_blocked.json": "live_memory_boundary_admission_blocked_live_delete_claim",
        "index_mutation_claim_blocked.json": "live_memory_boundary_admission_blocked_index_mutation_claim",
        "capsule_persistence_claim_blocked.json": "live_memory_boundary_admission_blocked_live_write_claim",
        "prompt_materialization_blocked.json": "live_memory_boundary_admission_blocked_prompt_materialization",
        "action_execution_blocked.json": "live_memory_boundary_admission_blocked_action_execution",
        "external_disclosure_blocked.json": "live_memory_boundary_admission_blocked_external_disclosure",
        "authority_smuggling_blocked.json": "live_memory_boundary_admission_blocked_authority_smuggling",
        "raw_payload_leak_blocked.json": "live_memory_boundary_admission_blocked_raw_payload_leak",
        "scope_mismatch_blocked.json": "live_memory_boundary_admission_blocked_scope_mismatch",
    }
    for fixture, status in expected.items():
        assert evaluate_live_memory_boundary_admission_gate(_fixture(fixture)).status == status


def test_operator_review_cannot_override_hard_blockers() -> None:
    payload = _fixture("authority_smuggling_blocked.json")
    payload["admission_candidate"]["requested_next_actions"] = ["operator_review_required"]
    payload["policy"] = {"allow_operator_review_candidates": True}
    assert evaluate_live_memory_boundary_admission_gate(payload).status == "live_memory_boundary_admission_blocked_authority_smuggling"


def test_mixed_scope_diagnostic_warns_only_when_allowed() -> None:
    allowed = evaluate_live_memory_boundary_admission_gate(_fixture("valid_mixed_scope_diagnostic_warning.json"))
    assert allowed.status == "live_memory_boundary_admission_ready_with_warnings"
    blocked = _fixture("valid_mixed_scope_diagnostic_warning.json")
    blocked["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    assert evaluate_live_memory_boundary_admission_gate(blocked).status == "live_memory_boundary_admission_blocked_scope_mismatch"


def test_successful_outputs_include_invariants_and_forbidden_steps() -> None:
    result = evaluate_live_memory_boundary_admission_gate(_fixture("valid_ai_capsule_boundary_candidate.json"))
    assert result.packet is not None
    packet = result.packet.to_dict()
    for key in [
        "admission_is_not_memory_write",
        "admission_is_not_memory_deletion",
        "admission_is_not_index_mutation",
        "admission_is_not_capsule_persistence",
        "admission_is_not_prompt_assembly",
        "admission_is_not_truth",
        "admission_is_not_policy",
        "admission_is_not_authority",
        "admission_is_not_consent",
        "admission_does_not_execute_action",
        "admission_does_not_disclose_externally",
        "default_deny_live_boundary",
        "future_review_required",
    ]:
        assert packet[key] is True
    for key in ["live_memory_write_enabled", "live_memory_deletion_enabled", "live_index_mutation_enabled", "capsule_persistence_enabled", "prompt_materialization_enabled", "external_disclosure_enabled", "remote_service_enabled"]:
        assert packet[key] is False
    required = {"write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "persist_capsule_now", "apply_protection_now", "apply_merge_now", "complete_tomb_now", "mutate_vector_index", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "infer_truth_from_admission", "infer_authority_from_admission", "convert_admission_to_policy", "convert_admission_to_action", "bypass_governed_writer_adapter", "enable_external_disclosure"}
    assert required.issubset(set(FORBIDDEN_NEXT_STEPS))
    assert required.issubset(set(packet["forbidden_next_steps"]))


def test_deterministic_json_digest_and_mixed_packet_counts() -> None:
    payload = _fixture("mixed_live_memory_boundary_admission_packet.json")
    first = evaluate_live_memory_boundary_admission_gate(payload)
    second = evaluate_live_memory_boundary_admission_gate(payload)
    assert first.to_dict() == second.to_dict()
    assert first.packet is not None
    assert first.report.summary_counts["candidate_count"] == 2
    assert first.report.summary_counts["boundary_review_candidate_ready"] == 1
    assert first.report.summary_counts["boundary_review_noop"] == 1


def test_fixtures_are_metadata_only() -> None:
    forbidden = ["data:image", "data:audio", "data:video", "begin private", "provider prompt text", "real operator home", "/home/"]
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        if path.name == "raw_payload_leak_blocked.json":
            assert "synthetic fixture marker" in text
            continue
        assert not any(marker in text for marker in forbidden), path
