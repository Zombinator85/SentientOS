from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.constitutional_slice_pattern import non_sovereign_diagnostic_boundaries


_HISTORY_PATH = "glow/federation/bounded_seed_health_history.jsonl"
_DEFAULT_HISTORY_LIMIT = 64
_DEFAULT_STABILITY_WINDOW = 6
_STATUS_ORDER: dict[str, int] = {"healthy": 0, "degraded": 1, "fragmented": 2}
_STABILITY_CLASSES: tuple[str, ...] = ("stable", "improving", "degrading", "oscillating", "insufficient_history")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _step_direction(previous: dict[str, Any], current: dict[str, Any]) -> int:
    previous_status = str(previous.get("health_status") or "fragmented")
    current_status = str(current.get("health_status") or "fragmented")
    previous_rank = _STATUS_ORDER.get(previous_status)
    current_rank = _STATUS_ORDER.get(current_status)
    if previous_rank is not None and current_rank is not None and previous_rank != current_rank:
        return -1 if current_rank < previous_rank else 1

    previous_fragmented = bool(previous.get("has_fragmentation"))
    current_fragmented = bool(current.get("has_fragmentation"))
    if previous_fragmented != current_fragmented:
        return -1 if not current_fragmented else 1

    previous_admitted_failure = bool(previous.get("has_admitted_failure"))
    current_admitted_failure = bool(current.get("has_admitted_failure"))
    if previous_admitted_failure != current_admitted_failure:
        return -1 if not current_admitted_failure else 1

    return 0


def derive_bounded_federation_seed_stability(
    history_rows: list[dict[str, Any]],
    *,
    window_size: int = _DEFAULT_STABILITY_WINDOW,
) -> dict[str, Any]:
    bounded_window = history_rows[-window_size:] if window_size > 0 else list(history_rows)
    records_considered = len(bounded_window)
    if records_considered < 3:
        return {
            "classification": "insufficient_history",
            "window_size": window_size,
            "records_considered": records_considered,
            "basis": "need_at_least_three_records_for_conservative_stability_signal",
            "observed_transition_classes": [str(row.get("transition_classification") or "unknown") for row in bounded_window],
            **non_sovereign_diagnostic_boundaries(
                derived_from="sentientos.federation_seed_health_history.persist_bounded_federation_seed_health_history",
                extra={
                    "support_signal_only": True,
                    "does_not_change_admission_or_readiness": True,
                    "acts_as_federation_adjudicator": False,
                },
            ),
        }

    directions = [_step_direction(bounded_window[idx - 1], bounded_window[idx]) for idx in range(1, records_considered)]
    nonzero_directions = [direction for direction in directions if direction != 0]
    transition_classes = [str(row.get("transition_classification") or "unknown") for row in bounded_window]

    if not nonzero_directions:
        classification = "stable"
        basis = "no_meaningful_health_or_fragmentation_churn_in_window"
    else:
        alternations = sum(
            1
            for idx in range(1, len(nonzero_directions))
            if nonzero_directions[idx] != nonzero_directions[idx - 1]
        )
        has_improving = any(direction < 0 for direction in nonzero_directions)
        has_degrading = any(direction > 0 for direction in nonzero_directions)
        if has_improving and has_degrading and alternations >= 2:
            classification = "oscillating"
            basis = "repeated_direction_alternation_between_healthier_and_worse_states"
        elif has_improving and not has_degrading:
            classification = "improving"
            basis = "monotonic_movement_toward_healthier_state_without_worsening"
        elif has_degrading and not has_improving:
            classification = "degrading"
            basis = "monotonic_movement_toward_worse_state_without_recovery"
        else:
            classification = "stable"
            basis = "mixed_churn_without_repeated_alternation"

    if classification not in _STABILITY_CLASSES:
        classification = "insufficient_history"
        basis = "classifier_safety_fallback"

    return {
        "classification": classification,
        "window_size": window_size,
        "records_considered": records_considered,
        "basis": basis,
        "observed_transition_classes": transition_classes,
        "latest_transition_classification": transition_classes[-1],
        **non_sovereign_diagnostic_boundaries(
            derived_from="sentientos.federation_seed_health_history.persist_bounded_federation_seed_health_history",
            extra={
                "support_signal_only": True,
                "does_not_change_admission_or_readiness": True,
                "acts_as_federation_adjudicator": False,
            },
        ),
    }


