"""Helpers for extracting durable outcome summaries from forge reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class OutcomeSummary:
    run_id: str
    goal_id: str | None
    campaign_id: str | None
    outcome: str
    ci_before_failed_count: int | None
    ci_after_failed_count: int | None
    progress_delta_percent: float | None
    last_progress_improved: bool
    last_progress_notes: list[str]
    no_improvement_streak: int
    audit_status: str | None
    created_at: str


def summarize_report(report_json: dict[str, Any]) -> OutcomeSummary:
    run_id = _as_str(report_json.get("provenance_run_id")) or _as_str(report_json.get("run_id")) or _as_str(report_json.get("generated_at")) or ""
    goal_id = _as_str(report_json.get("goal_id"))
    campaign_id = _as_str(report_json.get("campaign_id"))
    outcome = _as_str(report_json.get("outcome")) or "failed"
    created_at = _as_str(report_json.get("generated_at")) or _iso_now()

    before_ci = report_json.get("ci_baseline_before") if isinstance(report_json.get("ci_baseline_before"), dict) else {}
    after_ci = report_json.get("ci_baseline_after") if isinstance(report_json.get("ci_baseline_after"), dict) else {}
    progress_delta = report_json.get("progress_delta") if isinstance(report_json.get("progress_delta"), dict) else {}
    baseline_progress = report_json.get("baseline_progress") if isinstance(report_json.get("baseline_progress"), list) else []

    ci_before_failed = _as_int(before_ci.get("failed_count"))
    ci_after_failed = _as_int(after_ci.get("failed_count"))

    if ci_before_failed is None:
        ci_before_failed = _as_int(report_json.get("test_failures_before"))
    if ci_after_failed is None:
        ci_after_failed = _as_int(report_json.get("test_failures_after"))

    progress_delta_percent = _as_float(progress_delta.get("reduction_pct"))
    if progress_delta_percent is None:
        progress_delta_percent = _as_float(progress_delta.get("progress_delta_percent"))

    last_progress_improved = False
    last_progress_notes: list[str] = []
    if baseline_progress:
        last_record = baseline_progress[-1]
        if isinstance(last_record, dict):
            raw_notes = last_record.get("notes")
            if isinstance(raw_notes, list):
                last_progress_notes.extend(str(item) for item in raw_notes if isinstance(item, str))
            delta_payload = last_record.get("delta")
            if isinstance(delta_payload, dict):
                last_progress_improved = bool(delta_payload.get("improved", False))
                delta_notes = delta_payload.get("notes")
                if isinstance(delta_notes, list):
                    last_progress_notes.extend(str(item) for item in delta_notes if isinstance(item, str))

    if not baseline_progress:
        if ci_before_failed is not None and ci_after_failed is not None:
            last_progress_improved = ci_after_failed < ci_before_failed
        elif progress_delta_percent is not None:
            last_progress_improved = progress_delta_percent > 0

    bounded_notes = last_progress_notes[:8]

    no_improvement_streak = _as_int(report_json.get("no_improvement_streak"))
    if no_improvement_streak is None:
        no_improvement_streak = _infer_no_improvement_streak(baseline_progress)

    doctrine = report_json.get("stability_doctrine") if isinstance(report_json.get("stability_doctrine"), dict) else {}
    audit_status = _as_str(report_json.get("audit_status")) or _as_str(doctrine.get("audit_strict_status"))

    return OutcomeSummary(
        run_id=run_id,
        goal_id=goal_id,
        campaign_id=campaign_id,
        outcome=outcome,
        ci_before_failed_count=ci_before_failed,
        ci_after_failed_count=ci_after_failed,
        progress_delta_percent=progress_delta_percent,
        last_progress_improved=last_progress_improved,
        last_progress_notes=bounded_notes,
        no_improvement_streak=no_improvement_streak,
        audit_status=audit_status,
        created_at=created_at,
    )


def _infer_no_improvement_streak(progress: list[Any]) -> int:
    streak = 0
    for row in reversed(progress):
        if not isinstance(row, dict):
            continue
        delta_payload = row.get("delta")
        if not isinstance(delta_payload, dict):
            continue
        if bool(delta_payload.get("improved", False)):
            break
        streak += 1
    return streak


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

