"""Query interface for pulse history events and monitoring metrics."""

from __future__ import annotations

import base64
import binascii
import copy
import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


logger = logging.getLogger(__name__)

MAX_EVENT_RESULTS = 10_000

_ALLOWED_FILTERS = {"priority", "source_daemon", "event_type"}
_HISTORY_FILENAME = re.compile(r"pulse_(\d{4}-\d{2}-\d{2})\.jsonl$")
_WINDOW_PATTERN = re.compile(
    r"(?:(?:last)\s+)?(\d+)\s*(s|sec|secs|seconds|m|min|mins|minutes|h|hour|hours|d|day|days)?"
)

_LEDGER_PATH = Path(os.getenv("CODEX_LEDGER_PATH", "/daemon/logs/codex.jsonl"))
_PULSE_HISTORY_ROOT = Path(os.getenv("PULSE_HISTORY_ROOT", "/glow/pulse_history"))
_METRICS_PATH = Path(
    os.getenv(
        "MONITORING_METRICS_PATH",
        str(Path(os.getenv("MONITORING_GLOW_ROOT", "/glow/monitoring")) / "metrics.jsonl"),
    )
)

_VERIFY_KEY_LOCK = threading.Lock()
_VERIFY_KEY: VerifyKey | None = None
_LEDGER_LOCK = threading.Lock()

_BANNED_SEGMENTS = {"vow", "newlegacy"}
_BANNED_KEYWORDS = ("privileged",)


