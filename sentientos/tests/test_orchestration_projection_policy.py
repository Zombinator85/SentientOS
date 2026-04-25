from __future__ import annotations

from sentientos.orchestration_spine.projection import policy_helpers


def test_attention_projection_mixed_light_block_observe() -> None:
    projection = policy_helpers.derive_attention_projection(
        {
            "review_classification": "mixed_orchestration_stress",
            "records_considered": 4,
            "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
            "recent_outcome_counts": {"handoff_not_admitted": 1},
        },
        allowed_recommendations={
            "none",
            "observe",
            "inspect_handoff_blocks",
            "inspect_execution_failures",
            "inspect_pending_stall",
            "review_mixed_orchestration_stress",
            "insufficient_context",
        },
    )

    assert projection["operator_attention_recommendation"] == "observe"


def test_next_venue_projection_escalates_operator() -> None:
    projection = policy_helpers.derive_next_venue_projection(
        {"recommended_venue": "operator_decision_required", "escalation_classification": ""},
        {"review_classification": "clean_recent_orchestration", "records_considered": 8, "condition_flags": {}},
        {"review_classification": "balanced_recent_venue_mix", "records_considered": 8},
        {"operator_attention_recommendation": "none"},
        allowed_recommendations={
            "prefer_internal_execution",
            "prefer_codex_implementation",
            "prefer_deep_research_audit",
            "prefer_operator_decision",
            "hold_current_venue_mix",
            "insufficient_context",
        },
        allowed_relations={"affirming", "nudging", "holding", "escalating", "insufficient_context"},
    )

    assert projection["next_venue_recommendation"] == "prefer_operator_decision"
    assert projection["relation_to_delegated_judgment"] == "escalating"


def test_next_venue_projection_affirms_internal() -> None:
    projection = policy_helpers.derive_next_venue_projection(
        {"recommended_venue": "internal_direct_execution", "escalation_classification": ""},
        {
            "review_classification": "clean_recent_orchestration",
            "records_considered": 4,
            "condition_flags": {"blocked_heavy": False, "failure_heavy": False, "stall_heavy": False},
        },
        {"review_classification": "balanced_recent_venue_mix", "records_considered": 4},
        {"operator_attention_recommendation": "observe"},
        allowed_recommendations={
            "prefer_internal_execution",
            "prefer_codex_implementation",
            "prefer_deep_research_audit",
            "prefer_operator_decision",
            "hold_current_venue_mix",
            "insufficient_context",
        },
        allowed_relations={"affirming", "nudging", "holding", "escalating", "insufficient_context"},
    )

    assert projection["next_venue_recommendation"] == "prefer_internal_execution"
    assert projection["relation_to_delegated_judgment"] == "affirming"
