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
    has_contract_drift: bool | None
    drift_domains: list[str]
    contract_alert_badge: str | None
    contract_alert_reason: str | None
    contract_alert_counts: dict[str, int]
    contract_row_summary_counts: dict[str, int]
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
    contract_digest = _contract_digest_from_report(report_json)
    alert_counts = _as_dict(contract_digest.get("contract_alert_counts"))
    row_counts = _as_dict(contract_digest.get("contract_row_summary_counts"))
    drift_domains_raw = contract_digest.get("drift_domains")
    drift_domains = [str(item) for item in drift_domains_raw if isinstance(item, str)] if isinstance(drift_domains_raw, list) else []

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
        has_contract_drift=bool(contract_digest.get("has_drift")) if "has_drift" in contract_digest else None,
        drift_domains=drift_domains,
        contract_alert_badge=_as_str(contract_digest.get("contract_alert_badge")),
        contract_alert_reason=_as_str(contract_digest.get("contract_alert_reason")),
        contract_alert_counts={
            "freshness_issue": _as_count(alert_counts.get("freshness_issue")),
            "domain_drift": _as_count(alert_counts.get("domain_drift")),
            "baseline_absent": _as_count(alert_counts.get("baseline_absent")),
            "partial_evidence": _as_count(alert_counts.get("partial_evidence")),
            "informational": _as_count(alert_counts.get("informational")),
        },
        contract_row_summary_counts={
            "row_count": _as_count(row_counts.get("row_count")),
            "drifted_rows": _as_count(row_counts.get("drifted_rows")),
            "baseline_missing_rows": _as_count(row_counts.get("baseline_missing_rows")),
            "indeterminate_rows": _as_count(row_counts.get("indeterminate_rows")),
            "stale_or_missing_rows": _as_count(row_counts.get("stale_or_missing_rows")),
        },
        created_at=created_at,
    )


def _contract_digest_from_report(report_json: dict[str, Any]) -> dict[str, Any]:
    after = report_json.get("transaction_snapshot_after")
    if isinstance(after, dict):
        digest = after.get("contract_status_digest")
        if isinstance(digest, dict):
            return digest
    digest_after = report_json.get("contract_status_digest_after")
    if isinstance(digest_after, dict):
        return digest_after
    digest_preflight = report_json.get("contract_status_digest_preflight")
    if isinstance(digest_preflight, dict):
        return digest_preflight
    preflight = report_json.get("preflight")
    if isinstance(preflight, dict):
        digest = preflight.get("contract_status_digest")
        if isinstance(digest, dict):
            return digest
    return {}


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