def _ensure_safe_path(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    lowered = [part.lower() for part in resolved.parts]
    for segment in lowered:
        if segment in _BANNED_SEGMENTS:
            raise PermissionError(f"Access to {resolved} is not permitted")
        if any(keyword in segment for keyword in _BANNED_KEYWORDS):
            raise PermissionError(f"Access to {resolved} is not permitted")
    return resolved


def _load_verify_key() -> VerifyKey:
    global _VERIFY_KEY
    with _VERIFY_KEY_LOCK:
        if _VERIFY_KEY is not None:
            return _VERIFY_KEY
        key_path_value = os.getenv("PULSE_VERIFY_KEY")
        if not key_path_value:
            raise RuntimeError("PULSE_VERIFY_KEY is required to verify query results")
        key_path = _ensure_safe_path(Path(key_path_value))
        try:
            data = key_path.read_bytes()
        except FileNotFoundError as exc:
            raise RuntimeError(f"Pulse verify key missing at {key_path}") from exc
        _VERIFY_KEY = VerifyKey(data)
        return _VERIFY_KEY


def _serialize_event_for_signature(event: Mapping[str, object]) -> bytes:
    payload = copy.deepcopy(dict(event))
    payload.pop("signature", None)
    payload.pop("source_peer", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _serialize_snapshot_payload(snapshot: Mapping[str, object]) -> bytes:
    payload = {key: value for key, value in snapshot.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_timestamp(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_window(value: str) -> timedelta:
    """Parse a textual time window such as ``"24h"`` into a ``timedelta``."""

    if not value:
        raise ValueError("Window value must be provided")
    text = value.strip().lower()
    match = _WINDOW_PATTERN.fullmatch(text)
    if not match:
        raise ValueError(f"Unsupported window expression: {value}")
    amount = int(match.group(1))
    unit = match.group(2) or "h"
    return timedelta(seconds=_unit_to_seconds(amount, unit))


def parse_iso_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware ``datetime`` value."""

    dt = _parse_timestamp(value)
    if dt == datetime.fromtimestamp(0, tz=timezone.utc):
        raise ValueError(f"Invalid ISO timestamp: {value}")
    return dt


def _unit_to_seconds(value: int, unit: str) -> int:
    unit = unit.lower()
    if unit in {"s", "sec", "secs", "seconds"}:
        return value
    if unit in {"m", "min", "mins", "minutes"}:
        return value * 60
    if unit in {"h", "hour", "hours"}:
        return value * 3600
    if unit in {"d", "day", "days"}:
        return value * 86400
    raise ValueError(f"Unsupported time unit: {unit}")


def _normalize_filters(filters: Mapping[str, object] | None) -> Dict[str, str]:
    if filters is None:
        return {}
    if not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping")
    normalized: Dict[str, str] = {}
    for key, value in filters.items():
        if value is None:
            continue
        if key not in _ALLOWED_FILTERS:
            raise ValueError(f"Unsupported filter: {key}")
        if key == "priority":
            normalized[key] = str(value).lower()
        else:
            normalized[key] = str(value)
    return normalized


def _history_root() -> Path:
    return _ensure_safe_path(_PULSE_HISTORY_ROOT)


def _metrics_path() -> Path:
    return _ensure_safe_path(_METRICS_PATH)


def _iter_history_files(cutoff: datetime) -> Iterable[Path]:
    root = _history_root()
    if not root.exists():
        return []
    resolved_root = root.resolve(strict=False)
    files = sorted(path for path in root.glob("pulse_*.jsonl") if path.is_file())
    filtered: List[Path] = []
    cutoff_date = cutoff.date()
    for path in files:
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            continue
        if not resolved.is_relative_to(resolved_root):
            continue
        match = _HISTORY_FILENAME.match(path.name)
        if not match:
            continue
        try:
            file_date = datetime.fromisoformat(match.group(1)).date()
        except ValueError:
            continue
        if file_date < cutoff_date:
            continue
        filtered.append(resolved)
    return filtered


def _load_events_from_file(path: Path, cutoff: datetime) -> Iterable[dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed pulse entry in %s", path)
                    continue
                if not isinstance(event, dict):
                    continue
                if not _event_signature_valid(event):
                    continue
                timestamp = _parse_timestamp(str(event.get("timestamp", "")))
                if timestamp < cutoff:
                    continue
                yield copy.deepcopy(event)
    except FileNotFoundError:  # pragma: no cover - removed concurrently
        return


def _event_signature_valid(event: Mapping[str, object]) -> bool:
    signature = event.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    source_peer = event.get("source_peer")
    if source_peer not in (None, "local"):
        return False
    try:
        signature_bytes = base64.b64decode(signature)
    except (ValueError, binascii.Error):
        return False
    verify_key = _load_verify_key()
    try:
        verify_key.verify(_serialize_event_for_signature(event), signature_bytes)
        return True
    except BadSignatureError:
        logger.warning("Rejecting pulse event with invalid signature")
        return False


def _event_matches_filters(event: Mapping[str, object], filters: Mapping[str, str]) -> bool:
    if "priority" in filters and str(event.get("priority", "")).lower() != filters["priority"]:
        return False
    if "source_daemon" in filters and str(event.get("source_daemon", "")) != filters["source_daemon"]:
        return False
    if "event_type" in filters and str(event.get("event_type", "")) != filters["event_type"]:
        return False
    return True


def query_events(
    since: datetime,
    filters: Mapping[str, object] | None = None,
    *,
    requester: str = "local",
) -> List[dict[str, object]]:
    """Return verified pulse events since ``since`` applying ``filters``."""

    if not isinstance(since, datetime):
        raise TypeError("since must be a datetime instance")
    cutoff = _ensure_utc(since)
    normalized_filters = _normalize_filters(filters)
    events: List[dict[str, object]] = []
    for path in _iter_history_files(cutoff):
        for event in _load_events_from_file(path, cutoff):
            if not _event_matches_filters(event, normalized_filters):
                continue
            events.append(event)
            if len(events) >= MAX_EVENT_RESULTS:
                break
        if len(events) >= MAX_EVENT_RESULTS:
            break
    _log_query(
        "events",
        requester,
        {**normalized_filters, "since": cutoff.isoformat()},
        len(events),
    )
    return events


def get_events(since: datetime, filters: Mapping[str, object] | None = None) -> List[dict[str, object]]:
    """Return verified pulse events for local callers."""

    return query_events(since, filters, requester="local")


def _load_snapshots() -> List[dict[str, object]]:
    path = _metrics_path()
    if not path.exists():
        return []
    snapshots: Dict[str, dict[str, object]] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                entry = line.strip()
                if not entry:
                    continue
                try:
                    snapshot = json.loads(entry)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed snapshot entry in %s", path)
                    continue
                if not isinstance(snapshot, dict):
                    continue
                if not _snapshot_signature_valid(snapshot):
                    continue
                timestamp = str(snapshot.get("timestamp", ""))
                if not timestamp:
                    continue
                snapshots[timestamp] = snapshot
    except FileNotFoundError:  # pragma: no cover - removed concurrently
        return []
    return [snapshots[key] for key in sorted(snapshots)]


def _snapshot_signature_valid(snapshot: Mapping[str, object]) -> bool:
    signature = snapshot.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    try:
        signature_bytes = base64.b64decode(signature)
    except (ValueError, binascii.Error):
        return False
    verify_key = _load_verify_key()
    try:
        verify_key.verify(_serialize_snapshot_payload(snapshot), signature_bytes)
        return True
    except BadSignatureError:
        logger.warning("Rejecting monitoring snapshot with invalid signature")
        return False


def _available_windows(snapshots: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    available: Dict[str, int] = {}
    for snapshot in snapshots:
        windows = snapshot.get("windows")
        if not isinstance(windows, Mapping):
            continue
        for label, metrics in windows.items():
            if not isinstance(label, str) or not isinstance(metrics, Mapping):
                continue
            seconds = metrics.get("window_seconds")
            if isinstance(seconds, (int, float)):
                available[label.strip().lower()] = int(seconds)
    return available


def _resolve_window_label(window: str, available: Mapping[str, int]) -> str:
    if not window:
        raise ValueError("Window value must be provided")
    if not available:
        raise ValueError("No monitoring snapshots available")
    normalized = window.strip().lower()
    if normalized.startswith("last "):
        normalized = normalized[5:].strip()
    if normalized in available:
        return normalized
    match = _WINDOW_PATTERN.fullmatch(normalized)
    if match:
        seconds = _unit_to_seconds(int(match.group(1)), match.group(2) or "h")
        for label, duration in available.items():
            if duration == seconds:
                return label
    raise ValueError(f"Window {window} is not available")


def _apply_metrics_filters(
    metrics: Mapping[str, object],
    filters: Mapping[str, str],
) -> Dict[str, object]:
    duration_seconds = int(metrics.get("window_seconds", 0))
    duration = timedelta(seconds=max(duration_seconds, 0)) if duration_seconds else None
    if not filters:
        summary = dict(metrics)
        total = int(summary.get("total_events", 0))
        if duration_seconds:
            minutes = max(duration_seconds / 60, 1e-9)
            hours = max(duration_seconds / 3600, 1e-9)
            summary.setdefault("rate_per_minute", total / minutes)
            summary.setdefault("rate_per_hour", total / hours)
        return summary

    per_daemon = metrics.get("per_daemon")
    if not isinstance(per_daemon, Mapping):
        return {"total_events": 0, "priority": {}, "source_daemon": {}, "event_type": {}, "rate_per_minute": 0.0, "rate_per_hour": 0.0}

    from collections import Counter

    priority_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    event_type_counts: Counter[str] = Counter()
    total = 0

    for daemon, data_obj in per_daemon.items():
        if "source_daemon" in filters and daemon != filters["source_daemon"]:
            continue
        if not isinstance(data_obj, Mapping):
            continue
        matrix = data_obj.get("matrix")
        if not isinstance(matrix, Mapping):
            continue
        for priority, event_counts in matrix.items():
            if "priority" in filters and priority != filters["priority"]:
                continue
            if not isinstance(event_counts, Mapping):
                continue
            for event_type, count in event_counts.items():
                if "event_type" in filters and event_type != filters["event_type"]:
                    continue
                if not isinstance(count, int) or count <= 0:
                    continue
                total += count
                priority_counts[priority] += count
                source_counts[str(daemon)] += count
                event_type_counts[str(event_type)] += count

    minutes = max(duration_seconds / 60, 1e-9)
    hours = max(duration_seconds / 3600, 1e-9)
    return {
        "total_events": total,
        "priority": {key: priority_counts[key] for key in sorted(priority_counts)},
        "source_daemon": {key: source_counts[key] for key in sorted(source_counts)},
        "event_type": {key: event_type_counts[key] for key in sorted(event_type_counts)},
        "rate_per_minute": total / minutes if duration_seconds else 0.0,
        "rate_per_hour": total / hours if duration_seconds else 0.0,
    }


def _filter_anomalies(
    anomalies: Sequence[Mapping[str, object]] | Mapping[str, object] | None,
    filters: Mapping[str, str],
) -> List[dict[str, object]]:
    result: List[dict[str, object]] = []
    if not anomalies:
        return result
    iterable: Sequence[Mapping[str, object]]
    if isinstance(anomalies, Mapping):
        iterable = [anomalies]
    else:
        iterable = list(anomalies)
    for anomaly in iterable:
        if not isinstance(anomaly, Mapping):
            continue
        if "source_daemon" in filters and anomaly.get("source_daemon") != filters["source_daemon"]:
            continue
        if "priority" in filters and anomaly.get("priority") != filters["priority"]:
            continue
        if "event_type" in filters and anomaly.get("event_type") != filters["event_type"]:
            continue
        result.append(dict(anomaly))
    return result


def query_metrics(
    window: str,
    filters: Mapping[str, object] | None = None,
    *,
    requester: str = "local",
) -> dict[str, object]:
    """Return verified monitoring metrics for ``window`` applying ``filters``."""

    if not isinstance(window, str):
        raise TypeError("window must be a string")
    normalized_filters = _normalize_filters(filters)
    snapshots = _load_snapshots()
    available = _available_windows(snapshots)
    label = _resolve_window_label(window, available)

    latest_snapshot: dict[str, object] | None = None
    for snapshot in snapshots:
        windows = snapshot.get("windows")
        if not isinstance(windows, Mapping):
            continue
        metrics = windows.get(label)
        if not isinstance(metrics, Mapping):
            continue
        latest_snapshot = {
            "timestamp": str(snapshot.get("timestamp", "")),
            "metrics": metrics,
            "anomalies": snapshot.get("anomalies", []),
        }

    if latest_snapshot is None:
        raise ValueError(f"Window {label} not present in monitoring snapshots")

    summary = _apply_metrics_filters(latest_snapshot["metrics"], normalized_filters)
    anomalies = _filter_anomalies(latest_snapshot["anomalies"], normalized_filters)
    response = {
        "window": label,
        "filters": normalized_filters,
        "summary": summary,
        "anomalies": anomalies,
        "verified_snapshots": [latest_snapshot["timestamp"]],
    }
    _log_query("metrics", requester, {**normalized_filters, "window": label}, 1)
    return response


def get_metrics(window: str, filters: Mapping[str, object] | None = None) -> dict[str, object]:
    """Return monitoring metrics for local callers."""

    return query_metrics(window, filters, requester="local")


def _log_query(
    kind: str,
    requester: str,
    filters: Mapping[str, object],
    count: int,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "requester": requester,
        "query": kind,
        "filters": dict(filters),
        "count": int(count),
    }
    path = _ensure_safe_path(_LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LEDGER_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


__all__ = ["MAX_EVENT_RESULTS", "get_events", "get_metrics", "parse_window", "parse_iso_timestamp", "query_events", "query_metrics"]

