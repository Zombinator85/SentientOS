from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HISTORY_PATH = "glow/contracts/constitutional_execution_fabric_scoped_slice_health_history.jsonl"
_DEFAULT_HISTORY_LIMIT = 64
_STATUS_ORDER: dict[str, int] = {"healthy": 0, "degraded": 1, "fragmented": 2}


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

    if previous_has_fragmentation and not (current_status == "fragmented"):
        return "improving"
    return "unchanged"


def build_scoped_slice_health_history_record(
    *,
    slice_health: dict[str, Any],
    previous_record: dict[str, Any] | None,
    evaluation_id: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    current_status = str(slice_health.get("slice_health_status") or "fragmented")
    previous_status_raw = previous_record.get("slice_health_status") if isinstance(previous_record, dict) else None
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
        "scope": "constitutional_execution_fabric_scoped_slice",
        "evaluation_id": evaluation_id or f"slice-health:{evaluated_at_value}",
        "evaluated_at": evaluated_at_value,
        "slice_health_status": current_status,
        "previous_slice_health_status": previous_status,
        "transition_classification": transition,
        "per_action_latest_outcome": dict(slice_health.get("per_action_latest_outcome") or {}),
        "outcome_counts": dict(slice_health.get("outcome_counts") or {}),
        "has_fragmentation": bool(slice_health.get("has_fragmentation")),
        "has_admitted_failure": bool(slice_health.get("has_admitted_failure")),
        "diagnostic_only": True,
        "non_authoritative": True,
        "derived_from": "scoped_slice_health_synthesis",
        "decision_power": "none",
    }


def persist_scoped_slice_health_history(
    repo_root: Path,
    *,
    slice_health: dict[str, Any],
    history_limit: int = _DEFAULT_HISTORY_LIMIT,
    evaluation_id: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    history_path = root / _HISTORY_PATH
    history_rows = _read_jsonl(history_path)
    previous_record = history_rows[-1] if history_rows else None

    current_record = build_scoped_slice_health_history_record(
        slice_health=slice_health,
        previous_record=previous_record,
        evaluation_id=evaluation_id,
        evaluated_at=evaluated_at,
    )

    bounded_rows = [*history_rows, current_record]
    if history_limit > 0 and len(bounded_rows) > history_limit:
        bounded_rows = bounded_rows[-history_limit:]

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in bounded_rows), encoding="utf-8")

    return {
        "history_path": _HISTORY_PATH,
        "current_record": current_record,
        "previous_record": previous_record,
        "recent_history": bounded_rows[-5:],
        "history_length": len(bounded_rows),
        "diagnostic_only": True,
        "non_authoritative": True,
    }
