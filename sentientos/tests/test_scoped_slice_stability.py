from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic
from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS
from sentientos.scoped_slice_health import synthesize_scoped_slice_health
from sentientos.scoped_slice_health_history import persist_scoped_slice_health_history
from sentientos.scoped_slice_stability import derive_scoped_slice_stability


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


def _append_history(tmp_path: Path, statuses: list[str]) -> None:
    for index, status in enumerate(statuses):
        if status == "healthy":
            health = _health("success")
        elif status == "degraded":
            health = _health("success", first_outcome="failed_after_admission")
        else:
            health = _health("success", first_outcome="fragmented_unresolved")
        persist_scoped_slice_health_history(
            tmp_path,
            slice_health=health,
            evaluated_at=f"2026-04-06T00:{index:02d}:00Z",
        )


def test_stability_is_insufficient_with_too_few_records() -> None:
    stability = derive_scoped_slice_stability(
        [{"slice_health_status": "healthy", "transition_classification": "initial_observation"}],
    )

    assert stability["stability_classification"] == "insufficient_history", json.dumps(stability, indent=2, sort_keys=True)
    assert stability["records_considered"] == 1


def test_steady_healthy_history_is_stable(tmp_path: Path) -> None:
    _append_history(tmp_path, ["healthy", "healthy", "healthy"])
    history = json.loads(
        "[" + ",".join((tmp_path / "glow/contracts/constitutional_execution_fabric_scoped_slice_health_history.jsonl").read_text(encoding="utf-8").splitlines()) + "]"
    )
    stability = derive_scoped_slice_stability(history)

    assert stability["stability_classification"] == "stable", json.dumps(stability, indent=2, sort_keys=True)


def test_alternating_health_window_is_oscillating(tmp_path: Path) -> None:
    _append_history(tmp_path, ["healthy", "degraded", "healthy", "degraded"])
    history = json.loads(
        "[" + ",".join((tmp_path / "glow/contracts/constitutional_execution_fabric_scoped_slice_health_history.jsonl").read_text(encoding="utf-8").splitlines()) + "]"
    )
    stability = derive_scoped_slice_stability(history)

    assert stability["stability_classification"] == "oscillating", json.dumps(stability, indent=2, sort_keys=True)


def test_degraded_to_healthy_then_steady_is_improving(tmp_path: Path) -> None:
    _append_history(tmp_path, ["degraded", "healthy", "healthy"])
    history = json.loads(
        "[" + ",".join((tmp_path / "glow/contracts/constitutional_execution_fabric_scoped_slice_health_history.jsonl").read_text(encoding="utf-8").splitlines()) + "]"
    )
    stability = derive_scoped_slice_stability(history)

    assert stability["stability_classification"] == "improving", json.dumps(stability, indent=2, sort_keys=True)


def test_monotonic_worsening_is_degrading(tmp_path: Path) -> None:
    _append_history(tmp_path, ["healthy", "degraded", "fragmented"])
    history = json.loads(
        "[" + ",".join((tmp_path / "glow/contracts/constitutional_execution_fabric_scoped_slice_health_history.jsonl").read_text(encoding="utf-8").splitlines()) + "]"
    )
    stability = derive_scoped_slice_stability(history)

    assert stability["stability_classification"] == "degrading", json.dumps(stability, indent=2, sort_keys=True)


def test_denied_only_health_semantics_remain_consistent_and_stable(tmp_path: Path) -> None:
    _append_history(tmp_path, ["healthy", "healthy", "healthy"])
    health = _health("denied")
    snapshot = persist_scoped_slice_health_history(
        tmp_path,
        slice_health=health,
        evaluated_at="2026-04-06T00:59:00Z",
    )
    stability = derive_scoped_slice_stability(snapshot["recent_history"])

    assert health["slice_health_status"] == "healthy", json.dumps(health, indent=2, sort_keys=True)
    assert stability["stability_classification"] == "stable", json.dumps(stability, indent=2, sort_keys=True)


def test_diagnostic_consumer_exposes_stability_reading(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sequence = [
        "failed_after_admission",
        "success",
        "failed_after_admission",
    ]
    call_index = {"value": 0}

    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        current = sequence[call_index["value"] % len(sequence)]
        if action_id != SCOPED_ACTION_IDS[0]:
            current = "success"
        return {
            "typed_action_identity": action_id,
            "correlation_id": correlation_id,
            "outcome_class": current,
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
    call_index["value"] += 1
    second = build_scoped_lifecycle_diagnostic(tmp_path)
    call_index["value"] += 1
    third = build_scoped_lifecycle_diagnostic(tmp_path)

    assert first["slice_stability"]["stability_classification"] == "insufficient_history"
    assert second["slice_stability"]["stability_classification"] == "insufficient_history"
    assert third["slice_stability"]["stability_classification"] == "oscillating", json.dumps(third, indent=2, sort_keys=True)
    assert third["slice_stability"]["diagnostic_only"] is True
    assert third["slice_stability"]["non_authoritative"] is True
