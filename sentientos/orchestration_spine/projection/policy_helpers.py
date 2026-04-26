from __future__ import annotations

"""Policy projection helpers for bounded orchestration recommendations.

These helpers compute derived recommendation projections only. Kernel callers
remain responsible for canonical schema shaping and anti-sovereignty envelopes.
They must not own venue authority, admission authority, lifecycle truth, or
execution routing.
"""

from typing import Any, Mapping

POLICY_PROJECTION_FAMILY_RECOMMENDATION = (
    "derive_attention_projection",
    "derive_next_venue_projection",
)


def derive_attention_projection(
    outcome_review: Mapping[str, Any],
    *,
    allowed_recommendations: set[str],
) -> dict[str, Any]:
    """Derive bounded operator-attention projection from outcome review state."""

    review_classification = str(outcome_review.get("review_classification") or "insufficient_history")
    records_considered = int(outcome_review.get("records_considered") or 0)
    condition_flags_raw = outcome_review.get("condition_flags")
    condition_flags = condition_flags_raw if isinstance(condition_flags_raw, Mapping) else {}
    blocked_heavy = bool(condition_flags.get("blocked_heavy"))
    failure_heavy = bool(condition_flags.get("failure_heavy"))
    stall_heavy = bool(condition_flags.get("stall_heavy"))
    recent_counts_raw = outcome_review.get("recent_outcome_counts")
    recent_outcome_counts = recent_counts_raw if isinstance(recent_counts_raw, Mapping) else {}
    handoff_not_admitted = int(recent_outcome_counts.get("handoff_not_admitted") or 0)
    light_block_pattern = handoff_not_admitted >= 1 and not blocked_heavy

    recommendation = "insufficient_context"
    rationale = "insufficient_orchestration_history_for_confident_attention_guidance"

    if review_classification == "clean_recent_orchestration":
        recommendation = "none"
        rationale = "recent_internal_orchestration_outcomes_are_clean_and_loop_closure_is_healthy"
    elif review_classification == "handoff_block_heavy" or blocked_heavy:
        recommendation = "inspect_handoff_blocks"
        rationale = "recent_history_shows_block_heavy_internal_handoff_behavior"
    elif review_classification == "execution_failure_heavy" or failure_heavy:
        recommendation = "inspect_execution_failures"
        rationale = "recent_history_shows_execution_failure_heavy_pattern_after_admission"
    elif review_classification == "pending_stall_pattern" or stall_heavy:
        recommendation = "inspect_pending_stall"
        rationale = "recent_history_shows_pending_or_missing_result_stall_pattern"
    elif review_classification == "mixed_orchestration_stress":
        recommendation = "review_mixed_orchestration_stress"
        rationale = "recent_history_shows_mixed_orchestration_stress_needing_human_interpretation"
    elif review_classification == "insufficient_history":
        recommendation = "insufficient_context"
        rationale = "insufficient_recent_orchestration_history_for_specific_attention_recommendation"
    elif light_block_pattern and records_considered >= 3 and review_classification not in {"clean_recent_orchestration"}:
        recommendation = "observe"
        rationale = "light_non_failure_handoff_block_pattern_detected_observe_before_deeper_intervention"

    if (
        light_block_pattern
        and review_classification == "mixed_orchestration_stress"
        and recommendation == "review_mixed_orchestration_stress"
    ):
        recommendation = "observe"
        rationale = "light_non_failure_handoff_block_pattern_detected_observe_before_deeper_intervention"

    if recommendation not in allowed_recommendations:
        recommendation = "insufficient_context"
        rationale = "unrecognized_review_pattern_defaulted_to_insufficient_context"

    return {
        "review_classification": review_classification,
        "records_considered": records_considered,
        "operator_attention_recommendation": recommendation,
        "basis": {
            "condition_flags": {
                "blocked_heavy": blocked_heavy,
                "failure_heavy": failure_heavy,
                "stall_heavy": stall_heavy,
                "light_block_pattern": light_block_pattern,
            },
            "recent_outcome_counts": {
                "execution_succeeded": int(recent_outcome_counts.get("execution_succeeded") or 0),
                "execution_failed": int(recent_outcome_counts.get("execution_failed") or 0),
                "handoff_admitted_pending_result": int(recent_outcome_counts.get("handoff_admitted_pending_result") or 0),
                "execution_still_pending": int(recent_outcome_counts.get("execution_still_pending") or 0),
                "execution_result_missing": int(recent_outcome_counts.get("execution_result_missing") or 0),
                "handoff_not_admitted": handoff_not_admitted,
            },
            "rationale": rationale,
        },
    }


