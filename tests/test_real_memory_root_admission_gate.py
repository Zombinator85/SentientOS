from __future__ import annotations

import json
import pytest
from pathlib import Path

from sentientos.real_memory_root_admission_gate import (
    FORBIDDEN_NEXT_STEPS,
    evaluate_real_memory_root_admission_gate,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/real_memory_root_admission_gate")


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_candidate_builds_metadata_only_admission_packet() -> None:
    result = evaluate_real_memory_root_admission_gate(_fixture("valid_ai_capsule_real_root_admission_candidate.json"))
    assert result.status == "real_root_admission_ready"
    assert result.packet is not None
    packet = result.packet.to_dict()
    for key in [
        "real_root_admission_is_not_memory_write",
        "real_root_admission_is_not_memory_deletion",
        "real_root_admission_is_not_memory_purge",
        "real_root_admission_is_not_index_mutation",
        "real_root_admission_is_not_capsule_persistence",
        "real_root_admission_is_not_prompt_assembly",
        "real_root_admission_is_not_execution",
        "real_root_admission_is_not_live_commit",
        "real_root_admission_is_not_truth",
        "real_root_admission_is_not_policy",
        "real_root_admission_is_not_authority",
        "real_root_admission_is_not_consent",
        "real_root_admission_does_not_execute_action",
        "real_root_admission_does_not_disclose_externally",
        "future_real_live_commit_adapter_required",
        "final_operator_review_required",
    ]:
        assert packet[key] is True
    for key in [
        "real_memory_root_access_enabled",
        "live_memory_write_enabled",
        "live_memory_deletion_enabled",
        "live_memory_purge_enabled",
        "live_index_mutation_enabled",
        "prompt_materialization_enabled",
        "external_disclosure_enabled",
        "remote_service_enabled",
    ]:
        assert packet[key] is False
    record = packet["records"][0]
    assert record["admission_decision"] == "real_root_admission_candidate_ready_for_future_adapter"
    assert record["real_memory_root_access_performed"] is False
    assert record["future_adapter_consideration_record"]["real_live_commit_performed"] is False
    assert {"write_live_memory_now", "delete_live_memory_now", "purge_live_memory_now", "mutate_live_index", "assemble_prompt_now", "retrieve_live_context", "execute_action_ingress", "bypass_real_root_admission_gate", "enable_external_disclosure"}.issubset(set(FORBIDDEN_NEXT_STEPS))


def test_expected_decision_fixtures() -> None:
    expected = {
        "valid_ai_capsule_real_root_admission_candidate.json": "real_root_admission_ready",
        "operator_review_real_root_admission_candidate.json": "real_root_admission_deferred_for_operator_review",
        "noop_real_root_admission_candidate.json": "real_root_admission_noop",
        "mixed_real_root_admission_candidate.json": "real_root_admission_ready_with_warnings",
    }
    for fixture, status in expected.items():
        assert evaluate_real_memory_root_admission_gate(_fixture(fixture)).status == status


def test_blocker_fixtures_cover_evidence_and_boundaries() -> None:
    expected_codes = {
        "missing_sandbox_commit_packet_blocked.json": "missing_sandbox_commit_packet",
        "invalid_sandbox_commit_packet_blocked.json": "invalid_sandbox_commit_packet",
        "missing_candidate_blocked.json": "missing_real_root_admission_candidate",
        "invalid_candidate_blocked.json": "invalid_real_root_admission_candidate",
        "sandbox_commit_not_ready_blocked.json": "sandbox_commit_not_ready",
        "digest_mismatch_blocked.json": "sandbox_commit_digest_mismatch",
        "decision_mismatch_blocked.json": "sandbox_commit_decision_mismatch",
        "missing_receipt_manifest_digest_blocked.json": "missing_sandbox_receipt_manifest_digest",
        "missing_rollback_manifest_digest_blocked.json": "missing_sandbox_rollback_manifest_digest",
        "missing_artifact_plan_blocked.json": "missing_sandbox_artifact_plan",
        "real_memory_root_access_claim_blocked.json": "real_memory_root_access_claim",
        "live_write_claim_blocked.json": "live_write_claim",
        "live_delete_claim_blocked.json": "live_delete_claim",
        "live_purge_claim_blocked.json": "live_purge_claim",
        "index_mutation_claim_blocked.json": "index_mutation_claim",
        "path_traversal_blocked.json": "path_traversal",
        "unsafe_root_metadata_blocked.json": "unsafe_real_root_path_metadata",
        "sandbox_commit_conversion_claim_blocked.json": "sandbox_commit_conversion_claim",
        "sandbox_receipt_conversion_claim_blocked.json": "sandbox_receipt_conversion_claim",
        "sandbox_rollback_conversion_claim_blocked.json": "sandbox_rollback_conversion_claim",
        "prompt_materialization_blocked.json": "prompt_materialization",
        "live_context_retrieval_blocked.json": "live_context_retrieval",
        "action_execution_blocked.json": "action_execution",
        "external_disclosure_blocked.json": "external_disclosure",
        "authority_smuggling_blocked.json": "authority_smuggling",
        "consent_smuggling_blocked.json": "consent_smuggling",
        "policy_smuggling_blocked.json": "policy_smuggling",
        "truth_smuggling_blocked.json": "truth_smuggling",
        "raw_payload_leak_blocked.json": "raw_payload_leak",
    }
    for fixture, code in expected_codes.items():
        result = evaluate_real_memory_root_admission_gate(_fixture(fixture))
        assert result.status == "real_root_admission_blocked", fixture
        assert result.report.findings[0].code == code
        assert result.packet is None


def test_evaluate_mode_is_deterministic_and_non_mutating(tmp_path: Path) -> None:
    payload = _fixture("valid_ai_capsule_real_root_admission_candidate.json")
    probe = tmp_path / "probe"
    probe.mkdir()
    before = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    first = evaluate_real_memory_root_admission_gate(payload).to_dict()
    second = evaluate_real_memory_root_admission_gate(payload).to_dict()
    after = sorted(p.relative_to(probe) for p in probe.rglob("*"))
    assert first == second
    assert before == after == []


def test_noop_is_deterministic_non_mutating_and_needs_no_manifest_digests(tmp_path: Path) -> None:
    first = evaluate_real_memory_root_admission_gate(_fixture("noop_real_root_admission_candidate.json"))
    second = evaluate_real_memory_root_admission_gate(_fixture("noop_real_root_admission_candidate.json"))
    assert first.to_dict() == second.to_dict()
    assert first.status == "real_root_admission_noop"
    probe = tmp_path / "noop-probe"
    probe.mkdir()
    assert list(probe.rglob("*")) == []


def test_mixed_diagnostics_warn_only_when_policy_allows_them() -> None:
    allowed = evaluate_real_memory_root_admission_gate(_fixture("mixed_real_root_admission_candidate.json"))
    assert allowed.status == "real_root_admission_ready_with_warnings"
    payload = _fixture("mixed_real_root_admission_candidate.json")
    payload["policy"] = {"allow_mixed_scope_diagnostic_packet": False}
    blocked = evaluate_real_memory_root_admission_gate(payload)
    assert blocked.status == "real_root_admission_blocked"
    assert blocked.report.findings[0].code == "scope_mismatch"


def test_module_does_not_introduce_unsafe_runtime_surfaces() -> None:
    text = Path("sentientos/real_memory_root_admission_gate.py").read_text(encoding="utf-8")
    forbidden = ["append_memory(", "purge_memory(", "apply_forgetting_curve(", "requests.", "subprocess.", "openai", "prompt_assembler", "write_text(", "open("]
    assert not any(marker in text for marker in forbidden)
