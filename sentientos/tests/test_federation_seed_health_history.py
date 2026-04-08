from __future__ import annotations

from pathlib import Path

from sentientos.federation_canonical_execution import BOUNDED_FEDERATION_CANONICAL_ACTIONS
from sentientos.federation_mutation_control_preflight import build_federation_mutation_control_preflight
from sentientos.federation_seed_health_history import (
    build_bounded_federation_seed_health_history_record,
    derive_bounded_federation_seed_stability,
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
    assert second_temporal["stability"]["classification"] in {
        "stable",
        "improving",
        "degrading",
        "oscillating",
        "insufficient_history",
    }
    assert second_temporal["stability"]["diagnostic_only"] is True
    assert second_temporal["stability"]["decision_power"] == "none"
    assert second_temporal["stability"]["does_not_change_admission_or_readiness"] is True


def _persist_health_sequence(tmp_path: Path, statuses: list[str]) -> dict[str, object]:
    outcome_by_status = {
        "healthy": _health("success"),
        "degraded": _health("success", first_outcome="failed_after_admission"),
        "fragmented": _health("success", first_outcome="fragmented_unresolved"),
    }
    snapshot: dict[str, object] = {}
    for idx, status in enumerate(statuses):
        snapshot = persist_bounded_federation_seed_health_history(
            tmp_path,
            seed_health=outcome_by_status[status],
            evaluated_at=f"2026-04-08T00:{idx:02d}:00Z",
        )
    return snapshot


def test_stability_is_insufficient_with_too_few_records(tmp_path: Path) -> None:
    snapshot = _persist_health_sequence(tmp_path, ["healthy", "healthy"])
    assert snapshot["stability"]["classification"] == "insufficient_history"


def test_steady_healthy_history_classifies_as_stable(tmp_path: Path) -> None:
    snapshot = _persist_health_sequence(tmp_path, ["healthy", "healthy", "healthy", "healthy"])
    assert snapshot["stability"]["classification"] == "stable"


def test_alternating_health_history_classifies_as_oscillating(tmp_path: Path) -> None:
    snapshot = _persist_health_sequence(tmp_path, ["healthy", "degraded", "healthy", "degraded", "healthy"])
    assert snapshot["stability"]["classification"] == "oscillating"


def test_monotonic_improvement_classifies_as_improving(tmp_path: Path) -> None:
    snapshot = _persist_health_sequence(tmp_path, ["fragmented", "degraded", "healthy", "healthy"])
    assert snapshot["stability"]["classification"] == "improving"


def test_monotonic_worsening_classifies_as_degrading(tmp_path: Path) -> None:
    snapshot = _persist_health_sequence(tmp_path, ["healthy", "degraded", "fragmented", "fragmented"])
    assert snapshot["stability"]["classification"] == "degrading"


def test_denied_only_behavior_remains_stable_under_existing_semantics() -> None:
    denied_health = _health("denied")
    history_rows = [
        build_bounded_federation_seed_health_history_record(seed_health=denied_health, previous_record=None, evaluated_at="2026-04-08T00:00:00Z"),
        build_bounded_federation_seed_health_history_record(
            seed_health=denied_health,
            previous_record={"health_status": "healthy", "has_fragmentation": False, "has_admitted_failure": False},
            evaluated_at="2026-04-08T00:01:00Z",
        ),
        build_bounded_federation_seed_health_history_record(
            seed_health=denied_health,
            previous_record={"health_status": "healthy", "has_fragmentation": False, "has_admitted_failure": False},
            evaluated_at="2026-04-08T00:02:00Z",
        ),
    ]
    stability = derive_bounded_federation_seed_stability(history_rows)
    assert stability["classification"] == "stable"
