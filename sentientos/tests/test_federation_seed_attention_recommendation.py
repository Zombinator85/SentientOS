from __future__ import annotations

from sentientos.federation_seed_attention_recommendation import derive_bounded_federation_seed_attention_recommendation


def _recommendation(
    *,
    review_classification: str,
    stability_classification: str = "stable",
    seed_health_status: str = "healthy",
    records_considered: int = 4,
) -> dict[str, object]:
    return derive_bounded_federation_seed_attention_recommendation(
        seed_health={"health_status": seed_health_status},
        seed_health_history={"history_path": "glow/federation/bounded_seed_health_history.jsonl"},
        seed_stability={"classification": stability_classification},
        retrospective_integrity_review={
            "review_classification": review_classification,
            "records_considered": records_considered,
        },
    )


def test_recommendation_none_for_clean_stable() -> None:
    recommendation = _recommendation(review_classification="clean_recent_history")
    assert recommendation["recommended_attention"] == "none"


def test_recommendation_observe_for_denial_heavy() -> None:
    recommendation = _recommendation(review_classification="denial_heavy")
    assert recommendation["recommended_attention"] == "observe"


def test_recommendation_inspect_recent_failures_for_failure_heavy() -> None:
    recommendation = _recommendation(review_classification="failure_heavy")
    assert recommendation["recommended_attention"] == "inspect_recent_failures"


def test_recommendation_inspect_fragmentation_for_fragmentation_heavy() -> None:
    recommendation = _recommendation(review_classification="fragmentation_heavy")
    assert recommendation["recommended_attention"] == "inspect_fragmentation"


def test_recommendation_watch_for_oscillation_for_oscillatory_instability() -> None:
    recommendation = _recommendation(review_classification="oscillatory_instability", stability_classification="oscillating")
    assert recommendation["recommended_attention"] == "watch_for_oscillation"


def test_recommendation_review_mixed_stress_for_mixed_pattern() -> None:
    recommendation = _recommendation(review_classification="mixed_stress_pattern")
    assert recommendation["recommended_attention"] == "review_mixed_stress"


def test_recommendation_insufficient_context_for_insufficient_history() -> None:
    recommendation = _recommendation(review_classification="insufficient_history", records_considered=2)
    assert recommendation["recommended_attention"] == "insufficient_context"
