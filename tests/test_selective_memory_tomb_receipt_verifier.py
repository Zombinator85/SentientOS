from __future__ import annotations

import json
import pytest
from pathlib import Path

from sentientos.selective_memory_tomb_receipt_verifier import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_selective_memory_tomb_receipt_verifier,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/selective_memory_tomb_receipt_verifier")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_validates() -> None:
    result = validate_policy(build_default_policy())
    assert result["ok"] is True
    assert result["digest"]


def test_missing_and_invalid_inputs_block() -> None:
    expected = {
        "missing_distillation_packet_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_missing_distillation_packet",
        "invalid_distillation_packet_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_invalid_distillation_packet",
        "missing_receipt_gate_packet_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_missing_receipt_gate_packet",
        "invalid_receipt_gate_packet_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_invalid_receipt_gate_packet",
        "missing_tomb_claim_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_missing_tomb_claim",
        "invalid_tomb_claim_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_invalid_tomb_claim",
    }
    for fixture, status in expected.items():
        assert evaluate_selective_memory_tomb_receipt_verifier(_fixture(fixture)).status == status


def test_valid_claim_types_map_to_outcomes() -> None:
    expected = {
        "valid_tomb_intent_observed_receipt.json": "tomb_receipt_verified",
        "valid_tomb_after_distillation_observed_receipt.json": "tomb_receipt_verified",
        "valid_tomb_without_retention_observed_receipt.json": "tomb_receipt_verified",
        "valid_tomb_deferred_for_writer_receipt.json": "tomb_receipt_deferred_for_operator_review",
        "valid_tomb_rejected_receipt.json": "tomb_receipt_rejected",
        "valid_tomb_noop_receipt.json": "tomb_receipt_noop",
    }
    for fixture, outcome in expected.items():
        result = evaluate_selective_memory_tomb_receipt_verifier(_fixture(fixture))
        assert result.status == "selective_memory_tomb_receipt_verifier_ready"
        assert result.packet is not None
        assert result.packet.records[0].verification_outcome == outcome


def test_blocker_statuses() -> None:
    expected = {
        "digest_mismatch_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_digest_mismatch",
        "decision_mismatch_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_decision_mismatch",
        "gate_not_admissible_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_gate_not_admissible",
        "missing_tomb_intent_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_missing_tomb_intent",
        "tomb_intent_mismatch_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_tomb_intent_mismatch",
        "applied_state_overclaim_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_applied_state_overclaim",
        "claims_memory_mutation_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_claims_memory_mutation",
        "claims_unverified_deletion_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_claims_unverified_deletion",
        "capsule_persistence_claim_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_capsule_persistence_claim",
        "raw_payload_leak_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_raw_payload_leak",
        "authority_smuggling_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_authority_smuggling",
        "prompt_materialization_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_prompt_materialization",
        "external_disclosure_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_external_disclosure",
        "scope_mismatch_blocked.json": "selective_memory_tomb_receipt_verifier_blocked_scope_mismatch",
    }
    for fixture, status in expected.items():
        assert evaluate_selective_memory_tomb_receipt_verifier(_fixture(fixture)).status == status


def test_diagnostic_warnings_require_policy() -> None:
    blocked = _fixture("gate_not_admissible_blocked.json")
    assert "blocked_gate_not_admissible" in evaluate_selective_memory_tomb_receipt_verifier(blocked).status
    diagnostic = _fixture("valid_tomb_blocked_diagnostic_warning.json")
    result = evaluate_selective_memory_tomb_receipt_verifier(diagnostic)
    assert result.status == "selective_memory_tomb_receipt_verifier_ready_with_warnings"
    assert result.packet is not None
    assert result.packet.records[0].verification_outcome == "tomb_receipt_verified_with_warnings"


def test_observed_deletion_can_only_warn_when_policy_allows() -> None:
    payload = _fixture("claims_unverified_deletion_blocked.json")
    payload["policy"] = {"allow_observed_deletion_diagnostic_warning": True}
    result = evaluate_selective_memory_tomb_receipt_verifier(payload)
    assert result.status == "selective_memory_tomb_receipt_verifier_ready_with_warnings"
    assert result.packet is not None
    assert result.packet.records[0].deletion_performed_by_verifier is False


def test_operator_review_cannot_override_hard_blockers() -> None:
    payload = _fixture("authority_smuggling_blocked.json")
    payload["tomb_claim"]["requested_next_actions"] = ["operator_review_required"]
    payload["policy"] = {"allow_operator_review_receipts": True}
    assert evaluate_selective_memory_tomb_receipt_verifier(payload).status == "selective_memory_tomb_receipt_verifier_blocked_authority_smuggling"


def test_mixed_scope_diagnostic_warns_only_when_allowed() -> None:
    allowed = evaluate_selective_memory_tomb_receipt_verifier(_fixture("valid_mixed_scope_diagnostic_warning.json"))
    assert allowed.status == "selective_memory_tomb_receipt_verifier_ready_with_warnings"
    blocked = _fixture("valid_mixed_scope_diagnostic_warning.json")
    blocked.pop("policy")
    assert evaluate_selective_memory_tomb_receipt_verifier(blocked).status == "selective_memory_tomb_receipt_verifier_blocked_scope_mismatch"


def test_successful_outputs_include_invariants_and_forbidden_steps() -> None:
    result = evaluate_selective_memory_tomb_receipt_verifier(_fixture("valid_tomb_after_distillation_observed_receipt.json"))
    assert result.packet is not None
    packet = result.packet.to_dict()
    assert packet["tomb_verifier_is_not_memory_write"] is True
    assert packet["tomb_verifier_is_not_deletion"] is True
    assert packet["tomb_verifier_is_not_tomb_completion"] is True
    assert packet["tomb_verifier_is_not_policy"] is True
    assert packet["tomb_verifier_is_not_authority"] is True
    assert packet["runtime_memory_mutation_enabled"] is False
    assert packet["external_disclosure_enabled"] is False
    required = {
        "delete_memory_now", "purge_memory_now", "write_memory_now", "claim_deletion_performed_by_verifier",
        "claim_tomb_completed_by_verifier", "mutate_vector_index", "assemble_prompt_now", "retrieve_live_context",
        "execute_action_ingress", "infer_truth_from_tomb_receipt", "infer_authority_from_tomb_receipt",
        "convert_tomb_receipt_to_policy", "convert_tomb_verification_to_action", "bypass_receipt_gate", "enable_external_disclosure",
    }
    assert required.issubset(set(FORBIDDEN_NEXT_STEPS))
    assert required.issubset(set(packet["forbidden_next_steps"]))


def test_deterministic_json_digest_and_mixed_counts() -> None:
    payload = _fixture("mixed_tomb_receipt_verification_packet.json")
    first = evaluate_selective_memory_tomb_receipt_verifier(payload).to_dict()
    second = evaluate_selective_memory_tomb_receipt_verifier(payload).to_dict()
    assert first == second
    assert first["report"]["summary_counts"]["claim_count"] == 3
    assert first["report"]["summary_counts"]["tomb_receipt_verified"] == 1
    assert first["report"]["summary_counts"]["tomb_receipt_rejected"] == 1
    assert first["report"]["summary_counts"]["tomb_receipt_noop"] == 1


def test_fixtures_are_metadata_only() -> None:
    forbidden = ["image", "audio", "video", "screenshot", "thumbnail", "encoded_media", "raw_transcript", "provider_prompt", "api_key", "password", "secret"]
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        if "raw_payload_leak_blocked" in path.name:
            continue
        assert not any(token in text for token in forbidden), path
