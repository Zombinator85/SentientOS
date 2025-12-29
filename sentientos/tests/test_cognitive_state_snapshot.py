from __future__ import annotations

from copy import deepcopy

from sentientos.consciousness.cognitive_state import build_cognitive_state_snapshot
from sentientos.consciousness.integration import run_consciousness_cycle


def _sample_pressure_snapshot() -> dict:
    return {
        "total_active_pressure": 2,
        "pressure_by_subsystem": [
            {"subsystem": "memory", "count": 2, "content_id": "secret"}
        ],
        "phase_counts": {"refused": 2, "ignored": "nope"},
        "refusal_count": 2,
        "deferred_count": 0,
        "overload": True,
        "overload_domains": [
            {"subsystem": "memory", "outstanding": 2, "cause": "internal"}
        ],
        "oldest_unresolved_age": 5,
        "snapshot_hash": "ignored",
        "secret": "classified",
    }


def test_cognitive_state_snapshot_deterministic_and_hashable() -> None:
    pressure_snapshot = _sample_pressure_snapshot()
    posture_history = ["stable", "tense"]

    snapshot_one = build_cognitive_state_snapshot(
        pressure_snapshot=pressure_snapshot,
        posture_history=posture_history,
    )
    snapshot_two = build_cognitive_state_snapshot(
        pressure_snapshot=pressure_snapshot,
        posture_history=posture_history,
    )

    assert snapshot_one == snapshot_two
    assert snapshot_one["snapshot_hash"] == snapshot_two["snapshot_hash"]


def test_cognitive_state_snapshot_redacts_pressure_fields() -> None:
    pressure_snapshot = _sample_pressure_snapshot()
    snapshot = build_cognitive_state_snapshot(
        pressure_snapshot=pressure_snapshot,
        posture_history=["tense"],
    )

    pressure = snapshot["pressure_snapshot"]
    assert pressure is not None
    assert "secret" not in pressure
    assert "content_id" not in pressure["pressure_by_subsystem"][0]
    assert "cause" not in pressure["overload_domains"][0]
    assert pressure["overload"] is True


def test_cognitive_state_snapshot_does_not_mutate_inputs() -> None:
    pressure_snapshot = _sample_pressure_snapshot()
    posture_history = ["stable"]

    pressure_copy = deepcopy(pressure_snapshot)
    history_copy = list(posture_history)

    build_cognitive_state_snapshot(
        pressure_snapshot=pressure_snapshot,
        posture_history=posture_history,
    )

    assert pressure_snapshot == pressure_copy
    assert posture_history == history_copy


def test_cognitive_state_snapshot_matches_cycle() -> None:
    pressure_snapshot = _sample_pressure_snapshot()
    cycle_result = run_consciousness_cycle({"pressure_snapshot": pressure_snapshot})

    expected_snapshot = build_cognitive_state_snapshot(
        pressure_snapshot=pressure_snapshot,
        posture_history=None,
    )

    assert cycle_result["cognitive_state_snapshot"] == expected_snapshot
