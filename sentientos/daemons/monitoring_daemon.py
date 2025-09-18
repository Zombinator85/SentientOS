"""Monitoring daemon that aggregates pulse metrics and anomalies."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Mapping, Sequence, cast

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from logging_config import get_log_path
from log_utils import append_json

from . import pulse_bus


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _EventRecord:
    """Simplified view of a pulse event for aggregation."""

    timestamp: datetime
    priority: str
    source_daemon: str
    event_type: str


@dataclass(frozen=True)
class AnomalyThreshold:
    """Configuration describing when to trigger an anomaly alert."""

    priority: str
    limit: int
    window: timedelta
    name: str = "threshold"


class _SnapshotSigner:
    """Utility to sign and verify monitoring snapshots."""

    def __init__(self) -> None:
        self._signing_key: SigningKey | None = None
        self._verify_key: VerifyKey | None = None

    def reset(self) -> None:
        self._signing_key = None
        self._verify_key = None

    def sign(self, payload: Mapping[str, object]) -> str:
        signing_key = self._load_signing_key()
        signature = signing_key.sign(self._serialize(payload)).signature
        return base64.b64encode(signature).decode("ascii")

    def verify(self, payload: Mapping[str, object], signature: str) -> bool:
        if not isinstance(signature, str) or not signature:
            return False
        verify_key = self._load_verify_key()
        if verify_key is None:
            return False
        try:
            verify_key.verify(self._serialize(payload), base64.b64decode(signature))
            return True
        except BadSignatureError:
            return False

    @staticmethod
    def _serialize(payload: Mapping[str, object]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _load_signing_key(self) -> SigningKey:
        if self._signing_key is not None:
            return self._signing_key
        path = Path(os.getenv("PULSE_SIGNING_KEY", "/vow/keys/ed25519_private.key"))
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Monitoring snapshot signing key missing at {path}."
            ) from exc
        self._signing_key = SigningKey(data)
        self._verify_key = self._signing_key.verify_key
        return self._signing_key

    def _load_verify_key(self) -> VerifyKey | None:
        if self._verify_key is not None:
            return self._verify_key
        path = Path(os.getenv("PULSE_VERIFY_KEY", ""))
        if path and path.exists():
            self._verify_key = VerifyKey(path.read_bytes())
            return self._verify_key
        try:
            return self._load_signing_key().verify_key
        except RuntimeError:
            return None


_DEFAULT_WINDOWS: Dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
}

_DEFAULT_THRESHOLDS: Sequence[AnomalyThreshold] = (
    AnomalyThreshold(priority="critical", limit=5, window=timedelta(minutes=10), name="critical_spike"),
)

_VALID_FILTERS = {"priority", "source_daemon", "event_type"}

Snapshot = Dict[str, Any]
WindowMetrics = Dict[str, Any]
AnomalyRecord = Dict[str, Any]


@dataclass
class _PerDaemonDetail:
    total: int = 0
    priority: Counter[str] = field(default_factory=Counter)
    event_type: Counter[str] = field(default_factory=Counter)
    matrix: Dict[str, Counter[str]] = field(default_factory=dict)


class MonitoringDaemon:
    """Observability layer that aggregates pulse metrics and anomalies."""

    def __init__(
        self,
        *,
        windows: Mapping[str, timedelta] | None = None,
        anomaly_thresholds: Sequence[AnomalyThreshold] | None = None,
        snapshot_interval: timedelta | None = None,
        snapshot_cache_size: int = 128,
    ) -> None:
        self.events: List[dict[str, object]] = []
        self.messages: List[str] = []
        self.warning_events: List[dict[str, object]] = []
        self.critical_events: List[dict[str, object]] = []
        self.federated_restarts: List[dict[str, object]] = []
        self.anomalies: List[AnomalyRecord] = []

        self._signer = _SnapshotSigner()
        self._lock = threading.RLock()
        self._event_history: Deque[_EventRecord] = deque()
        self._pending_anomalies: List[AnomalyRecord] = []
        self._anomaly_state: Dict[tuple[str, str, float], datetime] = {}
        self._snapshots_cache: Deque[Snapshot] = deque(maxlen=snapshot_cache_size)

        self._windows = {
            label.strip().lower(): delta
            for label, delta in (windows or _DEFAULT_WINDOWS).items()
        }
        self._thresholds = list(anomaly_thresholds or _DEFAULT_THRESHOLDS)
        self._snapshot_interval = snapshot_interval or timedelta(hours=1)
        max_window_seconds = max((delta.total_seconds() for delta in self._windows.values()), default=0.0)
        max_threshold_seconds = max((threshold.window.total_seconds() for threshold in self._thresholds), default=0.0)
        self._history_retention = timedelta(
            seconds=max(
                max_window_seconds,
                max_threshold_seconds,
                self._snapshot_interval.total_seconds(),
            )
        )

        glow_root = Path(os.getenv("MONITORING_GLOW_ROOT", "/glow/monitoring"))
        self._metrics_path = Path(os.getenv("MONITORING_METRICS_PATH", str(glow_root / "metrics.jsonl")))
        self._alerts_path = Path(os.getenv("MONITORING_ALERTS_PATH", str(glow_root / "alerts.jsonl")))
        self._ledger_path = get_log_path("monitoring_alerts.jsonl")

        self._last_snapshot_at: datetime | None = None
        self._stop_event = threading.Event()
        self._subscription: pulse_bus.PulseSubscription | None = pulse_bus.subscribe(
            self._handle_event
        )
        self._load_existing_snapshots()

        self._snapshot_thread: threading.Thread | None = None
        if self._snapshot_interval.total_seconds() > 0:
            self._snapshot_thread = threading.Thread(
                target=self._snapshot_loop,
                name="MonitoringSnapshotLoop",
                daemon=True,
            )
            self._snapshot_thread.start()

    # ------------------------------------------------------------------
    # Pulse handling
    # ------------------------------------------------------------------
    def _handle_event(self, event: dict[str, object]) -> None:
        priority = str(event.get("priority", "info")).lower()
        if priority not in {"info", "warning", "critical"}:
            priority = "info"
        timestamp = self._parse_timestamp(str(event.get("timestamp", "")))
        source = str(event.get("source_daemon", "unknown"))
        event_type = str(event.get("event_type", "unknown"))

        if self._should_ignore_event(source, event_type):
            return

        message = json.dumps(event, sort_keys=True)

        with self._lock:
            self.events.append(event)
            self.messages.append(message)
            if priority == "warning":
                self.warning_events.append(event)
            elif priority == "critical":
                self.critical_events.append(event)

            if self._is_federated_restart(event):
                summary = self._build_federated_summary(event)
                if summary is not None:
                    self.federated_restarts.append(summary)
                    print(
                        "[MonitoringDaemon] federated_restart "
                        f"daemon={summary['daemon_name']} "
                        f"requested_by={summary['requested_by']} "
                        f"executor={summary['executor_peer']} "
                        f"outcome={summary['outcome']}"
                    )

            self._event_history.append(
                _EventRecord(
                    timestamp=timestamp,
                    priority=priority,
                    source_daemon=source,
                    event_type=event_type,
                )
            )
            self._prune_history(timestamp)
            triggered = self._evaluate_anomalies(timestamp)

        for anomaly in triggered:
            self._publish_alert(anomaly)

        print(f"[MonitoringDaemon] {message}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Unsubscribe from the pulse bus and stop background work."""

        if self._subscription and self._subscription.active:
            self._subscription.unsubscribe()
            self._subscription = None
        self._stop_event.set()
        if self._snapshot_thread and self._snapshot_thread.is_alive():
            self._snapshot_thread.join(timeout=1)
        self._signer.reset()

    def current_metrics(self) -> Dict[str, Any]:
        """Return the latest aggregated metrics without persisting."""

        with self._lock:
            now = datetime.now(timezone.utc)
            self._prune_history(now)
            events = list(self._event_history)
            overall = self._summarize_events(events)
            windows = {
                label: self._compute_window_metrics(delta, now)
                for label, delta in self._windows.items()
            }
            anomalies = list(self.anomalies)
        return {
            "timestamp": now.isoformat(),
            "overall": overall,
            "windows": windows,
            "anomalies": anomalies,
        }

    def persist_snapshot(self) -> dict[str, object]:
        """Persist a signed metrics snapshot and broadcast a summary pulse."""

        with self._lock:
            now = datetime.now(timezone.utc)
            self._prune_history(now)
            overall = self._summarize_events(list(self._event_history))
            windows = {
                label: self._compute_window_metrics(delta, now)
                for label, delta in self._windows.items()
            }
            anomalies = list(self._pending_anomalies)
            self._pending_anomalies.clear()

        payload: Snapshot = {
            "timestamp": now.isoformat(),
            "overall": overall,
            "windows": windows,
            "anomalies": anomalies,
        }
        signature = self._signer.sign(payload)
        snapshot: Snapshot = dict(payload)
        snapshot["signature"] = signature
        self._write_snapshot(snapshot)
        with self._lock:
            self._snapshots_cache.append(snapshot)
            self._last_snapshot_at = now
        self._publish_summary(payload)
        return snapshot

    def verify_snapshot(self, snapshot: Mapping[str, Any]) -> bool:
        signature = snapshot.get("signature")
        if not isinstance(signature, str):
            return False
        payload = {key: value for key, value in snapshot.items() if key != "signature"}
        return self._signer.verify(payload, signature)

    def query(self, window: str, filters: Mapping[str, str] | None = None) -> Dict[str, Any]:
        """Return filtered metrics derived from verified snapshots."""

        label, duration = self._resolve_window(window)
        normalized_filters = self._normalize_filters(filters)
        snapshots = self._get_verified_snapshots(label)
        if not snapshots:
            raise ValueError(f"No verified monitoring snapshots available for {label}")
        latest = snapshots[-1]
        windows = cast(Mapping[str, Any], latest.get("windows", {}))
        metrics = cast(WindowMetrics, windows[label])
        summary = self._apply_filters(metrics, normalized_filters, duration)
        anomalies = self._filter_anomalies(
            cast(Iterable[Mapping[str, Any]], latest.get("anomalies", [])),
            normalized_filters,
        )
        return {
            "window": label,
            "filters": normalized_filters,
            "summary": summary,
            "anomalies": anomalies,
            "verified_snapshots": [latest["timestamp"]],
        }

    # ------------------------------------------------------------------
    # Snapshot persistence & background loop
    # ------------------------------------------------------------------
    def _snapshot_loop(self) -> None:
        interval = max(self._snapshot_interval.total_seconds(), 0.0)
        while not self._stop_event.wait(interval):
            try:
                self.persist_snapshot()
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to persist monitoring snapshot")

    def _write_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self._metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with self._metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, sort_keys=True) + "\n")

    def _publish_summary(self, payload: Mapping[str, Any]) -> None:
        pulse_bus.publish(
            {
                "timestamp": payload["timestamp"],
                "source_daemon": "MonitoringDaemon",
                "event_type": "monitor_summary",
                "priority": "info",
                "payload": {
                    "overall": payload["overall"],
                    "windows": payload["windows"],
                    "anomalies": payload["anomalies"],
                },
            }
        )

    def _load_existing_snapshots(self) -> None:
        for snapshot in self._read_snapshots_from_disk():
            self._snapshots_cache.append(snapshot)

    def _read_snapshots_from_disk(self) -> List[Snapshot]:
        snapshots: List[Snapshot] = []
        if not self._metrics_path.exists():
            return snapshots
        try:
            with self._metrics_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    entry = line.strip()
                    if not entry:
                        continue
                    try:
                        snapshot = json.loads(entry)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed monitoring snapshot entry")
                        continue
                    if not isinstance(snapshot, dict):
                        continue
                    if self.verify_snapshot(snapshot):
                        snapshots.append(snapshot)
        except FileNotFoundError:  # pragma: no cover - file removed concurrently
            return snapshots
        return snapshots

    def _get_verified_snapshots(self, label: str) -> List[Snapshot]:
        combined: Dict[str, Snapshot] = {}
        for snapshot in list(self._snapshots_cache) + self._read_snapshots_from_disk():
            windows = cast(Mapping[str, Any], snapshot.get("windows", {}))
            if label not in windows:
                continue
            timestamp = str(snapshot.get("timestamp", ""))
            if not timestamp:
                continue
            if not self.verify_snapshot(snapshot):
                continue
            combined[timestamp] = snapshot
        return [combined[key] for key in sorted(combined)]

    # ------------------------------------------------------------------
    # Metric computation helpers
    # ------------------------------------------------------------------
    def _summarize_events(
        self, events: Iterable[_EventRecord], duration: timedelta | None = None
    ) -> WindowMetrics:
        event_list = list(events)
        priority_counts: Counter[str] = Counter()
        source_counts: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()
        per_daemon: Dict[str, _PerDaemonDetail] = {}

        for record in event_list:
            priority_counts[record.priority] += 1
            source_counts[record.source_daemon] += 1
            type_counts[record.event_type] += 1

            detail = per_daemon.setdefault(record.source_daemon, _PerDaemonDetail())
            detail.total += 1
            detail.priority[record.priority] += 1
            detail.event_type[record.event_type] += 1
            detail.matrix.setdefault(record.priority, Counter())[record.event_type] += 1

        def _counter_dict(counter: Counter[str]) -> Dict[str, int]:
            return {key: counter[key] for key in sorted(counter)}

        per_daemon_clean: Dict[str, dict[str, object]] = {}
        for daemon, data in sorted(per_daemon.items()):
            matrix_dict = {
                priority: {etype: count for etype, count in sorted(counter.items())}
                for priority, counter in sorted(data.matrix.items())
            }
            per_daemon_clean[daemon] = {
                "total": data.total,
                "priority": _counter_dict(data.priority),
                "event_type": _counter_dict(data.event_type),
                "matrix": matrix_dict,
            }

        result: WindowMetrics = {
            "total_events": len(event_list),
            "priority": _counter_dict(priority_counts),
            "source_daemon": _counter_dict(source_counts),
            "event_type": _counter_dict(type_counts),
            "per_daemon": per_daemon_clean,
        }
        if duration is not None and duration.total_seconds() > 0:
            minutes = duration.total_seconds() / 60
            hours = duration.total_seconds() / 3600
            result["rate_per_minute"] = len(event_list) / minutes
            result["rate_per_hour"] = len(event_list) / hours
        return result

    def _compute_window_metrics(self, duration: timedelta, now: datetime) -> WindowMetrics:
        cutoff = now - duration
        events = [record for record in self._event_history if record.timestamp >= cutoff]
        metrics = self._summarize_events(events, duration)
        metrics["window_seconds"] = int(duration.total_seconds())
        return metrics

    def _apply_filters(
        self,
        metrics: Mapping[str, Any],
        filters: Mapping[str, str],
        duration: timedelta,
    ) -> Dict[str, Any]:
        if not filters:
            summary = dict(metrics)
            total_events = cast(int, metrics.get("total_events", 0))
            summary.setdefault(
                "rate_per_minute",
                total_events / max(duration.total_seconds() / 60, 1e-9),
            )
            summary.setdefault(
                "rate_per_hour",
                total_events / max(duration.total_seconds() / 3600, 1e-9),
            )
            return summary

        per_daemon = cast(Mapping[str, Any], metrics.get("per_daemon", {}))
        priority_counts: Counter[str] = Counter()
        source_counts: Counter[str] = Counter()
        event_type_counts: Counter[str] = Counter()
        total = 0

        for daemon, data_obj in per_daemon.items():
            if "source_daemon" in filters and daemon != filters["source_daemon"]:
                continue
            data = cast(Mapping[str, Any], data_obj)
            matrix = cast(Mapping[str, Mapping[str, int]], data.get("matrix", {}))
            for priority, event_counts in matrix.items():
                if "priority" in filters and priority != filters["priority"]:
                    continue
                for event_type, count in event_counts.items():
                    if "event_type" in filters and event_type != filters["event_type"]:
                        continue
                    if count <= 0:
                        continue
                    total += int(count)
                    priority_counts[priority] += int(count)
                    source_counts[daemon] += int(count)
                    event_type_counts[event_type] += int(count)

        minutes = duration.total_seconds() / 60
        hours = duration.total_seconds() / 3600
        return {
            "total_events": total,
            "priority": {key: priority_counts[key] for key in sorted(priority_counts)},
            "source_daemon": {key: source_counts[key] for key in sorted(source_counts)},
            "event_type": {key: event_type_counts[key] for key in sorted(event_type_counts)},
            "rate_per_minute": total / minutes if minutes else 0.0,
            "rate_per_hour": total / hours if hours else 0.0,
        }

    def _filter_anomalies(
        self, anomalies: Iterable[Mapping[str, Any]], filters: Mapping[str, str]
    ) -> List[AnomalyRecord]:
        result: List[AnomalyRecord] = []
        for anomaly in anomalies:
            if "source_daemon" in filters and anomaly.get("source_daemon") != filters["source_daemon"]:
                continue
            if "priority" in filters and anomaly.get("priority") != filters["priority"]:
                continue
            if "event_type" in filters and anomaly.get("event_type") != filters["event_type"]:
                continue
            result.append(dict(anomaly))
        return result

    # ------------------------------------------------------------------
    # Anomaly detection & alerting
    # ------------------------------------------------------------------
    def _evaluate_anomalies(self, now: datetime) -> List[AnomalyRecord]:
        triggered: List[AnomalyRecord] = []
        if not self._event_history:
            return triggered
        latest = self._event_history[-1]
        for threshold in self._thresholds:
            if latest.priority != threshold.priority:
                continue
            window_start = now - threshold.window
            count = sum(
                1
                for record in self._event_history
                if record.source_daemon == latest.source_daemon
                and record.priority == threshold.priority
                and record.timestamp >= window_start
            )
            if count <= threshold.limit:
                continue
            key = (
                latest.source_daemon,
                threshold.priority,
                float(threshold.window.total_seconds()),
            )
            last_trigger = self._anomaly_state.get(key)
            if last_trigger is not None and (now - last_trigger) < threshold.window:
                continue
            anomaly: AnomalyRecord = {
                "timestamp": now.isoformat(),
                "source_daemon": latest.source_daemon,
                "priority": threshold.priority,
                "window_seconds": int(threshold.window.total_seconds()),
                "threshold": threshold.limit,
                "observed": count,
                "event_type": latest.event_type,
                "name": threshold.name,
            }
            self._anomaly_state[key] = now
            self.anomalies.append(anomaly)
            self._pending_anomalies.append(anomaly)
            triggered.append(anomaly)
        return triggered

    def _publish_alert(self, anomaly: Mapping[str, Any]) -> None:
        alert_entry: Dict[str, Any] = {
            "timestamp": anomaly["timestamp"],
            "source_daemon": anomaly["source_daemon"],
            "priority": anomaly["priority"],
            "window_seconds": anomaly["window_seconds"],
            "threshold": anomaly["threshold"],
            "observed": anomaly["observed"],
            "event_type": anomaly.get("event_type", ""),
            "name": anomaly.get("name", "threshold"),
        }
        append_json(self._ledger_path, dict(alert_entry))
        self._alerts_path.parent.mkdir(parents=True, exist_ok=True)
        with self._alerts_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(alert_entry, sort_keys=True) + "\n")
        pulse_bus.publish(
            {
                "timestamp": anomaly["timestamp"],
                "source_daemon": "MonitoringDaemon",
                "event_type": "monitor_alert",
                "priority": "critical",
                "payload": alert_entry,
            }
        )

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_timestamp(raw: str) -> datetime:
        if not raw:
            return datetime.now(timezone.utc)
        text = raw
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _should_ignore_event(source: str, event_type: str) -> bool:
        return source == "MonitoringDaemon" and event_type in {"monitor_summary", "monitor_alert"}

    def _prune_history(self, now: datetime) -> None:
        cutoff = now - self._history_retention
        self._event_history = deque(
            record for record in self._event_history if record.timestamp >= cutoff
        )

    def _resolve_window(self, window: str) -> tuple[str, timedelta]:
        if not window:
            raise ValueError("Window value must be provided")
        text = window.strip().lower()
        if text.startswith("last "):
            text = text[5:]
        if text in self._windows:
            return text, self._windows[text]
        match = re.fullmatch(
            r"(\d+)\s*(s|sec|secs|seconds|m|min|mins|minutes|h|hour|hours|d|day|days)",
            text,
        )
        if not match:
            raise ValueError(f"Unknown monitoring window: {window}")
        value = int(match.group(1))
        unit = match.group(2)
        seconds = self._unit_to_seconds(value, unit)
        for label, delta in self._windows.items():
            if int(delta.total_seconds()) == seconds:
                return label, delta
        raise ValueError(f"Window {window} is not configured for monitoring snapshots")

    @staticmethod
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

    def _normalize_filters(self, filters: Mapping[str, str] | None) -> Dict[str, str]:
        if not filters:
            return {}
        normalized: Dict[str, str] = {}
        for key, value in filters.items():
            if value is None:
                continue
            if key not in _VALID_FILTERS:
                raise ValueError(f"Unsupported monitoring filter: {key}")
            if key == "priority":
                normalized[key] = str(value).lower()
            else:
                normalized[key] = str(value)
        return normalized

    def _is_federated_restart(self, event: Mapping[str, object]) -> bool:
        if str(event.get("event_type", "")).lower() != "daemon_restart":
            return False
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return False
        scope = str(payload.get("scope", "")).lower()
        return scope == "federated"

    def _build_federated_summary(
        self, event: Mapping[str, object]
    ) -> dict[str, object] | None:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return None
        daemon_name = payload.get("daemon_name") or payload.get("daemon")
        if daemon_name is None:
            return None
        executor = str(event.get("source_peer", "local"))
        requested_by = str(payload.get("requested_by", "unknown"))
        outcome = str(payload.get("outcome", "unknown"))
        return {
            "daemon_name": str(daemon_name),
            "requested_by": requested_by,
            "executor_peer": executor,
            "outcome": outcome,
        }


__all__ = ["AnomalyThreshold", "MonitoringDaemon"]
