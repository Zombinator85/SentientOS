from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic
from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS
from sentientos.scoped_slice_attention_recommendation import derive_scoped_slice_attention_recommendation


def _recommendation(
    *,
    review_classification: str,
    stability_classification: str = "stable",
    slice_health_status: str = "healthy",
    records_considered: int = 4,
) -> dict[str, object]:
    return derive_scoped_slice_attention_recommendation(
        slice_health={"slice_health_status": slice_health_status},
        slice_health_history={"history_path": "glow/contracts/constitutional_execution_fabric_scoped_slice_health_history.jsonl"},
        slice_stability={"stability_classification": stability_classification},
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


def test_scoped_lifecycle_consumer_surfaces_attention_recommendation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        outcome = "denied" if action_id == SCOPED_ACTION_IDS[0] else "success"
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": outcome,
        }

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle", _fake_resolver)

    rows = [
        {
            "event": "constitutional_mutation_router_execution",
            "typed_action_id": action_id,
            "correlation_id": f"cid-{index}",
        }
        for index, action_id in enumerate(SCOPED_ACTION_IDS)
    ]
    forge_events = tmp_path / "pulse/forge_events.jsonl"
    forge_events.parent.mkdir(parents=True, exist_ok=True)
    forge_events.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    for _ in range(3):
        diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)

    recommendation = diagnostic["slice_operator_attention_recommendation"]
    assert recommendation["recommendation_kind"] == "operator_attention_recommendation"
    assert recommendation["recommended_attention"] == "observe"
    assert recommendation["diagnostic_only"] is True
    assert recommendation["recommendation_only"] is True
    assert recommendation["non_authoritative"] is True
    assert recommendation["decision_power"] == "none"
    assert recommendation["does_not_change_runtime_or_mergeability"] is True
    assert recommendation["does_not_change_release_readiness"] is True
    assert recommendation["does_not_change_admission_or_authority"] is True


def test_attention_recommendation_does_not_change_overall_outcome(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        outcome = "denied" if action_id == SCOPED_ACTION_IDS[0] else "success"
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": outcome,
        }

    monkeypatch.setattr("sentientos.scoped_lifecycle_diagnostic.resolve_scoped_mutation_lifecycle", _fake_resolver)
    monkeypatch.setattr(
        "sentientos.scoped_lifecycle_diagnostic.derive_scoped_slice_attention_recommendation",
        lambda **_: {
            "scope": "constitutional_execution_fabric_scoped_slice",
            "recommendation_kind": "operator_attention_recommendation",
            "recommended_attention": "review_mixed_stress",
            "diagnostic_only": True,
            "recommendation_only": True,
            "non_authoritative": True,
            "decision_power": "none",
            "does_not_change_runtime_or_mergeability": True,
            "does_not_change_release_readiness": True,
            "does_not_change_admission_or_authority": True,
        },
    )

    rows = [
        {
            "event": "constitutional_mutation_router_execution",
            "typed_action_id": action_id,
            "correlation_id": f"cid-{index}",
        }
        for index, action_id in enumerate(SCOPED_ACTION_IDS)
    ]
    forge_events = tmp_path / "pulse/forge_events.jsonl"
    forge_events.parent.mkdir(parents=True, exist_ok=True)
    forge_events.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    assert diagnostic["overall_outcome"] == "denied"
