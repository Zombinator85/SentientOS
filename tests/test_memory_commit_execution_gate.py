from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.memory_commit_execution_gate import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_memory_commit_execution_gate,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/memory_commit_execution_gate")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_validates() -> None:
    result = validate_policy(build_default_policy())
    assert result["status"] == "valid"
    assert result["digest"].startswith("sha256:")


def test_missing_and_invalid_core_inputs_block() -> None:
    expected = {
        "missing_commit_plan_packet_blocked.json": "memory_commit_execution_gate_blocked_missing_commit_plan_packet",
        "invalid_commit_plan_packet_blocked.json": "memory_commit_execution_gate_blocked_invalid_commit_plan_packet",
        "missing_operator_approval_packet_blocked.json": "memory_commit_execution_gate_blocked_missing_operator_approval_packet",
        "invalid_operator_approval_packet_blocked.json": "memory_commit_execution_gate_blocked_invalid_operator_approval_packet",
        "missing_execution_candidate_blocked.json": "memory_commit_execution_gate_blocked_missing_execution_candidate",
        "invalid_execution_candidate_blocked.json": "memory_commit_execution_gate_blocked_invalid_execution_candidate",
    }
    for fixture, status in expected.items():
        assert evaluate_memory_commit_execution_gate(_fixture(fixture)).status == status


def test_valid_candidate_types_map_to_expected_decisions() -> None:
    expected = {
        "valid_ai_capsule_commit_execution_candidate.json": "commit_execution_eligible_for_future_adapter",
        "valid_human_summary_commit_execution_candidate.json": "commit_execution_eligible_for_future_adapter",
        "valid_dual_capsule_commit_execution_candidate.json": "commit_execution_eligible_for_future_adapter",
        "valid_protect_receipt_commit_execution_candidate.json": "commit_execution_eligible_for_future_adapter",
        "valid_merge_receipt_commit_execution_candidate.json": "commit_execution_eligible_for_future_adapter",
        "valid_tomb_archive_commit_execution_candidate.json": "commit_execution_eligible_for_future_adapter",
        "valid_tomb_deferred_commit_execution_candidate.json": "commit_execution_deferred_for_operator_review",
        "valid_operator_review_commit_execution_candidate.json": "commit_execution_deferred_for_operator_review",
        "valid_noop_commit_execution_candidate.json": "commit_execution_noop",
        "valid_warning_commit_execution_candidate.json": "commit_execution_eligible_for_future_adapter_with_warnings",
        "valid_mixed_scope_diagnostic_warning.json": "commit_execution_eligible_for_future_adapter_with_warnings",
    }
    for fixture, decision in expected.items():
        result = evaluate_memory_commit_execution_gate(_fixture(fixture))
        assert result.packet is not None, fixture
        assert result.packet.records[0].execution_decision == decision, fixture


def test_blocker_behaviors() -> None:
    expected = {
        "plan_not_ready_blocked.json": "memory_commit_execution_gate_blocked_plan_not_ready",
        "approval_not_ready_blocked.json": "memory_commit_execution_gate_blocked_approval_not_ready",
        "plan_digest_mismatch_blocked.json": "memory_commit_execution_gate_blocked_plan_digest_mismatch",
        "approval_digest_mismatch_blocked.json": "memory_commit_execution_gate_blocked_approval_digest_mismatch",
        "plan_decision_mismatch_blocked.json": "memory_commit_execution_gate_blocked_plan_decision_mismatch",
        "approval_decision_mismatch_blocked.json": "memory_commit_execution_gate_blocked_approval_decision_mismatch",
        "missing_gate_precondition_blocked.json": "memory_commit_execution_gate_blocked_missing_gate_precondition",
        "precondition_mismatch_blocked.json": "memory_commit_execution_gate_blocked_precondition_mismatch",
        "missing_operator_scope_blocked.json": "memory_commit_execution_gate_blocked_missing_operator_scope",
        "scope_mismatch_blocked.json": "memory_commit_execution_gate_blocked_scope_mismatch",
        "missing_rollback_expectation_blocked.json": "memory_commit_execution_gate_blocked_missing_rollback_expectation",
        "missing_receipt_expectation_blocked.json": "memory_commit_execution_gate_blocked_missing_receipt_expectation",
        "execution_overclaim_blocked.json": "memory_commit_execution_gate_blocked_execution_overclaim",
        "execution_claim_blocked.json": "memory_commit_execution_gate_blocked_execution_claim",
        "live_write_claim_blocked.json": "memory_commit_execution_gate_blocked_live_write_claim",
        "live_delete_claim_blocked.json": "memory_commit_execution_gate_blocked_live_delete_claim",
        "index_mutation_claim_blocked.json": "memory_commit_execution_gate_blocked_index_mutation_claim",
        "capsule_persistence_claim_blocked.json": "memory_commit_execution_gate_blocked_capsule_persistence_claim",
        "prompt_materialization_blocked.json": "memory_commit_execution_gate_blocked_prompt_materialization",
        "action_execution_blocked.json": "memory_commit_execution_gate_blocked_action_execution",
        "external_disclosure_blocked.json": "memory_commit_execution_gate_blocked_external_disclosure",
        "authority_smuggling_blocked.json": "memory_commit_execution_gate_blocked_authority_smuggling",
        "raw_payload_leak_blocked.json": "memory_commit_execution_gate_blocked_raw_payload_leak",
    }
    for fixture, status in expected.items():
        assert evaluate_memory_commit_execution_gate(_fixture(fixture)).status == status, fixture


