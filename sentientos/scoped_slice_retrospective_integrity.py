from __future__ import annotations

from typing import Any

_RETROSPECTIVE_WINDOW = 6
_MIN_HISTORY_FOR_REVIEW = 3
_DOMINANCE_RATIO = 0.6


def _sum_outcome(records: list[dict[str, Any]], key: str) -> int:
    total = 0
    for record in records:
        outcome_counts = record.get("outcome_counts")
        if not isinstance(outcome_counts, dict):
            continue
        value = outcome_counts.get(key)
        if isinstance(value, int):
            total += value
    return total


def derive_scoped_slice_retrospective_integrity_review(
    history_records: list[dict[str, Any]],
    *,
    slice_stability: dict[str, Any] | None,
    window_size: int = _RETROSPECTIVE_WINDOW,
) -> dict[str, Any]:
    bounded_window_size = max(1, int(window_size))
    recent_history = history_records[-bounded_window_size:]
    stability_classification = str((slice_stability or {}).get("stability_classification") or "insufficient_history")

    if len(recent_history) < _MIN_HISTORY_FOR_REVIEW:
        classification = "insufficient_history"
        basis = "need_at_least_three_recent_records"
    else:
        statuses = [str(record.get("slice_health_status") or "unknown") for record in recent_history]
        denied_total = _sum_outcome(recent_history, "denied")
        failure_total = _sum_outcome(recent_history, "failed_after_admission")
        fragmentation_total = _sum_outcome(recent_history, "fragmented_unresolved")
        stress_total = denied_total + failure_total + fragmentation_total

        if stability_classification == "oscillating" and "healthy" in statuses and any(status in {"degraded", "fragmented"} for status in statuses):
            classification = "oscillatory_instability"
            basis = "stability_is_oscillating_with_mixed_recent_health_states"
        elif stress_total == 0 and all(status == "healthy" for status in statuses):
            classification = "clean_recent_history"
            basis = "no_recent_denial_failure_or_fragmentation_pressure"
        else:
            by_class = {
                "denial_heavy": denied_total,
                "failure_heavy": failure_total,
                "fragmentation_heavy": fragmentation_total,
            }
            dominant_label = max(by_class.items(), key=lambda item: item[1])[0]
            dominant_total = by_class[dominant_label]

            if stress_total > 0 and dominant_total >= 2 and (dominant_total / stress_total) >= _DOMINANCE_RATIO:
                classification = dominant_label
                basis = f"dominant_recent_stress_signal={dominant_label}"
            elif stress_total > 0:
                classification = "mixed_stress_pattern"
                basis = "multiple_recent_stress_signals_without_single_dominant_class"
            else:
                classification = "insufficient_history"
                basis = "insufficient_stress_evidence_for_classification"

    return {
        "scope": "constitutional_execution_fabric_scoped_slice",
        "review_kind": "retrospective_integrity_review",
        "review_classification": classification,
        "basis": basis,
        "window_size": bounded_window_size,
        "records_considered": len(recent_history),
        "stability_classification": stability_classification,
        "diagnostic_only": True,
        "non_authoritative": True,
        "decision_power": "none",
        "retrospective_support_signal_only": True,
        "does_not_change_release_readiness": True,
        "does_not_change_admission_or_authority": True,
        "derived_from": [
            "scoped_mutation_lifecycle_resolution",
            "scoped_slice_health_synthesis",
            "scoped_slice_health_history",
            "scoped_slice_stability",
        ],
    }
