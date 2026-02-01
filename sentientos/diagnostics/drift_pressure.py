from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from sentientos.diagnostics.drift_alerts import get_drift_summary, get_recent_drift_reports
from sentientos.pressure_queue import acknowledge_pressure_signal, enqueue_pressure_signal

DRIFT_COUNT_FIELDS = (
    "posture_stuck",
    "plugin_dominance",
    "motion_starvation",
    "anomaly_trend",
)


@dataclass(frozen=True)
class DriftSeverityThresholds:
    medium_total: int = 2
    high_total: int = 4
    high_single: int = 3


DRIFT_SEVERITY_THRESHOLDS = DriftSeverityThresholds()


def derive_drift_pressure_severity(counts: Mapping[str, int]) -> str:
    total = sum(int(value) for value in counts.values())
    if total == 0:
        return "none"
    if any(int(value) >= DRIFT_SEVERITY_THRESHOLDS.high_single for value in counts.values()):
        return "high"
    if total >= DRIFT_SEVERITY_THRESHOLDS.high_total:
        return "high"
    if total >= DRIFT_SEVERITY_THRESHOLDS.medium_total:
        return "medium"
    return "low"


def build_drift_pressure_signal(
    summary: Mapping[str, int],
    *,
    as_of_date: str | None,
    window_days: int | None = None,
) -> dict[str, object]:
    window = int(window_days or summary.get("days", 0) or 0)
    counts = {key: int(summary.get(key, 0) or 0) for key in DRIFT_COUNT_FIELDS}
    severity = derive_drift_pressure_severity(counts)
    digest_payload = {
        "as_of_date": as_of_date,
        "window_days": window,
        "counts": {key: counts[key] for key in sorted(counts)},
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "signal_type": "drift",
        "as_of_date": as_of_date,
        "window_days": window,
        "counts": counts,
        "severity": severity,
        "source": "drift_alerts",
        "digest": digest,
    }


def get_drift_pressure_signal(days: int = 7) -> dict[str, object]:
    summary = get_drift_summary(days)
    reports = get_recent_drift_reports(limit=summary.get("days", days))
    as_of_date = reports[0].get("date") if reports else None
    return build_drift_pressure_signal(
        summary,
        as_of_date=as_of_date if isinstance(as_of_date, str) else None,
        window_days=int(summary.get("days", days) or days),
    )


def enqueue_drift_pressure_signal(days: int = 7) -> dict[str, object] | None:
    signal = get_drift_pressure_signal(days)
    if signal["severity"] == "none":
        return None
    return enqueue_pressure_signal(signal)


def acknowledge_drift_pressure_signal(
    digest: str,
    *,
    actor: str | None = None,
) -> dict[str, object]:
    return acknowledge_pressure_signal(digest, actor=actor)


__all__ = [
    "DRIFT_COUNT_FIELDS",
    "DRIFT_SEVERITY_THRESHOLDS",
    "build_drift_pressure_signal",
    "derive_drift_pressure_severity",
    "acknowledge_drift_pressure_signal",
    "enqueue_drift_pressure_signal",
    "get_drift_pressure_signal",
]
