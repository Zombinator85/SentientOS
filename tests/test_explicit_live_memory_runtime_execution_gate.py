from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.explicit_live_memory_runtime_execution_gate import (
    evaluate_explicit_live_memory_runtime_execution_gate,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURE_ROOT = Path("tests/fixtures/explicit_live_memory_runtime_execution_gate")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_valid_candidate_emits_disabled_runtime_execution_gate_records() -> None:
    result = evaluate_explicit_live_memory_runtime_execution_gate(_fixture("valid_ai_capsule_runtime_execution_gate_candidate.json"))
    assert result.status == "runtime_execution_gate_ready"
    assert result.packet is not None
    packet = result.packet.to_dict()
    assert packet["runtime_execution_gate_is_not_memory_write"] is True
    assert packet["runtime_execution_gate_is_not_live_commit_execution"] is True
    assert packet["live_executor_enabled"] is False
    assert packet["future_real_live_memory_commit_executor_required"] is True
    assert packet["future_operator_runtime_confirmation_required"] is True
    assert packet["future_post_execution_audit_required"] is True
    record = packet["records"][0]
    assert record["readiness_envelope_digest"] == _fixture("valid_ai_capsule_runtime_execution_gate_candidate.json")["runtime_execution_gate_candidates"][0]["claimed_readiness_envelope_digest"]
    assert record["execution_precondition_record"]["execution_performed"] is False
    assert record["verification_readiness_record"]["post_commit_verification_performed"] is False
    assert record["abort_readiness_record"]["abort_ready_metadata_only"] is True
    assert record["rollback_readiness_record"]["rollback_applied"] is False
    assert record["future_live_executor_consideration_record"]["live_executor_enabled"] is False


def test_policy_preserves_disabled_default_invariants() -> None:
    result = validate_policy()
    assert result["status"] == "valid"
    bad = validate_policy({"default_posture": "allow", "live_executor_enabled": True})
    assert bad["status"] == "invalid"
    assert {finding["code"] for finding in bad["findings"]} >= {"default_posture_not_deny", "invariant_live_executor_enabled_changed"}


def test_candidate_type_statuses_are_deterministic() -> None:
    expected = {
        "valid_ai_capsule_runtime_execution_gate_candidate.json": "runtime_execution_gate_ready",
        "valid_human_summary_runtime_execution_gate_candidate.json": "runtime_execution_gate_ready",
        "valid_dual_capsule_runtime_execution_gate_candidate.json": "runtime_execution_gate_ready",
        "valid_protect_receipt_runtime_execution_gate_candidate.json": "runtime_execution_gate_ready",
        "valid_merge_receipt_runtime_execution_gate_candidate.json": "runtime_execution_gate_ready",
        "valid_tomb_archive_runtime_execution_gate_candidate.json": "runtime_execution_gate_ready",
        "valid_tomb_deferred_runtime_execution_gate_candidate.json": "runtime_execution_gate_ready",
        "operator_review_runtime_execution_gate_candidate.json": "runtime_execution_gate_deferred_for_operator_review",
        "noop_runtime_execution_gate_candidate.json": "runtime_execution_gate_noop",
        "mixed_runtime_execution_gate_candidate.json": "runtime_execution_gate_ready_with_warnings",
    }
    for fixture, status in expected.items():
        assert evaluate_explicit_live_memory_runtime_execution_gate(_fixture(fixture)).status == status, fixture


def test_blocker_fixtures_cover_evidence_metadata_and_boundaries() -> None:
    expected_codes = {
        "missing_readiness_envelope_packet_blocked.json": "missing_readiness_envelope_packet",
        "invalid_readiness_envelope_packet_blocked.json": "invalid_readiness_envelope_packet",
        "missing_candidate_blocked.json": "missing_runtime_execution_gate_candidate",
        "invalid_candidate_blocked.json": "invalid_runtime_execution_gate_candidate",
        "readiness_envelope_not_ready_blocked.json": "readiness_envelope_not_ready",
        "readiness_envelope_digest_mismatch_blocked.json": "readiness_envelope_digest_mismatch",
        "readiness_envelope_decision_mismatch_blocked.json": "readiness_envelope_decision_mismatch",
        "final_review_digest_mismatch_blocked.json": "final_review_digest_mismatch",
        "final_review_decision_mismatch_blocked.json": "final_review_decision_mismatch",
        "real_root_admission_digest_mismatch_blocked.json": "real_root_admission_digest_mismatch",
        "real_root_admission_decision_mismatch_blocked.json": "real_root_admission_decision_mismatch",
        "sandbox_commit_digest_mismatch_blocked.json": "sandbox_commit_digest_mismatch",
        "sandbox_commit_decision_mismatch_blocked.json": "sandbox_commit_decision_mismatch",
        "missing_sandbox_receipt_manifest_digest_blocked.json": "missing_sandbox_receipt_manifest_digest",
        "missing_sandbox_rollback_manifest_digest_blocked.json": "missing_sandbox_rollback_manifest_digest",
        "missing_sandbox_artifact_plan_blocked.json": "missing_sandbox_artifact_plan",
        "missing_live_receipt_schema_metadata_blocked.json": "missing_live_receipt_schema_metadata",
        "missing_live_rollback_schema_metadata_blocked.json": "missing_live_rollback_schema_metadata",
        "missing_post_commit_verification_plan_blocked.json": "missing_post_commit_verification_plan",
        "missing_abort_panic_stop_condition_metadata_blocked.json": "missing_abort_panic_stop_condition_metadata",
        "missing_operator_runtime_confirmation_metadata_blocked.json": "missing_operator_runtime_confirmation_metadata",
        "missing_operator_identity_role_metadata_blocked.json": "missing_operator_identity_role_metadata",
        "missing_execution_window_metadata_blocked.json": "missing_execution_window_metadata",
        "missing_dry_run_to_live_equivalence_metadata_blocked.json": "missing_dry_run_to_live_equivalence_metadata",
        "missing_rollback_rehearsal_metadata_blocked.json": "missing_rollback_rehearsal_metadata",
        "missing_post_execution_audit_metadata_blocked.json": "missing_post_execution_audit_metadata",
        "real_memory_root_access_claim_blocked.json": "real_memory_root_access_claim",
        "live_write_claim_blocked.json": "live_write_claim",
        "live_delete_claim_blocked.json": "live_delete_claim",
        "live_purge_claim_blocked.json": "live_purge_claim",
        "index_mutation_claim_blocked.json": "index_mutation_claim",
        "capsule_persistence_claim_blocked.json": "capsule_persistence_claim",
        "tomb_completion_claim_blocked.json": "tomb_completion_claim",
        "protection_application_claim_blocked.json": "protection_application_claim",
        "merge_application_claim_blocked.json": "merge_application_claim",
        "runtime_execution_claim_blocked.json": "runtime_execution_claim",
        "readiness_envelope_conversion_claim_blocked.json": "readiness_envelope_conversion_claim",
        "final_review_conversion_claim_blocked.json": "final_review_conversion_claim",
        "sandbox_conversion_claim_blocked.json": "sandbox_conversion_claim",
        "real_root_admission_conversion_claim_blocked.json": "real_root_admission_conversion_claim",
        "prompt_materialization_blocked.json": "prompt_materialization",
        "live_context_retrieval_blocked.json": "live_context_retrieval",
        "action_execution_blocked.json": "action_execution",
        "external_disclosure_blocked.json": "external_disclosure",
        "authority_smuggling_blocked.json": "authority_smuggling",
        "consent_smuggling_blocked.json": "consent_smuggling",
        "policy_smuggling_blocked.json": "policy_smuggling",
        "truth_smuggling_blocked.json": "truth_smuggling",
        "raw_payload_leak_blocked.json": "raw_payload_leak",
        "scope_mismatch_blocked.json": "scope_mismatch",
    }
    for fixture, code in expected_codes.items():
        result = evaluate_explicit_live_memory_runtime_execution_gate(_fixture(fixture))
        assert result.status == "runtime_execution_gate_blocked", fixture
        assert result.report.findings[0].code == code, fixture
        assert result.packet is None


def test_evaluate_mode_is_deterministic_and_non_mutating(tmp_path: Path) -> None:
    payload = _fixture("valid_ai_capsule_runtime_execution_gate_candidate.json")
    probe = tmp_path / "probe"; probe.mkdir()
    before = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    first = evaluate_explicit_live_memory_runtime_execution_gate(payload).to_dict()
    second = evaluate_explicit_live_memory_runtime_execution_gate(payload).to_dict()
    after = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    assert first == second
    assert before == after == []


def test_noop_is_deterministic_non_mutating_and_needs_no_non_noop_metadata(tmp_path: Path) -> None:
    first = evaluate_explicit_live_memory_runtime_execution_gate(_fixture("noop_runtime_execution_gate_candidate.json"))
    second = evaluate_explicit_live_memory_runtime_execution_gate(_fixture("noop_runtime_execution_gate_candidate.json"))
    assert first.to_dict() == second.to_dict()
    assert first.status == "runtime_execution_gate_noop"
    probe = tmp_path / "noop-probe"; probe.mkdir()
    assert list(probe.rglob("*")) == []


def test_mixed_diagnostics_warn_only_when_policy_allows_them() -> None:
    allowed = evaluate_explicit_live_memory_runtime_execution_gate(_fixture("mixed_runtime_execution_gate_candidate.json"))
    assert allowed.status == "runtime_execution_gate_ready_with_warnings"
    payload = _fixture("mixed_runtime_execution_gate_candidate.json")
    payload["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    blocked = evaluate_explicit_live_memory_runtime_execution_gate(payload)
    assert blocked.status == "runtime_execution_gate_blocked"
    assert blocked.report.findings[0].code == "scope_mismatch"


def test_module_does_not_introduce_unsafe_runtime_surfaces() -> None:
    text = Path("sentientos/explicit_live_memory_runtime_execution_gate.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler", "write_text(", "open("]
    assert not any(marker in text for marker in forbidden)
