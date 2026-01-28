from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Iterable

from logging_config import get_log_path
from log_utils import read_json


_DRIFT_TYPE_FLAGS = {
    "POSTURE_STUCK": "posture_stuck",
    "PLUGIN_DOMINANCE": "plugin_dominance",
    "MOTION_STARVATION": "motion_starvation",
    "ANOMALY_ESCALATION": "anomaly_trend",
}

_SILHOUETTE_ENV = "SENTIENTOS_SILHOUETTE_DIR"
_DATA_ROOT_ENV = "SENTIENTOS_DATA_DIR"


def normalize_drift_date(value: str) -> str:
    normalized = _parse_date(value)
    if normalized is None:
        raise ValueError(f"Invalid date: {value}")
    return normalized


def get_recent_drift_reports(limit: int = 7) -> list[dict[str, object]]:
    reports = _collect_reports(_load_drift_entries())
    ordered = _sort_reports(reports)
    if limit is None:
        return ordered
    limit = _coerce_positive(limit, 7)
    return ordered[:limit]


def get_drift_report_for_date(date_str: str) -> dict[str, object]:
    normalized = normalize_drift_date(date_str)
    reports = _collect_reports(_load_drift_entries())
    return reports.get(normalized, _empty_report(normalized))


def get_drift_summary(days: int = 7) -> dict[str, int]:
    days = _coerce_positive(days, 7)
    reports = get_recent_drift_reports(limit=days)
    summary = {
        "days": days,
        "total": 0,
        "posture_stuck": 0,
        "plugin_dominance": 0,
        "motion_starvation": 0,
        "anomaly_trend": 0,
    }
    for report in reports:
        if _has_any_drift(report):
            summary["total"] += 1
        for flag in _DRIFT_TYPE_FLAGS.values():
            if report.get(flag):
                summary[flag] += 1
    return summary


def get_silhouette_path(date_str: str) -> Path | None:
    normalized = normalize_drift_date(date_str)
    filename = f"{normalized}.json"
    for base in _candidate_silhouette_dirs():
        path = base / filename
        if path.exists():
            return path
    return None


def get_silhouette_payload(date_str: str) -> dict[str, object] | None:
    path = get_silhouette_path(date_str)
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _load_drift_entries() -> list[dict[str, object]]:
    log_path = get_log_path("drift_detector.jsonl", "DRIFT_DETECTOR_LOG")
    if not log_path.exists():
        return []
    return read_json(log_path)


def _collect_reports(entries: Iterable[dict[str, object]]) -> dict[str, dict[str, object]]:
    reports: dict[str, dict[str, object]] = {}
    for entry in entries:
        if entry.get("type") != "drift_detected":
            continue
        drift_type = entry.get("drift_type")
        flag = _DRIFT_TYPE_FLAGS.get(drift_type)
        if not flag:
            continue
        date_value = _entry_date(entry)
        if date_value is None:
            continue
        report = reports.get(date_value)
        if report is None:
            report = _empty_report(date_value)
            reports[date_value] = report
        report[flag] = True
    for report in reports.values():
        report["tags"] = ["DRIFT", "ALERT"] if _has_any_drift(report) else []
    return reports


def _entry_date(entry: dict[str, object]) -> str | None:
    dates = entry.get("dates")
    if isinstance(dates, list):
        for raw in dates:
            parsed = _parse_date(raw)
            if parsed:
                return parsed
    return _parse_date(entry.get("timestamp"))


def _parse_date(value: object) -> str | None:
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return _dt.date.fromisoformat(raw).isoformat()
        except ValueError:
            try:
                return _dt.datetime.fromisoformat(raw).date().isoformat()
            except ValueError:
                return None
    return None


def _empty_report(date_value: str) -> dict[str, object]:
    return {
        "date": date_value,
        "posture_stuck": False,
        "plugin_dominance": False,
        "motion_starvation": False,
        "anomaly_trend": False,
        "tags": [],
        "source": "drift_detector",
    }


def _sort_reports(reports: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    def sort_key(report: dict[str, object]) -> _dt.date:
        value = report.get("date")
        if isinstance(value, str):
            try:
                return _dt.date.fromisoformat(value)
            except ValueError:
                pass
        return _dt.date.min

    return sorted(reports.values(), key=sort_key, reverse=True)


def _has_any_drift(report: dict[str, object]) -> bool:
    return any(report.get(flag) for flag in _DRIFT_TYPE_FLAGS.values())


def _coerce_positive(value: int | None, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _candidate_silhouette_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_dir = os.environ.get(_SILHOUETTE_ENV)
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path("glow") / "silhouettes")
    data_root = os.environ.get(_DATA_ROOT_ENV)
    if data_root:
        candidates.append(Path(data_root) / "glow" / "silhouettes")
    else:
        candidates.append(Path.cwd() / "sentientos_data" / "glow" / "silhouettes")
    return candidates


__all__ = [
    "get_drift_report_for_date",
    "get_drift_summary",
    "get_recent_drift_reports",
    "get_silhouette_path",
    "get_silhouette_payload",
    "normalize_drift_date",
]
