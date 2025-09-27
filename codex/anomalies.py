"""Anomaly detection and proposal helpers for Codex."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional

import json

from .rewrites import RewritePatch, ScopedRewriteEngine

Severity = str


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Anomaly:
    """Representation of a detected daemon anomaly."""

    kind: str
    description: str
    severity: Severity
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_default_now)

    def to_event(self) -> Dict[str, Any]:
        payload = dict(self.metadata)
        payload.update(
            {
                "kind": self.kind,
                "description": self.description,
                "severity": self.severity,
                "timestamp": self.timestamp.isoformat(),
            }
        )
        return payload


class AnomalyEmitter:
    """Persist anomaly events and optionally forward them to the pulse bus."""

    def __init__(
        self,
        root: Path | str = Path("/pulse/anomalies"),
        *,
        bus: Any | None = None,
    ) -> None:
        self._root = Path(root)
        self._bus = bus

    def emit(self, anomaly: Anomaly, *, patch_id: str | None = None) -> Path:
        event = anomaly.to_event()
        if patch_id:
            event["patch_id"] = patch_id

        self._root.mkdir(parents=True, exist_ok=True)
        day_path = self._root / f"{anomaly.timestamp.date().isoformat()}.jsonl"
        with day_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

        if self._bus is not None:
            priority = "critical" if anomaly.severity == "critical" else "warning"
            payload = dict(event)
            payload.setdefault("severity", anomaly.severity)
            self._bus.publish(
                {
                    "timestamp": anomaly.timestamp.isoformat(),
                    "source_daemon": "CodexDaemon",
                    "event_type": "anomaly_detected",
                    "priority": priority,
                    "payload": payload,
                }
            )

        return day_path


class AnomalyDetector:
    """Detect key anomaly classes from daemon telemetry samples."""

    def __init__(
        self,
        *,
        crash_threshold: int = 3,
        latency_threshold_ms: float = 1_000.0,
        backlog_threshold: int = 10,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._crash_threshold = max(1, crash_threshold)
        self._latency_threshold_ms = float(latency_threshold_ms)
        self._backlog_threshold = max(1, backlog_threshold)
        self._now = now

    def analyze(
        self,
        logs: Iterable[Mapping[str, Any]],
        pulses: Iterable[Mapping[str, Any]],
        backlog: Iterable[Mapping[str, Any]],
        *,
        embodiment_events: Iterable[Mapping[str, Any]] = (),
    ) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        observed = self._now()

        crash_counts: MutableMapping[str, int] = {}
        for entry in logs:
            if not isinstance(entry, Mapping):
                continue
            if not (entry.get("crash_loop") or entry.get("event") == "crash"):
                continue
            daemon = str(entry.get("daemon") or entry.get("name") or "unknown")
            crash_counts[daemon] = crash_counts.get(daemon, 0) + 1
        for daemon, count in crash_counts.items():
            if count >= self._crash_threshold:
                anomalies.append(
                    Anomaly(
                        "crash_loop",
                        f"Daemon {daemon} crash loop detected {count}×",
                        "critical",
                        {"daemon": daemon, "count": count},
                        timestamp=observed,
                    )
                )

        for sample in pulses:
            if not isinstance(sample, Mapping):
                continue
            latency = sample.get("latency_ms") or sample.get("latency")
            if latency is None:
                continue
            try:
                latency_value = float(latency)
            except (TypeError, ValueError):
                continue
            threshold = sample.get("latency_threshold_ms") or sample.get("expected_latency_ms")
            threshold_value = float(threshold) if threshold is not None else self._latency_threshold_ms
            if latency_value > threshold_value:
                daemon = str(sample.get("daemon") or sample.get("source") or "unknown")
                anomalies.append(
                    Anomaly(
                        "latency_spike",
                        f"Daemon {daemon} latency spike: {latency_value:.0f}ms > {threshold_value:.0f}ms",
                        "warning",
                        {
                            "daemon": daemon,
                            "latency_ms": latency_value,
                            "threshold_ms": threshold_value,
                        },
                        timestamp=observed,
                    )
                )

        backlog_entries = list(backlog)
        for entry in backlog_entries:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("ledger_mismatch") or entry.get("ledger_status") == "diverged":
                daemon = str(entry.get("daemon") or entry.get("owner") or "unknown")
                anomalies.append(
                    Anomaly(
                        "ledger_mismatch",
                        f"Daemon {daemon} ledger mismatch detected",
                        "warning",
                        {"daemon": daemon, "task_id": entry.get("task_id")},
                        timestamp=observed,
                    )
                )
                break

        orphaned_tasks = [entry for entry in backlog_entries if _is_orphan(entry)]
        if orphaned_tasks:
            daemon = str(orphaned_tasks[0].get("daemon") or orphaned_tasks[0].get("owner") or "unknown")
            metadata = {
                "daemon": daemon,
                "orphaned_tasks": [entry.get("task_id") for entry in orphaned_tasks],
                "count": len(orphaned_tasks),
            }
            anomalies.append(
                Anomaly(
                    "orphaned_tasks",
                    f"{len(orphaned_tasks)} orphaned tasks detected for {daemon}",
                    "warning",
                    metadata,
                    timestamp=observed,
                )
            )

        if len(backlog_entries) >= self._backlog_threshold:
            daemon = str(backlog_entries[0].get("daemon") or backlog_entries[0].get("owner") or "unknown")
            anomalies.append(
                Anomaly(
                    "backlog_drift",
                    f"{daemon} backlog drifted to {len(backlog_entries)} entries",
                    "warning",
                    {"daemon": daemon, "backlog_size": len(backlog_entries)},
                    timestamp=observed,
                )
            )

        embodiment_payloads = [_normalize_embodiment_event(event) for event in embodiment_events]
        embodiment_payloads = [payload for payload in embodiment_payloads if payload is not None]
        anomalies.extend(_detect_embodiment_anomalies(embodiment_payloads, observed))

        return anomalies


def _is_orphan(entry: Mapping[str, Any]) -> bool:
    status = entry.get("status") or entry.get("state")
    return bool(entry.get("orphaned")) or status == "orphaned"


def _normalize_embodiment_event(entry: Mapping[str, Any] | Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, Mapping):
        return None
    channel = entry.get("channel") or entry.get("source") or entry.get("stream")
    if not channel:
        return None
    event_type = entry.get("event_type") or entry.get("type") or entry.get("event") or "event"
    payload = entry.get("payload")
    if not isinstance(payload, Mapping):
        payload = {
            key: value
            for key, value in entry.items()
            if key not in {"channel", "source", "stream", "event_type", "type", "event", "timestamp"}
        }
    timestamp = _coerce_timestamp(entry.get("timestamp"))
    return {
        "channel": str(channel),
        "event_type": str(event_type),
        "payload": dict(payload),
        "timestamp": timestamp,
    }


def _detect_embodiment_anomalies(
    events: Iterable[Mapping[str, Any]],
    observed: datetime,
) -> List[Anomaly]:
    anomalies: List[Anomaly] = []
    noise_counts: MutableMapping[str, int] = {}
    offline_channels: set[str] = set()

    for event in events:
        channel = str(event.get("channel") or "unknown")
        event_type = str(event.get("event_type") or "event")
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        timestamp = event.get("timestamp") if isinstance(event.get("timestamp"), datetime) else observed

        if _is_motion_anomaly(event_type, payload):
            period = str(payload.get("period") or "").lower()
            severity = "critical" if period in {"night", "quiet_hours"} else "warning"
            metadata = _embodiment_metadata(channel, payload)
            if period:
                metadata["period"] = period
            magnitude = _coerce_float(payload.get("magnitude"))
            if magnitude is not None:
                metadata["magnitude"] = magnitude
            anomalies.append(
                Anomaly(
                    "embodiment_motion",
                    f"Unexpected motion detected on {channel}",
                    severity,
                    metadata,
                    timestamp=timestamp,
                )
            )
            continue

        if _is_noise_event(event_type, payload):
            decibel = _coerce_float(payload.get("decibel"))
            threshold = _coerce_float(payload.get("threshold") or payload.get("baseline")) or 70.0
            noise_counts[channel] = noise_counts.get(channel, 0) + 1
            severity = "critical" if noise_counts[channel] >= 3 or payload.get("profanity") else "warning"
            metadata = _embodiment_metadata(channel, payload)
            metadata.update({"decibel": decibel, "threshold": threshold})
            anomalies.append(
                Anomaly(
                    "embodiment_noise",
                    f"Noise anomaly from {channel}: {decibel or 'unknown'} dB",
                    severity,
                    metadata,
                    timestamp=timestamp,
                )
            )
            continue

        if _is_absence_event(event_type, payload) and channel not in offline_channels:
            offline_channels.add(channel)
            metadata = _embodiment_metadata(channel, payload)
            status = str(payload.get("status") or event_type)
            metadata["status"] = status
            anomalies.append(
                Anomaly(
                    "embodiment_absence",
                    f"Embodiment feed offline: {channel}",
                    "critical",
                    metadata,
                    timestamp=timestamp,
                )
            )

    return anomalies


def _coerce_timestamp(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw
    if isinstance(raw, str):
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    return None


def _coerce_float(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _is_motion_anomaly(event_type: str, payload: Mapping[str, Any]) -> bool:
    if event_type.lower() != "motion":
        return False
    if payload.get("unexpected") or payload.get("allowed") is False:
        return True
    period = str(payload.get("period") or "").lower()
    magnitude = _coerce_float(payload.get("magnitude")) or 0.0
    if period in {"night", "quiet_hours"} and magnitude > 0.0:
        return True
    return False


def _is_noise_event(event_type: str, payload: Mapping[str, Any]) -> bool:
    if event_type.lower() not in {"noise", "audio"}:
        return False
    if payload.get("profanity") or payload.get("keyword_flag"):
        return True
    decibel = _coerce_float(payload.get("decibel"))
    threshold = _coerce_float(payload.get("threshold") or payload.get("baseline")) or 70.0
    return decibel is not None and decibel >= threshold


def _is_absence_event(event_type: str, payload: Mapping[str, Any]) -> bool:
    status = str(payload.get("status") or event_type).lower()
    if status in {"offline", "missing", "absent"}:
        return True
    if payload.get("expected") and not payload.get("present", True):
        return True
    return False


def _embodiment_metadata(channel: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    confidence = _coerce_float(payload.get("confidence")) or 0.5
    metadata: Dict[str, Any] = {
        "channel": channel,
        "source": channel,
        "impact": "environment",
        "confidence": confidence,
        "tags": ["embodiment", channel],
    }
    metadata.update({key: value for key, value in payload.items() if key != "confidence"})
    return metadata


ProposalBuilder = Callable[[Path, Anomaly], str]


@dataclass
class ProposalPlan:
    """Defines how to respond to a detected anomaly with a rewrite proposal."""

    daemon: str
    target_path: Path
    builder: ProposalBuilder
    reason: str
    confidence: float
    urgency: str = "medium"
    metadata: Optional[Mapping[str, Any]] = None


class RewriteProposalEngine:
    """Bridge anomaly detections into Codex rewrite proposals."""

    def __init__(self, engine: ScopedRewriteEngine, *, emitter: AnomalyEmitter | None = None) -> None:
        self._engine = engine
        self._emitter = emitter

    def propose(
        self,
        plan: ProposalPlan,
        anomaly: Anomaly,
    ) -> RewritePatch:
        new_content = plan.builder(plan.target_path, anomaly)
        metadata = {
            "anomaly": anomaly.to_event(),
            "reason": plan.reason,
            "confidence": float(plan.confidence),
        }
        if plan.metadata:
            metadata.update(plan.metadata)

        patch = self._engine.request_rewrite(
            plan.daemon,
            plan.target_path,
            new_content,
            reason=plan.reason,
            confidence=plan.confidence,
            urgency=plan.urgency,
            metadata=metadata,
        )

        if self._emitter is not None:
            self._emitter.emit(anomaly, patch_id=patch.patch_id)

        return patch


class AnomalyCoordinator:
    """Coordinate anomaly detection and proposal generation."""

    def __init__(self, detector: AnomalyDetector, proposal_engine: RewriteProposalEngine) -> None:
        self._detector = detector
        self._proposal_engine = proposal_engine

    def evaluate(
        self,
        logs: Iterable[Mapping[str, Any]],
        pulses: Iterable[Mapping[str, Any]],
        backlog: Iterable[Mapping[str, Any]],
        plans: Mapping[str, ProposalPlan],
    ) -> List[RewritePatch]:
        patches: List[RewritePatch] = []
        for anomaly in self._detector.analyze(logs, pulses, backlog):
            plan = plans.get(anomaly.kind)
            if plan is None:
                continue
            patch = self._proposal_engine.propose(plan, anomaly)
            patches.append(patch)
        return patches

