from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic
from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS
from sentientos.scoped_slice_health import synthesize_scoped_slice_health
from sentientos.scoped_slice_health_history import persist_scoped_slice_health_history
from sentientos.scoped_slice_retrospective_integrity import derive_scoped_slice_retrospective_integrity_review
from sentientos.scoped_slice_stability import derive_scoped_slice_stability


def _health_for_status(status: str) -> dict[str, object]:
    rows = [
        {
            "typed_action_identity": action_id,
            "correlation_id": f"cid-{index}",
            "outcome_class": "success",
        }
        for index, action_id in enumerate(SCOPED_ACTION_IDS)
    ]
    if status == "degraded":
        rows[0]["outcome_class"] = "failed_after_admission"
    elif status == "fragmented":
        rows[0]["outcome_class"] = "fragmented_unresolved"
    elif status == "denial":
        for row in rows:
            row["outcome_class"] = "denied"
    return synthesize_scoped_slice_health(rows)


def _history_from_statuses(tmp_path: Path, statuses: list[str]) -> list[dict[str, object]]:
    for index, status in enumerate(statuses):
        persist_scoped_slice_health_history(
            tmp_path,
            slice_health=_health_for_status(status),
            evaluated_at=f"2026-04-06T01:{index:02d}:00Z",
        )
    history_path = tmp_path / "glow/contracts/constitutional_execution_fabric_scoped_slice_health_history.jsonl"
    loaded = json.loads("[" + ",".join(history_path.read_text(encoding="utf-8").splitlines()) + "]")
    return cast(list[dict[str, object]], loaded)


def _review_from_history(history_rows: list[dict[str, object]]) -> dict[str, object]:
    stability = derive_scoped_slice_stability(history_rows)
    return derive_scoped_slice_retrospective_integrity_review(history_rows, slice_stability=stability)


def test_retrospective_classifies_clean_recent_history(tmp_path: Path) -> None:
    review = _review_from_history(_history_from_statuses(tmp_path, ["healthy", "healthy", "healthy"]))
    assert review["review_classification"] == "clean_recent_history", json.dumps(review, indent=2, sort_keys=True)


def test_retrospective_classifies_denial_heavy(tmp_path: Path) -> None:
    review = _review_from_history(_history_from_statuses(tmp_path, ["denial", "denial", "healthy", "denial"]))
    assert review["review_classification"] == "denial_heavy", json.dumps(review, indent=2, sort_keys=True)


def test_retrospective_classifies_failure_heavy(tmp_path: Path) -> None:
    review = _review_from_history(_history_from_statuses(tmp_path, ["degraded", "degraded", "degraded", "healthy"]))
    assert review["review_classification"] == "failure_heavy", json.dumps(review, indent=2, sort_keys=True)


def test_retrospective_classifies_fragmentation_heavy(tmp_path: Path) -> None:
    review = _review_from_history(_history_from_statuses(tmp_path, ["fragmented", "fragmented", "fragmented", "healthy"]))
    assert review["review_classification"] == "fragmentation_heavy", json.dumps(review, indent=2, sort_keys=True)


def test_retrospective_classifies_oscillatory_instability(tmp_path: Path) -> None:
    review = _review_from_history(_history_from_statuses(tmp_path, ["healthy", "degraded", "healthy", "degraded"]))
    assert review["review_classification"] == "oscillatory_instability", json.dumps(review, indent=2, sort_keys=True)


def test_retrospective_classifies_mixed_stress_pattern() -> None:
    history_rows: list[dict[str, object]] = [
        {
            "slice_health_status": "healthy",
            "transition_classification": "initial_observation",
            "outcome_counts": {"denied": 1, "failed_after_admission": 0, "fragmented_unresolved": 0},
        },
        {
            "slice_health_status": "degraded",
            "transition_classification": "degrading",
            "outcome_counts": {"denied": 0, "failed_after_admission": 1, "fragmented_unresolved": 0},
        },
        {
            "slice_health_status": "fragmented",
            "transition_classification": "degrading",
            "outcome_counts": {"denied": 0, "failed_after_admission": 0, "fragmented_unresolved": 1},
        },
    ]
    review = _review_from_history(history_rows)
    assert review["review_classification"] == "mixed_stress_pattern", json.dumps(review, indent=2, sort_keys=True)


def test_retrospective_classifies_insufficient_history(tmp_path: Path) -> None:
    review = _review_from_history(_history_from_statuses(tmp_path, ["healthy", "denial"]))
    assert review["review_classification"] == "insufficient_history", json.dumps(review, indent=2, sort_keys=True)


def test_scoped_lifecycle_consumer_surfaces_retrospective_review(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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

    review = diagnostic["slice_retrospective_integrity_review"]
    assert review["review_kind"] == "retrospective_integrity_review"
    assert review["review_classification"] == "denial_heavy"
    assert review["diagnostic_only"] is True
    assert review["non_authoritative"] is True
    assert review["decision_power"] == "none"
    assert review["does_not_change_release_readiness"] is True
    assert review["does_not_change_admission_or_authority"] is True
    assert diagnostic["overall_outcome"] in {"success", "denied", "failed_after_admission", "fragmented_unresolved"}
