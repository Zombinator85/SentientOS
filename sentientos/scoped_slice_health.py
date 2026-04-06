from __future__ import annotations

from typing import Any

from sentientos.constitutional_slice_pattern import non_sovereign_diagnostic_boundaries
from sentientos.scoped_mutation_lifecycle import SCOPED_ACTION_IDS

_OUTCOME_CLASSES: tuple[str, ...] = (
    "success",
    "denied",
    "failed_after_admission",
    "fragmented_unresolved",
)


def synthesize_scoped_slice_health(resolved_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive one scoped, diagnostic health view from resolved lifecycle rows."""
    per_action_latest_outcome: dict[str, str] = {
        action_id: "fragmented_unresolved" for action_id in SCOPED_ACTION_IDS
    }
    for row in resolved_rows:
        action_id = str(row.get("typed_action_identity") or "")
        if action_id not in per_action_latest_outcome:
            continue
        outcome_class = str(row.get("outcome_class") or "fragmented_unresolved")
        if outcome_class not in _OUTCOME_CLASSES:
            outcome_class = "fragmented_unresolved"
        per_action_latest_outcome[action_id] = outcome_class

    outcome_counts: dict[str, int] = {outcome: 0 for outcome in _OUTCOME_CLASSES}
    for outcome_class in per_action_latest_outcome.values():
        outcome_counts[outcome_class] += 1

    has_fragmentation = outcome_counts["fragmented_unresolved"] > 0
    has_admitted_failure = outcome_counts["failed_after_admission"] > 0

    if has_fragmentation:
        slice_health_status = "fragmented"
    elif has_admitted_failure:
        slice_health_status = "degraded"
    else:
        slice_health_status = "healthy"

    return {
        "scope": "constitutional_execution_fabric_scoped_slice",
        "slice_health_status": slice_health_status,
        "per_action_latest_outcome": per_action_latest_outcome,
        "outcome_counts": outcome_counts,
        "has_fragmentation": has_fragmentation,
        "has_admitted_failure": has_admitted_failure,
        **non_sovereign_diagnostic_boundaries(derived_from="scoped_mutation_lifecycle_resolution"),
    }