def _transition_classification(
    *,
    previous_status: str | None,
    current_status: str,
    previous_has_fragmentation: bool,
    previous_has_admitted_failure: bool,
) -> str:
    if previous_status is None:
        return "initial_observation"
    if previous_status == current_status:
        return "unchanged"
    if previous_status == "fragmented" and current_status == "healthy":
        return "recovered_from_fragmentation"
    if current_status == "healthy" and (previous_status == "degraded" or previous_has_admitted_failure):
        return "recovered_from_failure"

    previous_rank = _STATUS_ORDER.get(previous_status)
    current_rank = _STATUS_ORDER.get(current_status)
    if previous_rank is None or current_rank is None:
        return "unchanged"
    if current_rank < previous_rank:
        return "improving"
    if current_rank > previous_rank:
        return "degrading"

    if previous_has_fragmentation and current_status != "fragmented":
        return "improving"
    return "unchanged"


def build_bounded_federation_seed_health_history_record(
    *,
    seed_health: dict[str, Any],
    previous_record: dict[str, Any] | None,
    evaluation_id: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    current_status = str(seed_health.get("health_status") or "fragmented")
    previous_status_raw = previous_record.get("health_status") if isinstance(previous_record, dict) else None
    previous_status = str(previous_status_raw) if isinstance(previous_status_raw, str) else None
    previous_has_fragmentation = bool((previous_record or {}).get("has_fragmentation"))
    previous_has_admitted_failure = bool((previous_record or {}).get("has_admitted_failure"))

    evaluated_at_value = evaluated_at or _utc_now_iso()
    transition = _transition_classification(
        previous_status=previous_status,
        current_status=current_status,
        previous_has_fragmentation=previous_has_fragmentation,
        previous_has_admitted_failure=previous_has_admitted_failure,
    )

    return {
        "scope": "bounded_federation_seed",
        "evaluation_id": evaluation_id or f"federation-seed-health:{evaluated_at_value}",
        "evaluated_at": evaluated_at_value,
        "health_status": current_status,
        "previous_health_status": previous_status,
        "transition_classification": transition,
        "per_intent_latest_outcome": dict(seed_health.get("per_intent_latest_outcome") or {}),
        "outcome_counts": dict(seed_health.get("outcome_counts") or {}),
        "has_fragmentation": bool(seed_health.get("has_fragmentation")),
        "has_admitted_failure": bool(seed_health.get("has_admitted_failure")),
        **non_sovereign_diagnostic_boundaries(
            derived_from="sentientos.federation_slice_health.synthesize_bounded_federation_seed_health",
            extra={
                "support_signal_only": True,
                "affects_admission": False,
                "affects_mergeability": False,
                "affects_runtime_governor_behavior": False,
                "acts_as_federation_adjudicator": False,
            },
        ),
    }


def persist_bounded_federation_seed_health_history(
    repo_root: Path,
    *,
    seed_health: dict[str, Any],
    history_limit: int = _DEFAULT_HISTORY_LIMIT,
    evaluation_id: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    history_path = root / _HISTORY_PATH
    history_rows = _read_jsonl(history_path)
    previous_record = history_rows[-1] if history_rows else None

    current_record = build_bounded_federation_seed_health_history_record(
        seed_health=seed_health,
        previous_record=previous_record,
        evaluation_id=evaluation_id,
        evaluated_at=evaluated_at,
    )

    bounded_rows = [*history_rows, current_record]
    if history_limit > 0 and len(bounded_rows) > history_limit:
        bounded_rows = bounded_rows[-history_limit:]

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in bounded_rows), encoding="utf-8")
    stability = derive_bounded_federation_seed_stability(bounded_rows)

    return {
        "history_path": _HISTORY_PATH,
        "current_record": current_record,
        "previous_record": previous_record,
        "recent_history": bounded_rows[-5:],
        "history_length": len(bounded_rows),
        "stability": stability,
        "diagnostic_only": True,
        "non_authoritative": True,
    }


__all__ = [
    "build_bounded_federation_seed_health_history_record",
    "derive_bounded_federation_seed_stability",
    "persist_bounded_federation_seed_health_history",
]
