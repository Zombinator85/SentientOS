from __future__ import annotations

import json
import pytest
from pathlib import Path

from sentientos.real_live_memory_commit_adapter_readiness_envelope import (
    evaluate_real_live_memory_commit_adapter_readiness_envelope,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURE_ROOT = Path("tests/fixtures/real_live_memory_commit_adapter_readiness_envelope")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_valid_candidate_emits_disabled_readiness_envelopes() -> None:
    result = evaluate_real_live_memory_commit_adapter_readiness_envelope(_fixture("valid_ai_capsule_live_adapter_readiness_candidate.json"))
    assert result.status == "live_adapter_readiness_ready"
    assert result.packet is not None
    packet = result.packet.to_dict()
    assert packet["live_adapter_readiness_is_not_memory_write"] is True
    assert packet["live_adapter_readiness_is_not_live_commit_execution"] is True
    assert packet["adapter_runtime_execution_enabled"] is False
    assert packet["future_explicit_runtime_execution_gate_required"] is True
    assert packet["future_operator_runtime_confirmation_required"] is True
    record = packet["records"][0]
    assert record["final_review_digest"] == _fixture("valid_ai_capsule_live_adapter_readiness_candidate.json")["live_adapter_readiness_candidates"][0]["claimed_final_review_digest"]
    assert record["hypothetical_live_receipt_envelope"]["live_receipt_emitted"] is False
    assert record["hypothetical_rollback_envelope"]["rollback_applied"] is False
    assert record["post_commit_verification_envelope"]["post_commit_verification_performed"] is False
    assert record["adapter_readiness_future_runtime_gate_record"]["adapter_runtime_execution_enabled"] is False


def test_policy_preserves_disabled_default_invariants() -> None:
    result = validate_policy()
    assert result["status"] == "valid"
    bad = validate_policy({"default_posture": "allow", "adapter_runtime_execution_enabled": True})
    assert bad["status"] == "invalid"
    assert {f["code"] for f in bad["findings"]} >= {"default_posture_not_deny", "invariant_adapter_runtime_execution_enabled_changed"}


def test_candidate_type_statuses_are_deterministic() -> None:
    expected = {
        "valid_ai_capsule_live_adapter_readiness_candidate.json": "live_adapter_readiness_ready",
        "valid_human_summary_live_adapter_readiness_candidate.json": "live_adapter_readiness_ready",
        "valid_dual_capsule_live_adapter_readiness_candidate.json": "live_adapter_readiness_ready",
        "valid_protect_receipt_live_adapter_readiness_candidate.json": "live_adapter_readiness_ready",
        "valid_merge_receipt_live_adapter_readiness_candidate.json": "live_adapter_readiness_ready",
        "valid_tomb_archive_live_adapter_readiness_candidate.json": "live_adapter_readiness_ready",
        "valid_tomb_deferred_live_adapter_readiness_candidate.json": "live_adapter_readiness_ready",
        "operator_review_live_adapter_readiness_candidate.json": "live_adapter_readiness_deferred_for_operator_review",
        "noop_live_adapter_readiness_candidate.json": "live_adapter_readiness_noop",
        "mixed_live_adapter_readiness_candidate.json": "live_adapter_readiness_ready_with_warnings",
    }
    for fixture, status in expected.items():
        assert evaluate_real_live_memory_commit_adapter_readiness_envelope(_fixture(fixture)).status == status, fixture


def test_blocker_fixtures_cover_evidence_metadata_and_boundaries() -> None:
    expected_codes = {
        "missing_final_review_packet_blocked.json": "missing_final_review_packet",
        "invalid_final_review_packet_blocked.json": "invalid_final_review_packet",
        "missing_candidate_blocked.json": "missing_live_adapter_readiness_candidate",
        "invalid_candidate_blocked.json": "invalid_live_adapter_readiness_candidate",
        "final_review_not_ready_blocked.json": "final_review_not_ready",
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
        "missing_real_adapter_implementation_metadata_blocked.json": "missing_real_adapter_implementation_metadata",
        "real_memory_root_access_claim_blocked.json": "real_memory_root_access_claim",
        "live_write_claim_blocked.json": "live_write_claim",
        "live_delete_claim_blocked.json": "live_delete_claim",
        "live_purge_claim_blocked.json": "live_purge_claim",
        "index_mutation_claim_blocked.json": "index_mutation_claim",
        "capsule_persistence_claim_blocked.json": "capsule_persistence_claim",
        "tomb_completion_claim_blocked.json": "tomb_completion_claim",
        "protection_application_claim_blocked.json": "protection_application_claim",
        "merge_application_claim_blocked.json": "merge_application_claim",
        "adapter_readiness_execution_claim_blocked.json": "adapter_readiness_execution_claim",
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
        result = evaluate_real_live_memory_commit_adapter_readiness_envelope(_fixture(fixture))
        assert result.status == "live_adapter_readiness_blocked", fixture
        assert result.report.findings[0].code == code, fixture
        assert result.packet is None


def test_evaluate_mode_is_deterministic_and_non_mutating(tmp_path: Path) -> None:
    payload = _fixture("valid_ai_capsule_live_adapter_readiness_candidate.json")
    probe = tmp_path / "probe"; probe.mkdir()
    before = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    first = evaluate_real_live_memory_commit_adapter_readiness_envelope(payload).to_dict()
    second = evaluate_real_live_memory_commit_adapter_readiness_envelope(payload).to_dict()
    after = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    assert first == second
    assert before == after == []


def test_noop_is_deterministic_non_mutating_and_needs_no_non_noop_metadata(tmp_path: Path) -> None:
    first = evaluate_real_live_memory_commit_adapter_readiness_envelope(_fixture("noop_live_adapter_readiness_candidate.json"))
    second = evaluate_real_live_memory_commit_adapter_readiness_envelope(_fixture("noop_live_adapter_readiness_candidate.json"))
    assert first.to_dict() == second.to_dict()
    assert first.status == "live_adapter_readiness_noop"
    probe = tmp_path / "noop-probe"; probe.mkdir()
    assert list(probe.rglob("*")) == []


def test_mixed_diagnostics_warn_only_when_policy_allows_them() -> None:
    allowed = evaluate_real_live_memory_commit_adapter_readiness_envelope(_fixture("mixed_live_adapter_readiness_candidate.json"))
    assert allowed.status == "live_adapter_readiness_ready_with_warnings"
    payload = _fixture("mixed_live_adapter_readiness_candidate.json")
    payload["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    blocked = evaluate_real_live_memory_commit_adapter_readiness_envelope(payload)
    assert blocked.status == "live_adapter_readiness_blocked"
    assert blocked.report.findings[0].code == "scope_mismatch"


def test_module_does_not_introduce_unsafe_runtime_surfaces() -> None:
    text = Path("sentientos/real_live_memory_commit_adapter_readiness_envelope.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler", "write_text(", "open("]
    assert not any(marker in text for marker in forbidden)
