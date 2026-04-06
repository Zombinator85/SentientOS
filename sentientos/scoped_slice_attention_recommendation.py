from __future__ import annotations

from typing import Any

from sentientos.constitutional_slice_pattern import non_sovereign_diagnostic_boundaries

_ATTENTION_RECOMMENDATIONS = {
    "none",
    "observe",
    "inspect_recent_failures",
    "inspect_fragmentation",
    "watch_for_oscillation",
    "review_mixed_stress",
    "insufficient_context",
}


def derive_scoped_slice_attention_recommendation(
    *,
    slice_health: dict[str, Any],
    slice_health_history: dict[str, Any],
    slice_stability: dict[str, Any],
    retrospective_integrity_review: dict[str, Any],
) -> dict[str, Any]:
    """Derive one bounded, operator-facing recommendation for this scoped slice."""

    review_classification = str(retrospective_integrity_review.get("review_classification") or "insufficient_history")
    stability_classification = str(slice_stability.get("stability_classification") or "insufficient_history")
    slice_health_status = str(slice_health.get("slice_health_status") or "unknown")
    records_considered = int(retrospective_integrity_review.get("records_considered") or 0)

    if review_classification == "insufficient_history" or stability_classification == "insufficient_history" or records_considered < 3:
        recommendation = "insufficient_context"
        basis = "insufficient_recent_slice_context_for_attention_guidance"
    elif review_classification == "clean_recent_history" and slice_health_status == "healthy" and stability_classification in {"stable", "improving"}:
        recommendation = "none"
        basis = "clean_recent_history_with_healthy_slice_and_non_degrading_stability"
    elif review_classification == "denial_heavy":
        recommendation = "observe"
        basis = "retrospective_review_denial_heavy"
    elif review_classification == "failure_heavy":
        recommendation = "inspect_recent_failures"
        basis = "retrospective_review_failure_heavy"
    elif review_classification == "fragmentation_heavy":
        recommendation = "inspect_fragmentation"
        basis = "retrospective_review_fragmentation_heavy"
    elif review_classification == "oscillatory_instability":
        recommendation = "watch_for_oscillation"
        basis = "retrospective_review_oscillatory_instability"
    elif review_classification == "mixed_stress_pattern":
        recommendation = "review_mixed_stress"
        basis = "retrospective_review_mixed_stress_pattern"
    else:
        recommendation = "observe"
        basis = "unrecognized_retrospective_classification_fallback"

    if recommendation not in _ATTENTION_RECOMMENDATIONS:
        recommendation = "insufficient_context"
        basis = "recommendation_guardrail_fallback"

    return {
        "scope": "constitutional_execution_fabric_scoped_slice",
        "recommendation_kind": "operator_attention_recommendation",
        "recommended_attention": recommendation,
        "basis": basis,
        "review_classification": review_classification,
        "slice_health_status": slice_health_status,
        "stability_classification": stability_classification,
        "records_considered": records_considered,
        "recommendation_only": True,
        "does_not_change_runtime_or_mergeability": True,
        "does_not_change_release_readiness": True,
        "does_not_change_admission_or_authority": True,
        "allowed_recommendations": sorted(_ATTENTION_RECOMMENDATIONS),
        "history_source": slice_health_history.get("history_path"),
        **non_sovereign_diagnostic_boundaries(
            derived_from=[
                "scoped_slice_health_synthesis",
                "scoped_slice_health_history",
                "scoped_slice_stability",
                "scoped_slice_retrospective_integrity_review",
            ]
        ),
    }
