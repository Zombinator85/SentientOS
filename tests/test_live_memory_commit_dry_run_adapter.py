from __future__ import annotations

import json

import pytest
from pathlib import Path

from sentientos.live_memory_commit_dry_run_adapter import (
    FORBIDDEN_NEXT_STEPS,
    LiveMemoryCommitDryRunPolicy,
    build_default_policy,
    evaluate_live_memory_commit_dry_run_adapter,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/live_memory_commit_dry_run_adapter")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_is_default_deny_and_preview_friendly() -> None:
    policy = build_default_policy()
    assert policy.default_dry_run_posture == "deny"
    assert policy.allow_dry_run_previews is True
    assert policy.allow_warning_previews is True
    assert policy.allow_operator_review_deferrals is True
    assert policy.allow_noop_previews is True
    assert policy.allow_mixed_scope_diagnostic_packet is False
    assert policy.require_execution_gate_ready is True
    assert policy.require_matching_execution_gate_digest is True
    assert policy.require_matching_execution_gate_decision is True
    assert policy.require_operation_preview is True
    assert policy.require_receipt_preview is True
    assert policy.require_rollback_preview is True
    assert policy.require_scope_alignment is True
    assert policy.block_live_write_claims is True
    assert policy.block_live_delete_claims is True
    assert policy.block_index_mutation_claims is True
    assert policy.block_capsule_persistence_claims is True
    assert policy.block_tomb_completion_claims is True
    assert policy.block_hard_override_attempts is True
    assert validate_policy(policy)["status"] == "valid"


def test_valid_candidate_fixtures_are_ready_or_expected_terminal_states() -> None:
    expected = {
        "valid_ai_capsule_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_ready", "dry_run_commit_preview_ready"),
        "valid_human_summary_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_ready", "dry_run_commit_preview_ready"),
        "valid_dual_capsule_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_ready", "dry_run_commit_preview_ready"),
        "valid_protect_receipt_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_ready", "dry_run_commit_preview_ready"),
        "valid_merge_receipt_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_ready", "dry_run_commit_preview_ready"),
        "valid_tomb_archive_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_ready", "dry_run_commit_preview_ready"),
        "valid_tomb_deferred_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_deferred_for_operator_review", "dry_run_deferred_for_operator_review"),
        "valid_operator_review_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_deferred_for_operator_review", "dry_run_deferred_for_operator_review"),
        "valid_noop_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_noop", "dry_run_noop"),
        "valid_warning_commit_dry_run_candidate.json": ("live_memory_commit_dry_run_ready_with_warnings", "dry_run_commit_preview_ready_with_warnings"),
        "valid_mixed_scope_diagnostic_warning.json": ("live_memory_commit_dry_run_ready_with_warnings", "dry_run_commit_preview_ready_with_warnings"),
    }
    for fixture, (status, decision) in expected.items():
        result = evaluate_live_memory_commit_dry_run_adapter(_fixture(fixture))
        assert result.status == status, fixture
        assert result.packet is not None
        record = result.packet.records[0]
        assert record.dry_run_decision == decision
        if decision not in {"dry_run_noop"}:
            assert record.operation_preview is not None
            assert record.operation_preview.hypothetical_only is True
            assert record.operation_preview.applied is False
            assert record.receipt_preview is not None
            assert record.receipt_preview.receipt_emitted is False
            assert record.rollback_preview is not None
            assert record.rollback_preview.rollback_applied is False


def test_blocker_fixtures_return_expected_statuses() -> None:
    expected = {
        "missing_execution_gate_packet_blocked.json": "live_memory_commit_dry_run_blocked_missing_execution_gate_packet",
        "invalid_execution_gate_packet_blocked.json": "live_memory_commit_dry_run_blocked_invalid_execution_gate_packet",
        "missing_commit_candidate_blocked.json": "live_memory_commit_dry_run_blocked_missing_commit_candidate",
        "invalid_commit_candidate_blocked.json": "live_memory_commit_dry_run_blocked_invalid_commit_candidate",
        "execution_gate_not_ready_blocked.json": "live_memory_commit_dry_run_blocked_execution_gate_not_ready",
        "execution_gate_digest_mismatch_blocked.json": "live_memory_commit_dry_run_blocked_execution_gate_digest_mismatch",
        "execution_gate_decision_mismatch_blocked.json": "live_memory_commit_dry_run_blocked_execution_gate_decision_mismatch",
        "missing_operation_preview_blocked.json": "live_memory_commit_dry_run_blocked_missing_operation_preview",
        "operation_preview_mismatch_blocked.json": "live_memory_commit_dry_run_blocked_operation_preview_mismatch",
        "missing_receipt_preview_blocked.json": "live_memory_commit_dry_run_blocked_missing_receipt_preview",
        "missing_rollback_preview_blocked.json": "live_memory_commit_dry_run_blocked_missing_rollback_preview",
        "live_write_claim_blocked.json": "live_memory_commit_dry_run_blocked_live_write_claim",
        "live_delete_claim_blocked.json": "live_memory_commit_dry_run_blocked_live_delete_claim",
        "index_mutation_claim_blocked.json": "live_memory_commit_dry_run_blocked_index_mutation_claim",
        "capsule_persistence_claim_blocked.json": "live_memory_commit_dry_run_blocked_capsule_persistence_claim",
        "tomb_completion_claim_blocked.json": "live_memory_commit_dry_run_blocked_tomb_completion_claim",
        "prompt_materialization_blocked.json": "live_memory_commit_dry_run_blocked_prompt_materialization",
        "action_execution_blocked.json": "live_memory_commit_dry_run_blocked_action_execution",
        "external_disclosure_blocked.json": "live_memory_commit_dry_run_blocked_external_disclosure",
        "authority_smuggling_blocked.json": "live_memory_commit_dry_run_blocked_authority_smuggling",
        "raw_payload_leak_blocked.json": "live_memory_commit_dry_run_blocked_raw_payload_leak",
        "scope_mismatch_blocked.json": "live_memory_commit_dry_run_blocked_scope_mismatch",
    }
    for fixture, status in expected.items():
        assert evaluate_live_memory_commit_dry_run_adapter(_fixture(fixture)).status == status, fixture


