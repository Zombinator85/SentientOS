from __future__ import annotations

import datetime as _dt
import json
import os
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

import memory_manager as mm
from logging_config import get_log_path
from sentientos.embodiment.embodiment_digest import get_recent_embodiment_digest

_ANOMALY_DIR = Path(os.getenv("PULSE_ANOMALY_DIR", "/pulse/anomalies"))
_KERNEL_SNAPSHOT_LOG = get_log_path("kernel_snapshots.jsonl", "KERNEL_SNAPSHOT_LOG")
_SILHOUETTE_DIR = Path("glow") / "silhouettes"

_SEVERITY_MAP = {
    "critical": "critical",
    "high": "critical",
    "moderate": "moderate",
    "warning": "moderate",
    "medium": "moderate",
    "low": "low",
    "info": "low",
}


def _coerce_timestamp(value: object) -> _dt.datetime | None:
    if isinstance(value, _dt.datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value)
    except Exception:
        return None


def _iter_anomaly_paths(start: _dt.datetime, end: _dt.datetime) -> Iterable[Path]:
    if not _ANOMALY_DIR.exists():
        return []
    start_date = start.date()
    end_date = end.date()
    paths: list[Path] = []
    for path in sorted(_ANOMALY_DIR.glob("*.jsonl")):
        stem = path.stem
        try:
            file_date = _dt.date.fromisoformat(stem)
        except ValueError:
            continue
        if start_date <= file_date <= end_date:
            paths.append(path)
    return paths


def _iter_jsonl_entries(paths: Iterable[Path]) -> Iterable[Mapping[str, object]]:
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, Mapping):
                yield payload


def _normalize_severity(value: object) -> str:
    if not isinstance(value, str):
        return "low"
    return _SEVERITY_MAP.get(value.strip().lower(), "low")


def _extract_channel(entry: Mapping[str, object]) -> str:
    for key in ("channel", "kind", "source", "stream"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _extract_delta_signals(entry: Mapping[str, object]) -> Mapping[str, int] | None:
    candidates = []
    direct = entry.get("delta_signals")
    if isinstance(direct, Mapping):
        candidates.append(direct)
    embodiment = entry.get("embodiment")
    if isinstance(embodiment, Mapping):
        inner = embodiment.get("delta_signals")
        if isinstance(inner, Mapping):
            candidates.append(inner)
    payload = entry.get("payload")
    if isinstance(payload, Mapping):
        payload_embodiment = payload.get("embodiment")
        if isinstance(payload_embodiment, Mapping):
            inner = payload_embodiment.get("delta_signals")
            if isinstance(inner, Mapping):
                candidates.append(inner)
        inner = payload.get("delta_signals")
        if isinstance(inner, Mapping):
            candidates.append(inner)
    for candidate in candidates:
        normalized: dict[str, int] = {}
        for key, value in candidate.items():
            if not isinstance(key, str):
                continue
            try:
                normalized[key] = int(value)
            except (TypeError, ValueError):
                continue
        if normalized:
            return normalized
    return None


def _extract_kernel_epoch(entry: Mapping[str, object]) -> int | None:
    if isinstance(entry.get("kernel_epoch"), int):
        return entry["kernel_epoch"]
    governance = entry.get("governance")
    if isinstance(governance, Mapping):
        value = governance.get("kernel_epoch")
        if isinstance(value, int):
            return value
    payload = entry.get("payload")
    if isinstance(payload, Mapping):
        governance_payload = payload.get("governance")
        if isinstance(governance_payload, Mapping):
            value = governance_payload.get("kernel_epoch")
            if isinstance(value, int):
                return value
        value = payload.get("kernel_epoch")
        if isinstance(value, int):
            return value
    return None


def _load_kernel_snapshots(start: _dt.datetime, end: _dt.datetime) -> list[Mapping[str, object]]:
    if not _KERNEL_SNAPSHOT_LOG.exists():
        return []
    snapshots: list[Mapping[str, object]] = []
    try:
        lines = _KERNEL_SNAPSHOT_LOG.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, Mapping):
            continue
        ts = _coerce_timestamp(payload.get("timestamp"))
        if ts is None:
            continue
        if start <= ts <= end:
            snapshots.append(payload)
    snapshots.sort(key=lambda entry: str(entry.get("timestamp", "")))
    return snapshots


