from __future__ import annotations

from pathlib import Path

from sentientos.federation_canonical_execution import BOUNDED_FEDERATION_CANONICAL_ACTIONS
from sentientos.federation_mutation_control_preflight import build_federation_mutation_control_preflight
from sentientos.federation_seed_health_history import (
    build_bounded_federation_seed_health_history_record,
    persist_bounded_federation_seed_health_history,
)
from sentientos.federation_slice_health import synthesize_bounded_federation_seed_health


def _health(default_outcome: str, *, first_outcome: str | None = None) -> dict[str, object]:
    rows: list[dict[str, object]] = [
        {"typed_action_identity": action_id, "outcome_class": default_outcome}
        for action_id in BOUNDED_FEDERATION_CANONICAL_ACTIONS
    ]
    if first_outcome is not None:
        rows[0]["outcome_class"] = first_outcome
    return synthesize_bounded_federation_seed_health(rows)


def test_first_observation_initializes_history_sanely(tmp_path: Path) -> None:
    snapshot = persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("success"),
        evaluated_at="2026-04-08T00:00:00Z",
    )
    current = snapshot["current_record"]

    assert current["previous_health_status"] is None
    assert current["transition_classification"] == "initial_observation"
    assert current["health_status"] == "healthy"
    assert snapshot["history_length"] == 1


def test_healthy_to_degraded_transition_is_classified_correctly(tmp_path: Path) -> None:
    persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("success"),
        evaluated_at="2026-04-08T00:00:00Z",
    )
    snapshot = persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("success", first_outcome="failed_after_admission"),
        evaluated_at="2026-04-08T00:10:00Z",
    )

    assert snapshot["current_record"]["previous_health_status"] == "healthy"
    assert snapshot["current_record"]["health_status"] == "degraded"
    assert snapshot["current_record"]["transition_classification"] == "degrading"


def test_degraded_to_healthy_transition_is_classified_correctly(tmp_path: Path) -> None:
    persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("success", first_outcome="failed_after_admission"),
        evaluated_at="2026-04-08T00:00:00Z",
    )
    snapshot = persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("success"),
        evaluated_at="2026-04-08T00:10:00Z",
    )

    assert snapshot["current_record"]["previous_health_status"] == "degraded"
    assert snapshot["current_record"]["health_status"] == "healthy"
    assert snapshot["current_record"]["transition_classification"] == "recovered_from_failure"


def test_fragmented_to_healthy_transition_is_classified_correctly(tmp_path: Path) -> None:
    persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("success", first_outcome="fragmented_unresolved"),
        evaluated_at="2026-04-08T00:00:00Z",
    )
    snapshot = persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("success"),
        evaluated_at="2026-04-08T00:10:00Z",
    )

    assert snapshot["current_record"]["previous_health_status"] == "fragmented"
    assert snapshot["current_record"]["health_status"] == "healthy"
    assert snapshot["current_record"]["transition_classification"] == "recovered_from_fragmentation"


def test_unchanged_status_remains_unchanged(tmp_path: Path) -> None:
    persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("success"),
        evaluated_at="2026-04-08T00:00:00Z",
    )
    snapshot = persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("success"),
        evaluated_at="2026-04-08T00:10:00Z",
    )

    assert snapshot["current_record"]["health_status"] == "healthy"
    assert snapshot["current_record"]["transition_classification"] == "unchanged"


def test_denied_only_states_preserve_existing_health_semantics(tmp_path: Path) -> None:
    snapshot = persist_bounded_federation_seed_health_history(
        tmp_path,
        seed_health=_health("denied"),
        evaluated_at="2026-04-08T00:00:00Z",
    )

    assert snapshot["current_record"]["health_status"] == "healthy"
    assert snapshot["current_record"]["outcome_counts"]["denied"] == len(BOUNDED_FEDERATION_CANONICAL_ACTIONS)


def test_history_record_remains_explicitly_non_sovereign() -> None:
    record = build_bounded_federation_seed_health_history_record(
        seed_health=_health("success"),
        previous_record=None,
        evaluated_at="2026-04-08T00:00:00Z",
    )

    assert record["diagnostic_only"] is True
    assert record["non_authoritative"] is True
    assert record["decision_power"] == "none"
    assert record["support_signal_only"] is True
    assert record["affects_admission"] is False
    assert record["affects_mergeability"] is False
    assert record["affects_runtime_governor_behavior"] is False
    assert record["acts_as_federation_adjudicator"] is False


def test_preflight_consumer_exposes_temporal_health_view(tmp_path: Path) -> None:
    first = build_federation_mutation_control_preflight({"repo_root": str(tmp_path)})
    second = build_federation_mutation_control_preflight({"repo_root": str(tmp_path)})

    first_temporal = first["bounded_federation_lifecycle_diagnostic"]["bounded_federation_seed_temporal_view"]
    second_temporal = second["bounded_federation_lifecycle_diagnostic"]["bounded_federation_seed_temporal_view"]

    assert first_temporal["transition_classification"] == "initial_observation"
    assert second_temporal["transition_classification"] == "unchanged"
    assert second_temporal["history_path"].endswith("bounded_seed_health_history.jsonl")
    assert isinstance(second_temporal["recent_history"], list)
