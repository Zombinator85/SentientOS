from __future__ import annotations

import json
from pathlib import Path

from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic
from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS
from sentientos.scoped_slice_health import synthesize_scoped_slice_health


def _resolved_rows(outcome: str) -> list[dict[str, object]]:
    return [
        {
            "typed_action_identity": action_id,
            "correlation_id": f"cid-{index}",
            "outcome_class": outcome,
        }
        for index, action_id in enumerate(SCOPED_ACTION_IDS)
    ]


def test_all_success_rows_produce_healthy_slice_status() -> None:
    health = synthesize_scoped_slice_health(_resolved_rows("success"))

    assert health["slice_health_status"] == "healthy", json.dumps(health, indent=2, sort_keys=True)
    assert health["outcome_counts"]["success"] == len(SCOPED_ACTION_IDS)
    assert health["has_fragmentation"] is False
    assert health["has_admitted_failure"] is False


def test_admitted_failure_produces_degraded_slice_status() -> None:
    rows = _resolved_rows("success")
    rows[0]["outcome_class"] = "failed_after_admission"

    health = synthesize_scoped_slice_health(rows)

    assert health["slice_health_status"] == "degraded", json.dumps(health, indent=2, sort_keys=True)
    assert health["outcome_counts"]["failed_after_admission"] == 1
    assert health["has_admitted_failure"] is True


def test_fragmented_row_produces_fragmented_slice_status() -> None:
    rows = _resolved_rows("success")
    rows[0]["outcome_class"] = "fragmented_unresolved"

    health = synthesize_scoped_slice_health(rows)

    assert health["slice_health_status"] == "fragmented", json.dumps(health, indent=2, sort_keys=True)
    assert health["outcome_counts"]["fragmented_unresolved"] == 1
    assert health["has_fragmentation"] is True


def test_denied_outcomes_do_not_automatically_degrade_slice() -> None:
    health = synthesize_scoped_slice_health(_resolved_rows("denied"))

    assert health["slice_health_status"] == "healthy", json.dumps(health, indent=2, sort_keys=True)
    assert health["outcome_counts"]["denied"] == len(SCOPED_ACTION_IDS)


def test_health_view_is_explicitly_non_authoritative_and_derived() -> None:
    health = synthesize_scoped_slice_health(_resolved_rows("success"))

    assert health["diagnostic_only"] is True
    assert health["non_authoritative"] is True
    assert health["derived_from"] == "scoped_mutation_lifecycle_resolution"
    assert health["decision_power"] == "none"
    assert health["does_not_block_mutations"] is True


def test_diagnostic_consumer_reflects_slice_health_summary(monkeypatch, tmp_path: Path) -> None:
    def _fake_resolver(_repo_root: Path, *, action_id: str, correlation_id: str) -> dict[str, object]:
        outcome = "failed_after_admission" if action_id == "sentientos.manifest.generate" else "success"
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

    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)

    assert diagnostic["slice_health"]["slice_health_status"] == "degraded", json.dumps(diagnostic, indent=2, sort_keys=True)
    assert diagnostic["slice_health"]["outcome_counts"]["failed_after_admission"] == 1
    assert diagnostic["slice_health"]["per_action_latest_outcome"]["sentientos.manifest.generate"] == "failed_after_admission"
