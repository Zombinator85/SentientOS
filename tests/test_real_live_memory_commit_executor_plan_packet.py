from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sentientos.real_live_memory_commit_executor_plan_packet import (
    evaluate_real_live_memory_commit_executor_plan_packet,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURE_ROOT = Path("tests/fixtures/real_live_memory_commit_executor_plan_packet")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _base() -> dict:
    return _fixture("valid_ai_capsule_executor_plan_candidate.json")


def _blocked(payload: dict) -> str:
    result = evaluate_real_live_memory_commit_executor_plan_packet(payload)
    assert result.status == "executor_plan_blocked"
    assert result.packet is None
    return result.report.findings[0].code


def test_valid_candidate_emits_disabled_executor_plan_packet_records() -> None:
    result = evaluate_real_live_memory_commit_executor_plan_packet(_base())
    assert result.status == "executor_plan_ready"
    assert result.packet is not None
    packet = result.packet.to_dict()
    assert packet["executor_plan_is_not_memory_write"] is True
    assert packet["executor_plan_is_not_live_commit_execution"] is True
    assert packet["live_executor_enabled"] is False
    assert packet["future_real_live_memory_commit_executor_required"] is True
    assert packet["future_live_executor_lock_gate_required"] is True
    assert packet["future_post_execution_audit_required"] is True
    record = packet["records"][0]
    assert record["runtime_execution_gate_digest"] == _base()["executor_plan_candidates"][0]["claimed_runtime_execution_gate_digest"]
    assert record["ordered_operation_intent_records"][0]["intent_only"] is True
    assert record["ordered_operation_intent_records"][0]["executed"] is False
    assert record["receipt_target_records"][0]["live_receipt_emitted"] is False
    assert record["rollback_target_records"][0]["rollback_applied"] is False
    assert record["verification_step_records"][0]["verification_performed"] is False
    assert record["abort_condition_records"][0]["abort_evaluated_at_runtime"] is False
    assert record["audit_expectation_records"][0]["audit_emitted"] is False
    assert record["future_live_executor_consideration_record"]["live_executor_enabled"] is False


def test_policy_preserves_disabled_default_invariants() -> None:
    result = validate_policy()
    assert result["status"] == "valid"
    bad = validate_policy({"default_posture": "allow", "live_executor_enabled": True})
    assert bad["status"] == "invalid"
    assert {finding["code"] for finding in bad["findings"]} >= {"default_posture_not_deny", "invariant_live_executor_enabled_changed", "live_executor_enabled"}


def test_missing_and_invalid_upstream_or_candidate_blocks() -> None:
    payload = _base(); payload.pop("explicit_live_memory_runtime_execution_gate_packet")
    assert _blocked(payload) == "missing_runtime_execution_gate_packet"
    payload = _base(); payload["explicit_live_memory_runtime_execution_gate_packet"] = {"digest": "sha256:x", "records": []}
    assert _blocked(payload) == "invalid_runtime_execution_gate_packet"
    payload = _base(); payload["executor_plan_candidates"] = []
    assert _blocked(payload) == "missing_executor_plan_candidate"
    payload = _base(); payload["executor_plan_candidates"][0]["candidate_type"] = "bad"
    assert _blocked(payload) == "invalid_executor_plan_candidate"


def test_candidate_type_statuses_are_deterministic() -> None:
    expected = {
        "ai_capsule_executor_plan_candidate": "executor_plan_ready",
        "human_summary_executor_plan_candidate": "executor_plan_ready",
        "dual_capsule_executor_plan_candidate": "executor_plan_ready",
        "protect_receipt_executor_plan_candidate": "executor_plan_ready",
        "merge_receipt_executor_plan_candidate": "executor_plan_ready",
        "tomb_archive_executor_plan_candidate": "executor_plan_ready",
        "tomb_deferred_executor_plan_candidate": "executor_plan_ready",
        "operator_review_executor_plan_candidate": "executor_plan_deferred_for_operator_review",
    }
    for candidate_type, status in expected.items():
        payload = _base(); payload["executor_plan_candidates"][0]["candidate_type"] = candidate_type
        assert evaluate_real_live_memory_commit_executor_plan_packet(payload).status == status
    assert evaluate_real_live_memory_commit_executor_plan_packet(_fixture("noop_executor_plan_candidate.json")).status == "executor_plan_noop"
    payload = _base(); payload["executor_plan_candidates"][0]["candidate_type"] = "mixed_executor_plan_candidate"; payload["executor_plan_candidates"][0]["metadata"] = {"diagnostic_warning": True}
    payload["executor_plan_candidates"][0]["operator_scope_keys"] = ["different"]
    assert evaluate_real_live_memory_commit_executor_plan_packet(payload).status == "executor_plan_ready_with_warnings"


def test_evidence_metadata_and_executor_plan_blockers() -> None:
    cases: dict[str, tuple[list[str], object, str]] = {
        "runtime_execution_gate_not_ready": (["explicit_live_memory_runtime_execution_gate_packet", "records", 0, "execution_gate_decision"], "runtime_execution_gate_blocked", "runtime_execution_gate_not_ready"),
        "runtime_execution_gate_digest_mismatch": (["executor_plan_candidates", 0, "claimed_runtime_execution_gate_digest"], "sha256:mismatch", "runtime_execution_gate_digest_mismatch"),
        "runtime_execution_gate_decision_mismatch": (["executor_plan_candidates", 0, "claimed_runtime_execution_gate_decision"], "runtime_execution_gate_noop", "runtime_execution_gate_decision_mismatch"),
        "readiness_envelope_digest_mismatch": (["executor_plan_candidates", 0, "claimed_readiness_envelope_digest"], "sha256:mismatch", "readiness_envelope_digest_mismatch"),
        "readiness_envelope_decision_mismatch": (["executor_plan_candidates", 0, "claimed_readiness_envelope_decision"], "bad", "readiness_envelope_decision_mismatch"),
        "final_review_digest_mismatch": (["executor_plan_candidates", 0, "claimed_final_review_digest"], "sha256:mismatch", "final_review_digest_mismatch"),
        "final_review_decision_mismatch": (["executor_plan_candidates", 0, "claimed_final_review_decision"], "bad", "final_review_decision_mismatch"),
        "real_root_admission_digest_mismatch": (["executor_plan_candidates", 0, "claimed_real_root_admission_digest"], "sha256:mismatch", "real_root_admission_digest_mismatch"),
        "real_root_admission_decision_mismatch": (["executor_plan_candidates", 0, "claimed_real_root_admission_decision"], "bad", "real_root_admission_decision_mismatch"),
        "sandbox_commit_digest_mismatch": (["executor_plan_candidates", 0, "claimed_sandbox_commit_digest"], "sha256:mismatch", "sandbox_commit_digest_mismatch"),
        "sandbox_commit_decision_mismatch": (["executor_plan_candidates", 0, "claimed_sandbox_commit_decision"], "bad", "sandbox_commit_decision_mismatch"),
        "missing_sandbox_receipt_manifest_digest": (["executor_plan_candidates", 0, "claimed_sandbox_receipt_manifest_digest"], "", "missing_sandbox_receipt_manifest_digest"),
        "missing_sandbox_rollback_manifest_digest": (["executor_plan_candidates", 0, "claimed_sandbox_rollback_manifest_digest"], "", "missing_sandbox_rollback_manifest_digest"),
        "missing_sandbox_artifact_plan": (["executor_plan_candidates", 0, "sandbox_artifact_plan"], {}, "missing_sandbox_artifact_plan"),
        "missing_live_receipt_schema_metadata": (["executor_plan_candidates", 0, "live_receipt_schema_metadata"], {}, "missing_live_receipt_schema_metadata"),
        "missing_live_rollback_schema_metadata": (["executor_plan_candidates", 0, "live_rollback_schema_metadata"], {}, "missing_live_rollback_schema_metadata"),
        "missing_post_commit_verification_plan": (["executor_plan_candidates", 0, "post_commit_verification_plan"], {}, "missing_post_commit_verification_plan"),
        "missing_abort_panic_stop_condition_metadata": (["executor_plan_candidates", 0, "abort_panic_stop_condition_metadata"], {}, "missing_abort_panic_stop_condition_metadata"),
        "missing_operator_runtime_confirmation_metadata": (["executor_plan_candidates", 0, "operator_runtime_confirmation_metadata"], {}, "missing_operator_runtime_confirmation_metadata"),
        "missing_operator_identity_role_metadata": (["executor_plan_candidates", 0, "operator_identity_role_metadata"], {}, "missing_operator_identity_role_metadata"),
        "missing_execution_window_metadata": (["executor_plan_candidates", 0, "execution_window_metadata"], {}, "missing_execution_window_metadata"),
        "missing_dry_run_to_live_equivalence_metadata": (["executor_plan_candidates", 0, "dry_run_to_live_equivalence_metadata"], {}, "missing_dry_run_to_live_equivalence_metadata"),
        "missing_rollback_rehearsal_metadata": (["executor_plan_candidates", 0, "rollback_rehearsal_metadata"], {}, "missing_rollback_rehearsal_metadata"),
        "missing_post_execution_audit_metadata": (["executor_plan_candidates", 0, "post_execution_audit_metadata"], {}, "missing_post_execution_audit_metadata"),
        "missing_executor_plan_operation_list": (["executor_plan_candidates", 0, "executor_plan_operations"], [], "missing_executor_plan_operation_list"),
        "missing_operation_ordering_metadata": (["executor_plan_candidates", 0, "operation_ordering_metadata"], {}, "missing_operation_ordering_metadata"),
        "missing_lock_lease_expectation_metadata": (["executor_plan_candidates", 0, "lock_lease_expectation_metadata"], {}, "missing_lock_lease_expectation_metadata"),
        "missing_idempotency_key_metadata": (["executor_plan_candidates", 0, "idempotency_key_metadata"], {}, "missing_idempotency_key_metadata"),
        "missing_atomicity_boundary_metadata": (["executor_plan_candidates", 0, "atomicity_boundary_metadata"], {}, "missing_atomicity_boundary_metadata"),
        "missing_failure_mode_classification_metadata": (["executor_plan_candidates", 0, "failure_mode_classification_metadata"], {}, "missing_failure_mode_classification_metadata"),
    }
    for _, (path, value, expected_code) in cases.items():
        payload = _base(); target = payload
        for key in path[:-1]: target = target[key]
        target[path[-1]] = value
        assert _blocked(payload) == expected_code
    op_cases = {
        "precondition_metadata": "missing_per_operation_precondition_metadata",
        "receipt_target_metadata": "missing_receipt_target_metadata",
        "rollback_target_metadata": "missing_rollback_target_metadata",
    }
    for key, expected_code in op_cases.items():
        payload = _base(); payload["executor_plan_candidates"][0]["executor_plan_operations"][0][key] = {}
        assert _blocked(payload) == expected_code


def test_boundary_claims_block() -> None:
    claims = {
        "real_memory_root_access_claimed": "real_memory_root_access_claim",
        "live_memory_write_claimed": "live_write_claim",
        "live_memory_delete_claimed": "live_delete_claim",
        "live_memory_purge_claimed": "live_purge_claim",
        "live_index_mutation_claimed": "index_mutation_claim",
        "capsule_persistence_claimed": "capsule_persistence_claim",
        "tomb_completion_claimed": "tomb_completion_claim",
        "protection_application_claimed": "protection_application_claim",
        "merge_application_claimed": "merge_application_claim",
        "runtime_execution_claimed": "runtime_execution_claim",
        "executor_plan_grants_permission": "executor_permission_claim",
        "readiness_envelope_is_runtime_permission": "readiness_conversion_claim",
        "final_review_is_execution_permission": "final_review_conversion_claim",
        "sandbox_commit_is_real_commit": "sandbox_conversion_claim",
        "real_root_admission_is_memory_root_access": "real_root_admission_conversion_claim",
        "prompt_assembly_claimed": "prompt_materialization",
        "live_context_retrieval_claimed": "live_context_retrieval",
        "action_execution_claimed": "action_execution",
        "external_disclosure_claimed": "external_disclosure",
        "authority_claimed": "authority_smuggling",
        "consent_claimed": "consent_smuggling",
        "policy_claimed": "policy_smuggling",
        "truth_claimed": "truth_smuggling",
    }
    for claim, code in claims.items():
        payload = _base(); payload["executor_plan_candidates"][0]["executor_plan_claims"] = {claim: True}
        assert _blocked(payload) == code
    payload = _base(); payload["executor_plan_candidates"][0]["secret_payload"] = "secret: no"
    assert _blocked(payload) == "raw_payload_leak"
    payload = _base(); payload["executor_plan_candidates"][0]["operator_scope_keys"] = ["different"]
    assert _blocked(payload) == "scope_mismatch"


def test_evaluate_mode_is_deterministic_and_non_mutating(tmp_path: Path) -> None:
    payload = _base()
    probe = tmp_path / "probe"; probe.mkdir()
    before = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    first = evaluate_real_live_memory_commit_executor_plan_packet(payload).to_dict()
    second = evaluate_real_live_memory_commit_executor_plan_packet(payload).to_dict()
    after = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    assert first == second
    assert before == after == []


def test_noop_is_deterministic_non_mutating_and_needs_no_non_noop_metadata(tmp_path: Path) -> None:
    first = evaluate_real_live_memory_commit_executor_plan_packet(_fixture("noop_executor_plan_candidate.json"))
    second = evaluate_real_live_memory_commit_executor_plan_packet(_fixture("noop_executor_plan_candidate.json"))
    assert first.to_dict() == second.to_dict()
    assert first.status == "executor_plan_noop"
    probe = tmp_path / "noop-probe"; probe.mkdir()
    assert list(probe.rglob("*")) == []


def test_mixed_diagnostics_warn_only_when_policy_allows_them() -> None:
    payload = _base(); payload["executor_plan_candidates"][0]["candidate_type"] = "mixed_executor_plan_candidate"; payload["executor_plan_candidates"][0]["metadata"] = {"diagnostic_warning": True}; payload["executor_plan_candidates"][0]["operator_scope_keys"] = ["different"]
    allowed = evaluate_real_live_memory_commit_executor_plan_packet(payload)
    assert allowed.status == "executor_plan_ready_with_warnings"
    blocked_payload = copy.deepcopy(payload); blocked_payload["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    blocked = evaluate_real_live_memory_commit_executor_plan_packet(blocked_payload)
    assert blocked.status == "executor_plan_blocked"
    assert blocked.report.findings[0].code == "scope_mismatch"


def test_module_does_not_introduce_unsafe_runtime_surfaces() -> None:
    text = Path("sentientos/real_live_memory_commit_executor_plan_packet.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler", "write_text(", "open("]
    assert not any(marker in text for marker in forbidden)
