from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.selective_memory_distillation_contract import (
    FORBIDDEN_NEXT_STEPS,
    SelectiveMemoryDistillationPolicy,
    build_default_policy,
    evaluate_selective_memory_distillation_contract,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/selective_memory_distillation_contract")


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def evaluate(name: str):
    payload = load(name)
    policy_payload = payload.get("policy")
    policy = SelectiveMemoryDistillationPolicy(**policy_payload) if isinstance(policy_payload, dict) else build_default_policy()
    return evaluate_selective_memory_distillation_contract(payload, policy)


def test_default_policy_validates() -> None:
    result = validate_policy(build_default_policy())
    assert result["ok"] is True
    assert result["digest"]


@pytest.mark.parametrize(
    ("fixture", "status"),
    [
        ("missing_records_blocked.json", "selective_memory_distillation_blocked_missing_records"),
        ("invalid_record_blocked.json", "selective_memory_distillation_blocked_invalid_record"),
        ("unknown_record_kind_blocked.json", "selective_memory_distillation_blocked_invalid_record"),
        ("raw_media_payload_blocked.json", "selective_memory_distillation_blocked_raw_media_payload"),
        ("base64_payload_blocked.json", "selective_memory_distillation_blocked_raw_media_payload"),
        ("raw_transcript_blocked.json", "selective_memory_distillation_blocked_raw_media_payload"),
        ("unbounded_affective_context_blocked.json", "selective_memory_distillation_blocked_unbounded_affective_context"),
        ("missing_provenance_blocked.json", "selective_memory_distillation_blocked_missing_provenance"),
        ("authority_smuggling_blocked.json", "selective_memory_distillation_blocked_authority_smuggling"),
        ("prompt_materialization_blocked.json", "selective_memory_distillation_blocked_prompt_materialization"),
        ("runtime_memory_mutation_blocked.json", "selective_memory_distillation_blocked_runtime_memory_mutation"),
        ("external_authority_blocked.json", "selective_memory_distillation_blocked_external_authority"),
        ("tomb_without_receipt_intent_blocked.json", "selective_memory_distillation_blocked_tomb_without_receipt_intent"),
        ("scope_mismatch_blocked.json", "selective_memory_distillation_blocked_scope_mismatch"),
    ],
)
def test_blocked_fixtures(fixture: str, status: str) -> None:
    result = evaluate(fixture)
    assert result.status == status
    assert result.packet is None
    assert result.report.findings


@pytest.mark.parametrize(
    "fixture",
    [
        "valid_ai_symbolic_state_capsule.json",
        "valid_ai_boundary_state_capsule.json",
        "valid_ai_affective_state_capsule.json",
        "valid_ai_embodiment_state_capsule.json",
        "valid_ai_authority_state_capsule.json",
        "valid_ai_proof_state_capsule.json",
        "valid_ai_task_handoff_state_capsule.json",
        "valid_ai_operator_load_state_capsule.json",
        "valid_dual_capsule.json",
        "valid_tomb_after_distillation.json",
        "valid_tomb_without_retention.json",
        "valid_protect_from_forgetting.json",
        "valid_merge_into_existing_capsule.json",
        "valid_defer_for_operator_review.json",
        "valid_retain_raw_temporarily.json",
        "valid_human_summary.json",
        "valid_reject_record.json",
        "valid_no_distillation_needed.json",
    ],
)
def test_valid_records_produce_safe_deterministic_decisions(fixture: str) -> None:
    first = evaluate(fixture)
    second = evaluate(fixture)
    assert first.status == "selective_memory_distillation_ready"
    assert first.digest == second.digest
    assert first.packet is not None
    record = first.packet.records[0]
    assert record.retention_is_not_truth is True
    assert record.distillation_is_not_memory_write is True
    assert record.distillation_is_not_prompt_assembly is True
    assert record.capsule_is_not_policy is True
    assert record.capsule_is_not_authority is True
    assert record.deletion_recommendation_is_not_deletion is True
    assert record.external_disclosure_enabled is False
    assert record.runtime_memory_mutation_enabled is False
    assert record.prompt_materialization_enabled is False
    assert record.remote_service_enabled is False
    for step in (
        "delete_memory_now",
        "purge_memory_now",
        "write_memory_now",
        "mutate_vector_index",
        "call_append_memory",
        "call_purge_memory",
        "call_curate_memory",
        "assemble_prompt_now",
        "retrieve_live_context",
        "call_llm_provider",
        "call_network_api",
        "infer_truth_from_retention",
        "infer_authority_from_memory",
        "convert_capsule_to_policy",
        "convert_distillation_to_action",
        "enable_external_disclosure",
    ):
        assert step in record.forbidden_next_steps
        assert step in FORBIDDEN_NEXT_STEPS


def test_ai_capsules_are_compact_typed_symbol_limited_and_safe() -> None:
    result = evaluate("valid_dual_capsule.json")
    assert result.packet is not None
    capsule = result.packet.records[0].ai_capsule
    assert capsule is not None
    assert capsule.capsule_type == "ai_mixed_capsule"
    assert 1 <= len(capsule.symbols) <= build_default_policy().ai_capsule_symbol_limit
    assert capsule.digest
    forbidden = " ".join(capsule.symbols).lower()
    assert "raw_transcript" not in forbidden
    assert "provider_prompt" not in forbidden
    assert "secret" not in forbidden
    assert "base64" not in forbidden


def test_affective_embodiment_authority_are_descriptive_only() -> None:
    affect = evaluate("valid_ai_affective_state_capsule.json")
    embodiment = evaluate("valid_ai_embodiment_state_capsule.json")
    authority = evaluate("valid_ai_authority_state_capsule.json")
    assert affect.status == embodiment.status == authority.status == "selective_memory_distillation_ready"
    assert evaluate("unbounded_affective_context_blocked.json").status.endswith("unbounded_affective_context")
    assert evaluate("authority_smuggling_blocked.json").status.endswith("authority_smuggling")


def test_tomb_protect_and_merge_do_not_mutate_memory() -> None:
    tomb = evaluate("valid_tomb_without_retention.json")
    protect = evaluate("valid_protect_from_forgetting.json")
    merge = evaluate("valid_merge_into_existing_capsule.json")
    assert tomb.packet is not None and tomb.packet.records[0].tomb_intent is not None
    assert tomb.packet.records[0].tomb_intent.deletion_performed is False
    for result in (tomb, protect, merge):
        assert result.packet is not None
        record = result.packet.records[0]
        assert record.runtime_memory_mutation_enabled is False
        assert "write_memory_now" in record.forbidden_next_steps
        assert "mutate_distilled_memory" in record.forbidden_next_steps


def test_missing_provenance_warns_by_default_and_mixed_scope_warns_when_allowed() -> None:
    missing = evaluate("missing_provenance_warning.json")
    assert missing.status == "selective_memory_distillation_ready_with_warnings"
    assert [f.code for f in missing.report.findings] == ["missing_provenance"]
    mixed = evaluate("valid_mixed_scope_diagnostic_warning.json")
    assert mixed.status == "selective_memory_distillation_ready_with_warnings"
    assert "scope_mismatch" in [f.code for f in mixed.report.findings]


def test_mixed_distillation_packet_counts_and_digest_are_deterministic() -> None:
    first = evaluate("mixed_distillation_packet.json")
    second = evaluate("mixed_distillation_packet.json")
    assert first.status == "selective_memory_distillation_ready"
    assert first.digest == second.digest
    assert first.report.summary_counts["record_count"] == 3
    assert first.report.summary_counts["retain_raw_temporarily"] == 1
    assert first.report.summary_counts["distill_to_ai_capsule"] == 1
    assert first.report.summary_counts["protect_from_forgetting"] == 1


def test_fixture_payloads_are_metadata_only_except_negative_payload_fixtures() -> None:
    allowed_negative = {"raw_media_payload_blocked.json", "base64_payload_blocked.json", "raw_transcript_blocked.json"}
    forbidden_terms = ("/live/memory", "provider_prompt", "api_key", "password", "secret")
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        if path.name not in allowed_negative:
            assert "base64" not in text
            assert "raw_transcript" not in text
            assert "data:image" not in text
        for term in forbidden_terms:
            assert term not in text