def _sum_motion_deltas(snapshots: Iterable[Mapping[str, object]]) -> dict[str, int]:
    totals = {
        "motion_detected": 0,
        "noise_events": 0,
        "absence_periods": 0,
    }
    prior: Mapping[str, int] | None = None
    for entry in snapshots:
        delta_signals = _extract_delta_signals(entry)
        if not delta_signals:
            continue
        if prior is None:
            for key in totals:
                if key in delta_signals:
                    totals[key] += max(0, int(delta_signals[key]))
            prior = delta_signals
            continue
        for key in totals:
            if key not in delta_signals or key not in prior:
                continue
            diff = delta_signals[key] - prior[key]
            if diff > 0:
                totals[key] += diff
        prior = delta_signals
    return totals


def compute_daily_silhouette(start_time: _dt.datetime, end_time: _dt.datetime) -> dict:
    if start_time > end_time:
        raise ValueError("start_time must be <= end_time")
    date_value = start_time.date().isoformat()

    digest_entries = get_recent_embodiment_digest(n=float("inf"))
    posture_counts: Counter[str] = Counter()
    plugin_counts: Counter[str] = Counter()
    epoch_ids: set[int] = set()
    for entry in digest_entries:
        ts = _coerce_timestamp(entry.get("timestamp"))
        if ts is None or not (start_time <= ts <= end_time):
            continue
        posture = entry.get("posture")
        if isinstance(posture, str) and posture:
            posture_counts[posture] += 1
        plugin = entry.get("plugin")
        if isinstance(plugin, str) and plugin:
            plugin_counts[plugin] += 1
        epoch_id = entry.get("epoch_id")
        if isinstance(epoch_id, int):
            epoch_ids.add(epoch_id)

    snapshots = _load_kernel_snapshots(start_time, end_time)
    motion_deltas = _sum_motion_deltas(snapshots)

    snapshot_epoch_ids: set[int] = set()
    for entry in snapshots:
        epoch_id = _extract_kernel_epoch(entry)
        if epoch_id is not None:
            snapshot_epoch_ids.add(epoch_id)

    kernel_epoch_count = len(snapshot_epoch_ids or epoch_ids)

    anomaly_entries = []
    for entry in _iter_jsonl_entries(_iter_anomaly_paths(start_time, end_time)):
        ts = _coerce_timestamp(entry.get("timestamp"))
        if ts is None or not (start_time <= ts <= end_time):
            continue
        anomaly_entries.append((ts, entry))
    anomaly_entries.sort(key=lambda item: item[0])

    severity_counts: Counter[str] = Counter()
    latest_anomaly = None
    for ts, entry in anomaly_entries:
        severity = _normalize_severity(entry.get("severity"))
        severity_counts[severity] += 1
        latest_anomaly = {
            "timestamp": ts.strftime("%H:%M"),
            "channel": _extract_channel(entry),
            "severity": severity,
        }

    anomalies_payload = {
        "severity_counts": {
            "low": severity_counts.get("low", 0),
            "moderate": severity_counts.get("moderate", 0),
            "critical": severity_counts.get("critical", 0),
        },
        "latest_anomaly": latest_anomaly,
    }

    payload = {
        "date": date_value,
        "posture_counts": dict(sorted(posture_counts.items())),
        "plugin_usage": dict(sorted(plugin_counts.items())),
        "motion_deltas": motion_deltas,
        "kernel_epoch_count": kernel_epoch_count,
        "anomalies": anomalies_payload,
        "metadata": {"source": "embodiment_silhouette"},
    }
    return payload


def write_daily_silhouette(start_time: _dt.datetime, end_time: _dt.datetime) -> Path:
    payload = compute_daily_silhouette(start_time, end_time)
    date_value = payload.get("date")
    if not isinstance(date_value, str):
        raise ValueError("silhouette payload missing date")
    _SILHOUETTE_DIR.mkdir(parents=True, exist_ok=True)
    path = _SILHOUETTE_DIR / f"{date_value}.json"
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    tags = ["silhouette_summary", f"silhouette_date:{date_value}"]
    anomaly_present = False
    anomalies = payload.get("anomalies")
    if isinstance(anomalies, Mapping):
        latest = anomalies.get("latest_anomaly")
        severity_counts = anomalies.get("severity_counts")
        if latest or (isinstance(severity_counts, Mapping) and any(severity_counts.values())):
            anomaly_present = True
    if anomaly_present:
        tags.append("silhouette_anomaly")

    mm.append_memory(
        json.dumps(payload, sort_keys=True, ensure_ascii=False),
        tags=tags,
        source="embodiment_silhouette",
        meta={"date": date_value, "anomaly_present": anomaly_present},
    )
    return path
