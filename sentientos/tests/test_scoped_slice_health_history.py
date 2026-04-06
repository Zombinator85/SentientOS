from __future__ import annotations

import json
from pathlib import Path

from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic
from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS
from sentientos.scoped_slice_health import synthesize_scoped_slice_health
from sentientos.scoped_slice_health_history import (
    build_scoped_slice_health_history_record,
    persist_scoped_slice_health_history,
)


def _resolved_rows(default_outcome: str) -> list[dict[str, object]]:
    return [
        {
            "typed_action_identity": action_id,
            "correlation_id": f"cid-{index}",
            "outcome_class": default_outcome,
        }
        for index, action_id in enumerate(SCOPED_ACTION_IDS)
    ]


def _health(default_outcome: str, *, first_outcome: str | None = None) -> dict[str, object]:
    rows = _resolved_rows(default_outcome)
    if first_outcome is not None:
        rows[0]["outcome_class"] = first_outcome
    return synthesize_scoped_slice_health(rows)


def test_first_observation_initializes_history_sanely(tmp_path: Path) -> None:
    snapshot = persist_scoped_slice_health_history(tmp_path, slice_health=_health("success"), evaluated_at="2026-04-06T00:00:00Z")
    current = snapshot["current_record"]

    assert current["previous_slice_health_status"] is None
    assert current["transition_classification"] == "initial_observation"
    assert current["slice_health_status"] == "healthy"
    assert snapshot["history_length"] == 1


def test_healthy_to_degraded_transition_is_classified_correctly(tmp_path: Path) -> None:
    persist_scoped_slice_health_history(tmp_path, slice_health=_health("success"), evaluated_at="2026-04-06T00:00:00Z")
    snapshot = persist_scoped_slice_health_history(
        tmp_path,
        slice_health=_health("success", first_outcome="failed_after_admission"),
        evaluated_at="2026-04-06T00:10:00Z",
    )

    assert snapshot["current_record"]["previous_slice_health_status"] == "healthy"
    assert snapshot["current_record"]["slice_health_status"] == "degraded"
    assert snapshot["current_record"]["transition_classification"] == "degrading"


def test_degraded_to_healthy_transition_is_classified_correctly(tmp_path: Path) -> None:
    persist_scoped_slice_health_history(
        tmp_path,
        slice_health=_health("success", first_outcome="failed_after_admission"),
        evaluated_at="2026-04-06T00:00:00Z",
    )
    snapshot = persist_scoped_slice_health_history(tmp_path, slice_health=_health("success"), evaluated_at="2026-04-06T00:10:00Z")

    assert snapshot["current_record"]["previous_slice_health_status"] == "degraded"
    assert snapshot["current_record"]["slice_health_status"] == "healthy"
    assert snapshot["current_record"]["transition_classification"] == "recovered_from_failure"


def test_fragmented_to_healthy_transition_is_classified_correctly(tmp_path: Path) -> None:
    persist_scoped_slice_health_history(
        tmp_path,
        slice_health=_health("success", first_outcome="fragmented_unresolved"),
        evaluated_at="2026-04-06T00:00:00Z",
    )
    snapshot = persist_scoped_slice_health_history(tmp_path, slice_health=_health("success"), evaluated_at="2026-04-06T00:10:00Z")

    assert snapshot["current_record"]["previous_slice_health_status"] == "fragmented"
    assert snapshot["current_record"]["slice_health_status"] == "healthy"
    assert snapshot["current_record"]["transition_classification"] == "recovered_from_fragmentation"


def test_unchanged_status_remains_unchanged(tmp_path: Path) -> None:
    persist_scoped_slice_health_history(tmp_path, slice_health=_health("success"), evaluated_at="2026-04-06T00:00:00Z")
    snapshot = persist_scoped_slice_health_history(tmp_path, slice_health=_health("success"), evaluated_at="2026-04-06T00:10:00Z")

    assert snapshot["current_record"]["slice_health_status"] == "healthy"
    assert snapshot["current_record"]["transition_classification"] == "unchanged"


def test_denied_only_states_preserve_existing_health_semantics(tmp_path: Path) -> None:
    snapshot = persist_scoped_slice_health_history(tmp_path, slice_health=_health("denied"), evaluated_at="2026-04-06T00:00:00Z")

    assert snapshot["current_record"]["slice_health_status"] == "healthy"
    assert snapshot["current_record"]["outcome_counts"]["denied"] == len(SCOPED_ACTION_IDS)


def test_history_record_remains_explicitly_non_sovereign() -> None:
    health = _health("success")
    record = build_scoped_slice_health_history_record(slice_health=health, previous_record=None, evaluated_at="2026-04-06T00:00:00Z")

    assert record["diagnostic_only"] is True
    assert record["non_authoritative"] is True
    assert record["decision_power"] == "none"
    assert record["derived_from"] == "scoped_slice_health_synthesis"


def test_diagnostic_consumer_exposes_history_pointer_and_transition(monkeypatch, tmp_path: Path) -> None:
    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": "success",
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

    first = build_scoped_lifecycle_diagnostic(tmp_path)
    second = build_scoped_lifecycle_diagnostic(tmp_path)

    assert first["slice_health_history"]["current_record"]["transition_classification"] == "initial_observation"
    assert second["slice_health_history"]["current_record"]["transition_classification"] == "unchanged"
    assert second["slice_health_history"]["history_path"].endswith("scoped_slice_health_history.jsonl")