def test_operator_review_cannot_override_hard_blockers() -> None:
    payload = _fixture("authority_smuggling_blocked.json")
    payload["execution_candidate"]["metadata"]["operator_review_requested"] = True
    payload["policy"] = {"allow_operator_review_deferrals": True}
    assert evaluate_memory_commit_execution_gate(payload).status == "memory_commit_execution_gate_blocked_authority_smuggling"


def test_mixed_scope_diagnostic_warns_only_when_allowed() -> None:
    allowed = evaluate_memory_commit_execution_gate(_fixture("valid_mixed_scope_diagnostic_warning.json"))
    assert allowed.status == "memory_commit_execution_gate_ready_with_warnings"
    blocked = _fixture("valid_mixed_scope_diagnostic_warning.json")
    blocked["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    assert evaluate_memory_commit_execution_gate(blocked).status == "memory_commit_execution_gate_blocked_scope_mismatch"


def test_successful_outputs_include_non_authority_invariants_and_forbidden_steps() -> None:
    result = evaluate_memory_commit_execution_gate(_fixture("valid_ai_capsule_commit_execution_candidate.json"))
    assert result.packet is not None
    packet = result.packet.to_dict()
    for key in [
        "execution_gate_is_not_memory_write",
        "execution_gate_is_not_memory_deletion",
        "execution_gate_is_not_index_mutation",
        "execution_gate_is_not_capsule_persistence",
        "execution_gate_is_not_prompt_assembly",
        "execution_gate_is_not_execution",
        "execution_gate_is_not_live_commit",
        "execution_gate_is_not_truth",
        "execution_gate_is_not_policy",
        "execution_gate_is_not_authority",
        "execution_gate_is_not_consent",
        "execution_gate_does_not_execute_action",
        "execution_gate_does_not_disclose_externally",
        "default_deny_live_commit",
        "future_commit_adapter_required",
        "future_live_dry_run_required",
        "rollback_expectation_required",
        "receipt_expectation_required",
        "operator_approval_required",
    ]:
        assert packet[key] is True
    for key in ["live_memory_write_enabled", "live_memory_deletion_enabled", "live_index_mutation_enabled", "capsule_persistence_enabled", "prompt_materialization_enabled", "external_disclosure_enabled", "remote_service_enabled"]:
        assert packet[key] is False
    required = {"write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "run_live_commit_now", "execute_commit_plan_now", "execute_operator_approval_now", "execute_memory_commit_execution_gate_now", "mutate_vector_index", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "infer_truth_from_execution_gate", "infer_authority_from_execution_gate", "convert_execution_gate_to_policy", "convert_execution_gate_to_action", "bypass_commit_plan_packet", "bypass_operator_approval_packet", "enable_external_disclosure"}
    assert required.issubset(set(FORBIDDEN_NEXT_STEPS))
    assert required.issubset(set(packet["forbidden_next_steps"]))


def test_deterministic_json_digest_and_mixed_packet_counts() -> None:
    payload = _fixture("mixed_memory_commit_execution_gate_packet.json")
    first = evaluate_memory_commit_execution_gate(payload)
    second = evaluate_memory_commit_execution_gate(payload)
    assert first.to_dict() == second.to_dict()
    assert first.packet is not None
    assert first.report.summary_counts["candidate_count"] == 2
    assert first.report.summary_counts["commit_execution_eligible_for_future_adapter"] == 1
    assert first.report.summary_counts["commit_execution_noop"] == 1
    assert first.digest.startswith("sha256:")


def test_fixtures_are_metadata_only() -> None:
    forbidden = ["data:image", "data:audio", "data:video", "begin private", "provider prompt text", "real operator home", "/home/"]
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        if path.name == "raw_payload_leak_blocked.json":
            assert "synthetic fixture marker" in text
            continue
        assert not any(marker in text for marker in forbidden), path


def test_no_unsafe_surfaces_are_introduced() -> None:
    text = Path("sentientos/memory_commit_execution_gate.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler"]
    assert not any(marker in text for marker in forbidden)