def derive_next_venue_projection(
    delegated_judgment: Mapping[str, Any],
    outcome_review: Mapping[str, Any],
    venue_mix_review: Mapping[str, Any],
    attention_recommendation: Mapping[str, Any],
    *,
    allowed_recommendations: set[str],
    allowed_relations: set[str],
) -> dict[str, Any]:
    """Derive bounded next-venue projection from existing orchestration signals."""

    delegated_venue = str(delegated_judgment.get("recommended_venue") or "insufficient_context")
    escalation_classification = str(delegated_judgment.get("escalation_classification") or "")
    outcome_classification = str(outcome_review.get("review_classification") or "insufficient_history")
    venue_mix_classification = str(venue_mix_review.get("review_classification") or "insufficient_history")
    attention_signal = str(attention_recommendation.get("operator_attention_recommendation") or "insufficient_context")
    outcome_records = int(outcome_review.get("records_considered") or 0)
    venue_mix_records = int(venue_mix_review.get("records_considered") or 0)
    blocked_heavy = bool((outcome_review.get("condition_flags") or {}).get("blocked_heavy"))
    failure_heavy = bool((outcome_review.get("condition_flags") or {}).get("failure_heavy"))
    stall_heavy = bool((outcome_review.get("condition_flags") or {}).get("stall_heavy"))
    operator_heavy = venue_mix_classification == "operator_escalation_heavy"
    external_contribution = venue_mix_review.get("external_fulfillment_contribution")
    external_contribution_map = external_contribution if isinstance(external_contribution, Mapping) else {}
    by_venue = external_contribution_map.get("by_venue")
    by_venue_map = by_venue if isinstance(by_venue, Mapping) else {}

    def _venue_external_health(venue: str) -> dict[str, int]:
        venue_map = by_venue_map.get(venue)
        venue_metrics = venue_map if isinstance(venue_map, Mapping) else {}
        return {
            "healthy": int(venue_metrics.get("healthy") or 0),
            "stressed": int(venue_metrics.get("stressed") or 0),
            "blocked_or_unusable": int(venue_metrics.get("blocked_or_unusable") or 0),
            "fulfilled_externally": int(venue_metrics.get("fulfilled_externally") or 0),
            "fulfilled_externally_with_issues": int(venue_metrics.get("fulfilled_externally_with_issues") or 0),
            "externally_declined": int(venue_metrics.get("externally_declined") or 0),
            "externally_abandoned": int(venue_metrics.get("externally_abandoned") or 0),
            "externally_result_unusable": int(venue_metrics.get("externally_result_unusable") or 0),
        }

    codex_external = _venue_external_health("codex_implementation")
    deep_external = _venue_external_health("deep_research_audit")
    delegated_external = _venue_external_health(delegated_venue) if delegated_venue in {
        "codex_implementation",
        "deep_research_audit",
    } else _venue_external_health("")
    delegated_external_total = delegated_external["healthy"] + delegated_external["stressed"] + delegated_external["blocked_or_unusable"]
    delegated_external_healthy_strong = delegated_external["healthy"] >= 2 and (
        delegated_external["stressed"] + delegated_external["blocked_or_unusable"]
    ) == 0
    delegated_external_stressed = delegated_external_total >= 2 and (
        delegated_external["stressed"] + delegated_external["blocked_or_unusable"]
    ) >= delegated_external["healthy"]
    external_signal_present = bool(external_contribution_map.get("signal_present"))
    alternative_external_healthy = (
        deep_external["healthy"] >= 2 and (deep_external["stressed"] + deep_external["blocked_or_unusable"]) == 0
        if delegated_venue == "codex_implementation"
        else (
            codex_external["healthy"] >= 2 and (codex_external["stressed"] + codex_external["blocked_or_unusable"]) == 0
            if delegated_venue == "deep_research_audit"
            else False
        )
    )

    delegated_to_next = {
        "internal_direct_execution": "prefer_internal_execution",
        "codex_implementation": "prefer_codex_implementation",
        "deep_research_audit": "prefer_deep_research_audit",
        "operator_decision_required": "prefer_operator_decision",
    }
    delegated_next = delegated_to_next.get(delegated_venue)

    recommendation = "insufficient_context"
    relation = "insufficient_context"
    rationale = "insufficient_or_conflicting_recent_signal_basis_for_next_venue"

    operator_escalation_dominant = (
        delegated_venue == "operator_decision_required"
        or escalation_classification in {"escalate_for_missing_context", "escalate_for_operator_priority"}
        or operator_heavy
        or (
            attention_signal in {"inspect_handoff_blocks", "inspect_execution_failures", "inspect_pending_stall"}
            and (blocked_heavy or failure_heavy or stall_heavy)
        )
    )
    has_minimum_history = outcome_records >= 3 and venue_mix_records >= 3
    stress_signals_present = (
        outcome_classification in {
            "handoff_block_heavy",
            "execution_failure_heavy",
            "pending_stall_pattern",
            "mixed_orchestration_stress",
        }
        or venue_mix_classification == "mixed_venue_stress"
    )
    external_feedback_affirming = delegated_external_healthy_strong
    external_feedback_stressed = delegated_external_stressed

    if operator_escalation_dominant:
        recommendation = "prefer_operator_decision"
        relation = "escalating"
        rationale = "operator_required_or_escalation_signals_dominate_recent_orchestration_pattern"
    elif not has_minimum_history or delegated_next is None:
        recommendation = "insufficient_context"
        relation = "insufficient_context"
        rationale = "insufficient_recent_orchestration_history_or_delegated_judgment_venue_unavailable"
    elif (
        delegated_venue in {"internal_direct_execution", "codex_implementation"}
        and venue_mix_classification in {"mixed_venue_stress", "deep_research_heavy"}
        and outcome_classification in {"mixed_orchestration_stress", "execution_failure_heavy"}
    ):
        recommendation = "prefer_deep_research_audit"
        relation = "nudging"
        rationale = "recent_stress_or_architectural_ambiguity_pattern_nudges_toward_deep_research_audit"
    elif delegated_venue in {"codex_implementation", "deep_research_audit"} and external_feedback_stressed and alternative_external_healthy:
        recommendation = "prefer_deep_research_audit" if delegated_venue == "codex_implementation" else "prefer_codex_implementation"
        relation = "nudging"
        rationale = "recent_external_fulfillment_for_delegated_external_venue_is_stressed_while_alternative_external_venue_is_recently_healthy"
    elif delegated_venue in {"codex_implementation", "deep_research_audit"} and external_feedback_stressed:
        recommendation = "hold_current_venue_mix"
        relation = "holding"
        rationale = "recent_external_fulfillment_for_delegated_external_venue_is_stressed_without_a_clear_healthy_external_alternative"
    elif delegated_venue in {"codex_implementation", "deep_research_audit"} and external_feedback_affirming:
        recommendation = delegated_next if delegated_next is not None else "insufficient_context"
        relation = "affirming"
        rationale = "recent_external_fulfillment_for_delegated_external_venue_is_healthy_and_supports_affirmation"
    elif delegated_venue == "internal_direct_execution" and outcome_classification == "clean_recent_orchestration" and venue_mix_classification in {
        "balanced_recent_venue_mix",
        "internal_execution_heavy",
    }:
        recommendation = "prefer_internal_execution"
        relation = "affirming"
        rationale = "clean_recent_internal_outcomes_and_compatible_venue_mix_affirm_internal_execution"
    elif delegated_venue == "codex_implementation" and outcome_classification == "clean_recent_orchestration" and venue_mix_classification in {
        "balanced_recent_venue_mix",
        "codex_heavy",
    }:
        recommendation = "prefer_codex_implementation"
        relation = "affirming"
        rationale = "clean_recent_outcomes_and_compatible_codex_usage_affirm_codex_implementation"
    elif delegated_venue == "deep_research_audit" and venue_mix_classification in {
        "balanced_recent_venue_mix",
        "deep_research_heavy",
    } and outcome_classification in {"clean_recent_orchestration", "mixed_orchestration_stress", "execution_failure_heavy"}:
        recommendation = "prefer_deep_research_audit"
        relation = "affirming"
        rationale = "delegated_judgment_and_recent_venue_patterns_support_deep_research_audit"
    elif stress_signals_present:
        recommendation = "hold_current_venue_mix"
        relation = "holding"
        rationale = "recent_venue_behavior_is_stressed_or_unstable_without_clear_safe_correction_target"
    elif delegated_next is not None:
        recommendation = delegated_next
        relation = "affirming"
        rationale = "delegated_judgment_is_compatible_with_recent_orchestration_signals"

    if recommendation not in allowed_recommendations:
        recommendation = "insufficient_context"
        relation = "insufficient_context"
        rationale = "unrecognized_next_venue_recommendation_defaulted_to_insufficient_context"
    if relation not in allowed_relations:
        relation = "insufficient_context"

    return {
        "delegated_venue": delegated_venue,
        "escalation_classification": escalation_classification,
        "next_venue_recommendation": recommendation,
        "relation_to_delegated_judgment": relation,
        "attention_signal": attention_signal,
        "outcome_classification": outcome_classification,
        "venue_mix_classification": venue_mix_classification,
        "outcome_records": outcome_records,
        "venue_mix_records": venue_mix_records,
        "blocked_heavy": blocked_heavy,
        "failure_heavy": failure_heavy,
        "stall_heavy": stall_heavy,
        "external_signal_present": external_signal_present,
        "delegated_external": delegated_external,
        "codex_external": codex_external,
        "deep_external": deep_external,
        "external_feedback_affirming": external_feedback_affirming,
        "external_feedback_stressed": external_feedback_stressed,
        "rationale": rationale,
    }
