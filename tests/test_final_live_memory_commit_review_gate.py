from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.final_live_memory_commit_review_gate import (
    FORBIDDEN_NEXT_STEPS,
    INVARIANTS,
    evaluate_final_live_memory_commit_review_gate,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/final_live_memory_commit_review_gate")


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_packet_preserves_final_review_boundaries_and_invariants() -> None:
    result = evaluate_final_live_memory_commit_review_gate(_fixture("valid_ai_capsule_final_live_commit_review_candidate.json"))
    assert result.status == "final_live_commit_review_ready"
    assert result.packet is not None
    packet = result.packet.to_dict()
    for key, expected in INVARIANTS.items():
        assert packet[key] is expected
    record = packet["records"][0]
    assert record["review_decision"] == "final_live_commit_review_ready_for_future_adapter_implementation"
    assert record["future_adapter_implementation_consideration_record"]["real_live_commit_performed"] is False
    assert record["future_adapter_implementation_consideration_record"]["real_adapter_implemented_or_invoked"] is False
    assert record["future_adapter_implementation_consideration_record"]["future_real_live_commit_adapter_required"] is True
    assert record["future_adapter_implementation_consideration_record"]["explicit_operator_runtime_execution_required_later"] is True
    assert record["real_memory_root_access_performed"] is False
    assert record["final_review_is_execution_permission"] is False
    assert record["final_review_is_real_commit"] is False
    forbidden = {"write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "mutate_live_index", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "bypass_real_root_admission_gate", "bypass_final_live_commit_review_gate", "run_real_live_commit_adapter_now", "enable_external_disclosure"}
    assert forbidden.issubset(set(FORBIDDEN_NEXT_STEPS))


def test_policy_validation_default_deny() -> None:
    validation = validate_policy()
    assert validation["status"] == "valid"
    assert validation["policy"]["default_posture"] == "deny"


def test_expected_decision_fixtures() -> None:
    expected = {
        "valid_ai_capsule_final_live_commit_review_candidate.json": "final_live_commit_review_ready",
        "operator_review_final_live_commit_review_candidate.json": "final_live_commit_review_deferred_for_operator_review",
        "noop_final_live_commit_review_candidate.json": "final_live_commit_review_noop",
        "mixed_final_live_commit_review_candidate.json": "final_live_commit_review_ready_with_warnings",
    }
    for fixture, status in expected.items():
        assert evaluate_final_live_memory_commit_review_gate(_fixture(fixture)).status == status


def test_blocker_fixtures_cover_evidence_metadata_and_boundaries() -> None:
    expected_codes = {
        "missing_real_root_admission_packet_blocked.json": "missing_real_root_admission_packet",
        "invalid_real_root_admission_packet_blocked.json": "invalid_real_root_admission_packet",
        "missing_candidate_blocked.json": "missing_final_live_commit_review_candidate",
        "invalid_candidate_blocked.json": "invalid_final_live_commit_review_candidate",
        "real_root_admission_not_ready_blocked.json": "real_root_admission_not_ready",
        "real_root_admission_digest_mismatch_blocked.json": "real_root_admission_digest_mismatch",
        "real_root_admission_decision_mismatch_blocked.json": "real_root_admission_decision_mismatch",
        "sandbox_commit_digest_mismatch_blocked.json": "sandbox_commit_digest_mismatch",
        "sandbox_commit_decision_mismatch_blocked.json": "sandbox_commit_decision_mismatch",
        "missing_sandbox_receipt_manifest_digest_blocked.json": "missing_sandbox_receipt_manifest_digest",
        "missing_sandbox_rollback_manifest_digest_blocked.json": "missing_sandbox_rollback_manifest_digest",
        "missing_sandbox_artifact_plan_blocked.json": "missing_sandbox_artifact_plan",
        "missing_final_operator_review_metadata_blocked.json": "missing_final_operator_review_metadata",
        "missing_future_real_adapter_implementation_metadata_blocked.json": "missing_future_real_adapter_implementation_metadata",
        "missing_live_receipt_schema_metadata_blocked.json": "missing_live_receipt_schema_metadata",
        "missing_live_rollback_schema_metadata_blocked.json": "missing_live_rollback_schema_metadata",
        "missing_post_commit_verification_plan_blocked.json": "missing_post_commit_verification_plan",
        "missing_abort_panic_stop_condition_plan_blocked.json": "missing_abort_panic_stop_condition_plan",
        "real_memory_root_access_claim_blocked.json": "real_memory_root_access_claim",
        "live_write_claim_blocked.json": "live_write_claim",
        "live_delete_claim_blocked.json": "live_delete_claim",
        "live_purge_claim_blocked.json": "live_purge_claim",
        "index_mutation_claim_blocked.json": "index_mutation_claim",
        "sandbox_commit_conversion_claim_blocked.json": "sandbox_commit_conversion_claim",
        "real_root_admission_conversion_claim_blocked.json": "real_root_admission_conversion_claim",
        "final_review_conversion_claim_blocked.json": "final_review_conversion_claim",
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
        result = evaluate_final_live_memory_commit_review_gate(_fixture(fixture))
        assert result.status == "final_live_commit_review_blocked", fixture
        assert result.report.findings[0].code == code
        assert result.packet is None


def test_evaluate_mode_is_deterministic_and_non_mutating(tmp_path: Path) -> None:
    payload = _fixture("valid_ai_capsule_final_live_commit_review_candidate.json")
    probe = tmp_path / "probe"
    probe.mkdir()
    before = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    first = evaluate_final_live_memory_commit_review_gate(payload).to_dict()
    second = evaluate_final_live_memory_commit_review_gate(payload).to_dict()
    after = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    assert first == second
    assert before == after == []


def test_noop_is_deterministic_non_mutating_and_needs_no_non_noop_metadata(tmp_path: Path) -> None:
    first = evaluate_final_live_memory_commit_review_gate(_fixture("noop_final_live_commit_review_candidate.json"))
    second = evaluate_final_live_memory_commit_review_gate(_fixture("noop_final_live_commit_review_candidate.json"))
    assert first.to_dict() == second.to_dict()
    assert first.status == "final_live_commit_review_noop"
    probe = tmp_path / "noop-probe"
    probe.mkdir()
    assert list(probe.rglob("*")) == []


def test_mixed_diagnostics_warn_only_when_policy_allows_them() -> None:
    allowed = evaluate_final_live_memory_commit_review_gate(_fixture("mixed_final_live_commit_review_candidate.json"))
    assert allowed.status == "final_live_commit_review_ready_with_warnings"
    payload = _fixture("mixed_final_live_commit_review_candidate.json")
    payload["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    blocked = evaluate_final_live_memory_commit_review_gate(payload)
    assert blocked.status == "final_live_commit_review_blocked"
    assert blocked.report.findings[0].code == "scope_mismatch"


def test_module_does_not_introduce_unsafe_runtime_surfaces() -> None:
    text = Path("sentientos/final_live_memory_commit_review_gate.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler", "write_text(", "open("]
    assert not any(marker in text for marker in forbidden)
