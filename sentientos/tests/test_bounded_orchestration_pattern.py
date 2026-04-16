from __future__ import annotations

from sentientos.bounded_orchestration_pattern import (
    bounded_orchestration_layers,
    bounded_orchestration_venue_scaffold,
    codex_implementation_bounded_venue,
    next_bounded_venue_candidate_assessment,
    validate_bounded_orchestration_venue,
)


def test_scaffold_is_coherent_and_machine_readable() -> None:
    scaffold = bounded_orchestration_venue_scaffold()

    assert scaffold["schema_version"] == "bounded_orchestration_venue_scaffold.v1"
    assert scaffold["pattern_scope"] == "bounded_orchestration_venue_expansion"
    reference = scaffold["current_reference_venue"]
    assert reference["venue_id"] == "internal_task_admission"
    assert "internal_maintenance_execution" in reference["supported_intent_kinds"]
    assert reference["handoff_substrate"] == "task_admission_executor"


def test_required_fields_for_candidate_venue_are_enforced() -> None:
    candidate = {
        "venue_id": "candidate",
        "supported_intent_kinds": ["codex_work_order"],
        "executability_classes": ["stageable_external_work_order"],
        "handoff_substrate": "staged_external_handoff",
        "result_source": {"surface": "glow/orchestration/external_results.jsonl"},
        "required_linkage_fields": {
            "intent_to_handoff": ["intent_id"],
            "handoff_to_admission": ["handoff_id"],
            "admission_to_result": ["result_id"],
        },
        "review_attention_capabilities": {"outcome_review_enabled": True, "attention_recommendation_enabled": True},
        "anti_sovereignty_guarantees": {"non_authoritative": True, "decision_power": "none"},
    }

    assert validate_bounded_orchestration_venue(candidate) == []


def test_required_vs_optional_vs_internal_specific_layers_are_distinguishable() -> None:
    layers = bounded_orchestration_layers()
    by_layer = {row["layer"]: row["classification"] for row in layers}

    assert by_layer["delegated_judgment_input"] == "required_for_new_venue"
    assert by_layer["retrospective_orchestration_review"] == "optional_or_advanced"
    assert by_layer["task_admission_executor_noop_task_materialization"] == "current_internal_task_admission_specific"


def test_missing_required_pattern_elements_are_detectable() -> None:
    missing = validate_bounded_orchestration_venue(
        {
            "venue_id": "broken_candidate",
            "supported_intent_kinds": ["codex_work_order"],
            "anti_sovereignty_guarantees": {"non_authoritative": False, "decision_power": "full"},
        }
    )

    assert "executability_classes" in missing
    assert "handoff_substrate" in missing
    assert "required_linkage_fields" in missing
    assert "anti_sovereignty_guarantees.non_authoritative" in missing
    assert "anti_sovereignty_guarantees.decision_power" in missing


def test_scaffold_introduces_no_new_authority_or_execution_behavior() -> None:
    scaffold = bounded_orchestration_venue_scaffold()
    reference = scaffold["current_reference_venue"]
    guarantees = reference["anti_sovereignty_guarantees"]

    assert guarantees["non_authoritative"] is True
    assert guarantees["decision_power"] == "none"
    assert guarantees["does_not_invoke_external_tools"] is True
    assert guarantees["does_not_change_admission_or_execution"] is True


def test_next_candidate_assessment_tracks_codex_as_onboarded_next_venue() -> None:
    assessment = next_bounded_venue_candidate_assessment()

    assert assessment["recommended_next_venue"] == "codex_implementation"
    assert assessment["not_implemented_in_this_pass"] is False
    assert assessment["relative_difficulty_vs_current_internal_venue"] == "harder_than_internal_task_admission"


def test_codex_onboarded_venue_payload_passes_scaffold_validation() -> None:
    candidate = codex_implementation_bounded_venue()

    assert candidate["venue_id"] == "codex_implementation"
    assert "codex_work_order" in candidate["supported_intent_kinds"]
    assert "stageable_external_work_order" in candidate["executability_classes"]
    assert validate_bounded_orchestration_venue(candidate) == []