def test_operator_review_cannot_override_hard_blockers() -> None:
    payload = _fixture("authority_smuggling_blocked.json")
    payload["commit_candidate"]["metadata"]["operator_review_requested"] = True
    payload["policy"] = {"allow_operator_review_deferrals": True}
    assert evaluate_live_memory_commit_dry_run_adapter(payload).status == "live_memory_commit_dry_run_blocked_authority_smuggling"


def test_mixed_scope_diagnostic_warns_only_when_allowed() -> None:
    allowed = evaluate_live_memory_commit_dry_run_adapter(_fixture("valid_mixed_scope_diagnostic_warning.json"))
    assert allowed.status == "live_memory_commit_dry_run_ready_with_warnings"
    blocked = _fixture("valid_mixed_scope_diagnostic_warning.json")
    blocked["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    assert evaluate_live_memory_commit_dry_run_adapter(blocked).status == "live_memory_commit_dry_run_blocked_scope_mismatch"


def test_successful_outputs_include_non_authority_invariants_and_forbidden_steps() -> None:
    result = evaluate_live_memory_commit_dry_run_adapter(_fixture("valid_ai_capsule_commit_dry_run_candidate.json"))
    assert result.packet is not None
    packet = result.packet.to_dict()
    for key in [
        "dry_run_is_not_memory_write", "dry_run_is_not_memory_deletion", "dry_run_is_not_index_mutation", "dry_run_is_not_capsule_persistence", "dry_run_is_not_prompt_assembly", "dry_run_is_not_execution", "dry_run_is_not_live_commit", "dry_run_is_not_truth", "dry_run_is_not_policy", "dry_run_is_not_authority", "dry_run_is_not_consent", "dry_run_does_not_execute_action", "dry_run_does_not_disclose_externally", "default_deny_live_commit", "future_commit_adapter_required", "future_safety_interlock_required", "receipt_preview_required", "rollback_preview_required", "execution_gate_required",
    ]:
        assert packet[key] is True
    for key in ["live_memory_write_enabled", "live_memory_deletion_enabled", "live_index_mutation_enabled", "capsule_persistence_enabled", "prompt_materialization_enabled", "external_disclosure_enabled", "remote_service_enabled"]:
        assert packet[key] is False
    required = {"write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "persist_capsule_now", "persist_summary_now", "apply_protection_now", "apply_merge_now", "complete_tomb_now", "run_live_commit_now", "execute_dry_run_as_commit", "execute_commit_plan_now", "execute_operator_approval_now", "treat_dry_run_as_execution", "treat_dry_run_as_live_commit", "call_append_memory", "call_purge_memory", "call_apply_forgetting_curve", "call_curate_memory", "call_summarize_memory", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "infer_truth_from_dry_run", "infer_authority_from_dry_run", "infer_consent_from_dry_run", "convert_dry_run_to_policy", "convert_dry_run_to_action", "bypass_execution_gate", "bypass_operator_approval_packet", "bypass_commit_plan_packet", "bypass_live_boundary_admission", "bypass_governed_writer_adapter", "bypass_tomb_verifier", "bypass_receipt_gate", "bypass_distillation_contract", "bypass_operator_review", "enable_external_disclosure"}
    assert required.issubset(set(FORBIDDEN_NEXT_STEPS))
    assert required.issubset(set(packet["forbidden_next_steps"]))


def test_deterministic_json_digest_and_mixed_packet_counts() -> None:
    payload = _fixture("mixed_live_memory_commit_dry_run_packet.json")
    first = evaluate_live_memory_commit_dry_run_adapter(payload)
    second = evaluate_live_memory_commit_dry_run_adapter(payload)
    assert first.to_dict() == second.to_dict()
    assert first.packet is not None
    assert first.report.summary_counts["candidate_count"] == 2
    assert first.report.summary_counts["dry_run_commit_preview_ready"] == 1
    assert first.report.summary_counts["dry_run_noop"] == 1
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
    text = Path("sentientos/live_memory_commit_dry_run_adapter.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler"]
    assert not any(marker in text for marker in forbidden)


def test_invalid_policy_rejected() -> None:
    result = validate_policy(LiveMemoryCommitDryRunPolicy(default_dry_run_posture="allow"))
    assert result["status"] == "invalid"
