from __future__ import annotations

from typing import Any


def bounded_orchestration_pattern_note() -> dict[str, Any]:
    """Compact developer/operator note for bounded orchestration venue onboarding."""

    return {
        "title": "bounded_orchestration_pattern",
        "what_it_is": (
            "A compact constitutional pattern: delegated judgment -> typed orchestration intent -> bounded handoff -> "
            "result resolution -> retrospective review -> operator-attention recommendation -> bounded next-venue recommendation, "
            "with explicit non-sovereign boundaries."
        ),
        "reusable_parts": [
            "intent typing + executability classification",
            "append-only intent/handoff ledgers",
            "handoff-to-result linkage fields",
            "bounded retrospective review and operator-attention recommendation",
            "bounded next-venue recommendation derived from delegated judgment + retrospective signals",
            "explicit anti-sovereignty payload fields",
        ],
        "next_venue_recommendation": {
            "what_it_means": "A bounded recommendation for which existing venue is likely preferable next, not a planner or router.",
            "derived_from": [
                "delegated_judgment.recommended_venue and escalation_classification",
                "orchestration_outcome_review",
                "orchestration_venue_mix_review",
                "orchestration_operator_attention_recommendation",
            ],
            "return_values": [
                "prefer_internal_execution",
                "prefer_codex_implementation",
                "prefer_deep_research_audit",
                "prefer_operator_decision",
                "hold_current_venue_mix",
                "insufficient_context",
            ],
            "difference_from_delegated_judgment": (
                "delegated_judgment proposes venue from current slice evidence; next-venue recommendation applies conservative "
                "self-correction using recent orchestration outcome and venue-mix behavior."
            ),
            "explicitly_does_not_do": [
                "does_not_execute_or_route_work",
                "does_not_override_delegated_judgment",
                "does_not_add_new_venues_or_authority_surface",
            ],
        },
        "onboarding_checklist": [
            "define venue_id with supported_intent_kinds and executability_classes",
            "declare handoff_substrate and append-only result_source",
            "define required linkage fields from intent -> handoff -> result",
            "preserve non_authoritative decision_power=none boundaries",
            "add focused tests for required fields and missing-field detection",
        ],
        "what_not_to_do": [
            "do not add direct external actuation by default",
            "do not create a new sovereign or hidden orchestrator authority",
            "do not bypass admission/result linkage proof surfaces",
            "do not expand venue coverage without scaffold + tests",
        ],
        "current_staged_external_venues": [
            "codex_implementation",
            "deep_research_audit",
        ],
    }
