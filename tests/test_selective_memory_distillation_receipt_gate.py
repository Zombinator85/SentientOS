from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.selective_memory_distillation_receipt_gate import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_selective_memory_distillation_receipt_gate,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/selective_memory_distillation_receipt_gate")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_validates() -> None:
    assert validate_policy(build_default_policy())["ok"] is True


@pytest.mark.parametrize(
    ("fixture", "status"),
    [
        ("missing_distillation_packet_blocked.json", "selective_memory_receipt_gate_blocked_missing_distillation_packet"),
        ("invalid_distillation_packet_blocked.json", "selective_memory_receipt_gate_blocked_invalid_distillation_packet"),
        ("missing_receipt_candidate_blocked.json", "selective_memory_receipt_gate_blocked_missing_receipt_candidate"),
        ("invalid_receipt_candidate_blocked.json", "selective_memory_receipt_gate_blocked_invalid_receipt_candidate"),
        ("decision_mismatch_blocked.json", "selective_memory_receipt_gate_blocked_decision_mismatch"),
        ("digest_mismatch_blocked.json", "selective_memory_receipt_gate_blocked_digest_mismatch"),
        ("tomb_intent_missing_blocked.json", "selective_memory_receipt_gate_blocked_tomb_intent_missing"),
        ("tomb_receipt_claimed_blocked.json", "selective_memory_receipt_gate_blocked_tomb_receipt_claimed"),
        ("capsule_payload_unsafe_blocked.json", "selective_memory_receipt_gate_blocked_capsule_payload_unsafe"),
        ("raw_payload_leak_blocked.json", "selective_memory_receipt_gate_blocked_raw_payload_leak"),
        ("authority_smuggling_blocked.json", "selective_memory_receipt_gate_blocked_authority_smuggling"),
        ("prompt_materialization_blocked.json", "selective_memory_receipt_gate_blocked_prompt_materialization"),
        ("runtime_memory_mutation_blocked.json", "selective_memory_receipt_gate_blocked_runtime_memory_mutation"),
        ("external_disclosure_blocked.json", "selective_memory_receipt_gate_blocked_external_disclosure"),
        ("scope_mismatch_blocked.json", "selective_memory_receipt_gate_blocked_scope_mismatch"),
    ],
)
def test_blocked_fixtures(fixture: str, status: str) -> None:
    result = evaluate_selective_memory_distillation_receipt_gate(_fixture(fixture))
    assert result.status == status
    assert result.packet is None


@pytest.mark.parametrize(
    ("fixture", "decision"),
    [
        ("valid_ai_capsule_write_receipt_candidate.json", "receipt_candidate_admissible"),
        ("valid_human_summary_write_receipt_candidate.json", "receipt_candidate_admissible"),
        ("valid_dual_capsule_write_receipt_candidate.json", "receipt_candidate_admissible"),
        ("valid_tomb_intent_receipt_candidate.json", "receipt_candidate_admissible"),
        ("valid_tomb_after_distillation_receipt_candidate.json", "receipt_candidate_admissible"),
        ("valid_protect_memory_receipt_candidate.json", "receipt_candidate_admissible"),
        ("valid_merge_capsule_receipt_candidate.json", "receipt_candidate_admissible"),
        ("valid_operator_review_receipt_candidate.json", "receipt_candidate_deferred_for_operator_review"),
        ("valid_defer_receipt_candidate.json", "receipt_candidate_deferred_for_operator_review"),
        ("valid_reject_record_receipt_candidate.json", "receipt_candidate_rejected"),
        ("valid_noop_receipt_candidate.json", "receipt_candidate_noop"),
    ],
)
def test_valid_receipt_candidates_map_to_gate_decisions(fixture: str, decision: str) -> None:
    result = evaluate_selective_memory_distillation_receipt_gate(_fixture(fixture))
    assert result.status == "selective_memory_receipt_gate_ready"
    assert result.packet is not None
    assert result.packet.decisions[0].gate_decision == decision
    assert result.packet.receipt_gate_is_not_memory_write is True
    assert result.packet.receipt_gate_is_not_deletion is True
    assert result.packet.receipt_gate_is_not_policy is True
    assert result.packet.receipt_gate_is_not_authority is True
    assert result.packet.prompt_materialization_enabled is False
    assert result.packet.external_disclosure_enabled is False
    assert result.packet.remote_service_enabled is False
    for forbidden in [
        "write_memory_now",
        "delete_memory_now",
        "purge_memory_now",
        "claim_tomb_completed",
        "claim_capsule_written",
        "mutate_vector_index",
        "assemble_prompt_now",
        "retrieve_live_context",
        "execute_action_ingress",
        "infer_truth_from_receipt",
        "infer_authority_from_receipt",
        "convert_receipt_to_policy",
        "convert_receipt_gate_to_action",
        "enable_external_disclosure",
    ]:
        assert forbidden in result.packet.forbidden_next_steps
        assert forbidden in FORBIDDEN_NEXT_STEPS


def test_mixed_scope_diagnostic_packet_warns_only_when_allowed() -> None:
    allowed = evaluate_selective_memory_distillation_receipt_gate(_fixture("mixed_receipt_gate_packet.json"))
    assert allowed.status == "selective_memory_receipt_gate_ready_with_warnings"
    assert allowed.packet is not None
    assert allowed.report.summary_counts["candidate_count"] == 2
    blocked_payload = _fixture("mixed_receipt_gate_packet.json")
    blocked_payload.pop("policy", None)
    blocked = evaluate_selective_memory_distillation_receipt_gate(blocked_payload)
    assert blocked.status == "selective_memory_receipt_gate_blocked_scope_mismatch"


def test_deterministic_digest_output() -> None:
    payload = _fixture("mixed_receipt_gate_packet.json")
    first = evaluate_selective_memory_distillation_receipt_gate(payload).to_dict()
    second = evaluate_selective_memory_distillation_receipt_gate(payload).to_dict()
    assert first == second
    assert len(first["digest"]) == 64


def test_fixture_payloads_are_metadata_only() -> None:
    forbidden = ("raw transcript:", "provider_prompt", "api_key", "password", "data:image/", "data:audio/", "data:video/")
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        if path.name in {"raw_payload_leak_blocked.json", "capsule_payload_unsafe_blocked.json"}:
            continue
        assert not any(marker in text for marker in forbidden), path.name
