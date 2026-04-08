from __future__ import annotations

from typing import Any

from sentientos.constitutional_slice_pattern import non_sovereign_diagnostic_boundaries
from sentientos.federation_canonical_execution import BOUNDED_FEDERATION_CANONICAL_ACTIONS


_OUTCOME_CLASSES: tuple[str, ...] = (
    "success",
    "denied",
    "failed_after_admission",
    "fragmented_unresolved",
)


def synthesize_bounded_federation_seed_health(resolved_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive bounded, non-sovereign health from latest lifecycle rows per in-scope intent."""

    per_intent_latest_outcome: dict[str, str] = {
        action_id: "fragmented_unresolved" for action_id in BOUNDED_FEDERATION_CANONICAL_ACTIONS
    }
    for row in resolved_rows:
        action_id = str(row.get("typed_action_identity") or "")
        if action_id not in per_intent_latest_outcome:
            continue
        outcome = str(row.get("outcome_class") or "fragmented_unresolved")
        if outcome not in _OUTCOME_CLASSES:
            outcome = "fragmented_unresolved"
        per_intent_latest_outcome[action_id] = outcome

    outcome_counts: dict[str, int] = {outcome: 0 for outcome in _OUTCOME_CLASSES}
    for outcome in per_intent_latest_outcome.values():
        outcome_counts[outcome] += 1

    has_fragmentation = outcome_counts["fragmented_unresolved"] > 0
    has_admitted_failure = outcome_counts["failed_after_admission"] > 0
    if has_fragmentation:
        health_status = "fragmented"
    elif has_admitted_failure:
        health_status = "degraded"
    else:
        health_status = "healthy"

    return {
        "scope": "bounded_federation_seed",
        "health_status": health_status,
        "per_intent_latest_outcome": per_intent_latest_outcome,
        "outcome_counts": outcome_counts,
        "has_fragmentation": has_fragmentation,
        "has_admitted_failure": has_admitted_failure,
        **non_sovereign_diagnostic_boundaries(
            derived_from="sentientos.federation_bounded_lifecycle.resolve_bounded_federation_lifecycle",
            extra={
                "support_signal_only": True,
                "affects_admission": False,
                "affects_mergeability": False,
                "affects_runtime_governor_behavior": False,
                "acts_as_federation_adjudicator": False,
            },
        ),
    }


__all__ = ["synthesize_bounded_federation_seed_health"]
