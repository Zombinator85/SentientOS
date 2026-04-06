from __future__ import annotations

from typing import Any

_STATUS_ORDER: dict[str, int] = {"healthy": 0, "degraded": 1, "fragmented": 2}
_STABILITY_WINDOW = 6
_MIN_HISTORY_FOR_CLASSIFICATION = 3


def _classify_stability(statuses: list[str]) -> tuple[str, str]:
    if len(statuses) < _MIN_HISTORY_FOR_CLASSIFICATION:
        return "insufficient_history", "need_at_least_three_records"

    if all(status == statuses[0] for status in statuses):
        return "stable", "repeated_same_slice_health_status"

    maybe_ranks = [_STATUS_ORDER.get(status) for status in statuses]
    if any(rank is None for rank in maybe_ranks):
        return "insufficient_history", "unknown_status_in_window"
    ranks = [rank for rank in maybe_ranks if rank is not None]

    deltas = [ranks[index + 1] - ranks[index] for index in range(len(ranks) - 1)]
    has_improvement = any(delta < 0 for delta in deltas)
    has_degradation = any(delta > 0 for delta in deltas)

    if has_improvement and has_degradation:
        return "oscillating", "mixed_improving_and_degrading_steps"

    if has_improvement and not has_degradation:
        return "improving", "monotonic_toward_healthier_states"

    if has_degradation and not has_improvement:
        return "degrading", "monotonic_toward_worse_states"

    return "stable", "no_significant_status_churn"


def derive_scoped_slice_stability(
    history_records: list[dict[str, Any]],
    *,
    window_size: int = _STABILITY_WINDOW,
) -> dict[str, Any]:
    bounded_window_size = max(1, int(window_size))
    recent_history = history_records[-bounded_window_size:]
    statuses = [str(record.get("slice_health_status") or "unknown") for record in recent_history]
    transitions = [str(record.get("transition_classification") or "unknown") for record in recent_history]

    classification, basis = _classify_stability(statuses)

    return {
        "scope": "constitutional_execution_fabric_scoped_slice",
        "stability_classification": classification,
        "window_size": bounded_window_size,
        "records_considered": len(recent_history),
        "basis": basis,
        "recent_status_window": statuses,
        "recent_transition_window": transitions,
        "diagnostic_only": True,
        "non_authoritative": True,
        "derived_from": "scoped_slice_health_history",
        "decision_power": "none",
        "does_not_block_mutations": True,
        "does_not_override_kernel_or_governor": True,
        "does_not_replace_corridor_proof": True,
        "does_not_replace_jurisprudence": True,
    }
