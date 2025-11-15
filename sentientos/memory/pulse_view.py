"""Deterministic view over recent runtime pulses for Dream Loop reflection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional

from sentientos.experiments.runner import CHAIN_LOG_PATH as _EXPERIMENT_CHAIN_PATH

PulseKind = Literal[
    "experiment",
    "cathedral",
    "rollback",
    "federation",
    "world",
    "persona",
]

Severity = Literal["info", "warn", "error"]


@dataclass(frozen=True)
class PulseEvent:
    ts: datetime
    kind: PulseKind
    severity: Severity
    source: str
    payload: Dict[str, Any]


def collect_recent_pulse(runtime, since_ts: datetime) -> List[PulseEvent]:
    """Deterministically fetch recent events from logs and buffers."""

    cutoff = _normalize_timestamp(since_ts)
    pulses: List[PulseEvent] = []
    pulses.extend(_collect_experiment_pulses(cutoff))
    pulses.extend(_collect_cathedral_reviews(runtime, cutoff))
    pulses.extend(_collect_rollback_events(runtime, cutoff))
    pulses.extend(_collect_world_events(runtime, cutoff))
    pulses.extend(_collect_federation_reports(runtime, cutoff))
    pulses.extend(_collect_persona_reflection(runtime, cutoff))
    pulses = [event for event in pulses if event.ts > cutoff]
    return sorted(pulses, key=lambda event: event.ts)


def _collect_experiment_pulses(cutoff: datetime) -> List[PulseEvent]:
    path = _EXPERIMENT_CHAIN_PATH
    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists():
        return []
    events: List[PulseEvent] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ts = _parse_timestamp(entry.get("timestamp") or entry.get("ts"))
            if ts is None or ts <= cutoff:
                continue
            success = entry.get("success")
            severity: Severity
            if success is False or entry.get("error"):
                severity = "error"
            elif success is True:
                severity = "info"
            else:
                severity = "warn"
            payload = {
                "chain_id": entry.get("chain_id"),
                "experiment_id": entry.get("experiment_id"),
                "success": success,
                "error": entry.get("error"),
            }
            events.append(
                PulseEvent(
                    ts=ts,
                    kind="experiment",
                    severity=severity,
                    source="experiments.chain",
                    payload=payload,
                )
            )
    except OSError:
        return []
    return events


def _collect_cathedral_reviews(runtime, cutoff: datetime) -> List[PulseEvent]:
    path = _get_path(runtime, "cathedral_log_path", "_cathedral_log_path")
    if path is None or not path.exists():
        return []
    events: List[PulseEvent] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ts = _parse_timestamp(entry.get("timestamp") or entry.get("ts"))
            if ts is None or ts <= cutoff:
                continue
            status = str(entry.get("status") or "").lower()
            severity: Severity = "info"
            if status == "quarantined":
                severity = "warn"
            payload = {
                "amendment_id": entry.get("amendment_id"),
                "status": status,
                "validation_errors": entry.get("validation_errors", []),
                "invariant_errors": entry.get("invariant_errors", []),
            }
            events.append(
                PulseEvent(
                    ts=ts,
                    kind="cathedral",
                    severity=severity,
                    source="cathedral.review",
                    payload=payload,
                )
            )
    except OSError:
        return []
    return events


def _collect_rollback_events(runtime, cutoff: datetime) -> List[PulseEvent]:
    ledger_path = getattr(runtime, "ledger_path", None)
    if ledger_path is None:
        ledger_path = _get_path(runtime, "ledger_path", "_ledger_path")
    if isinstance(ledger_path, Path):
        path = ledger_path
    elif ledger_path is None:
        return []
    else:
        path = Path(ledger_path)
    if not path.exists():
        return []
    events: List[PulseEvent] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ts = _parse_timestamp(entry.get("ts") or entry.get("timestamp"))
            if ts is None or ts <= cutoff:
                continue
            event_name = str(entry.get("event") or "").lower()
            if event_name not in {"rollback", "rollback_error"}:
                continue
            severity: Severity = "info" if event_name == "rollback" else "error"
            payload = {
                "amendment_id": entry.get("amendment_id"),
                "auto_revert": entry.get("auto") or entry.get("auto_revert"),
                "reverted": entry.get("reverted"),
                "skipped": entry.get("skipped"),
                "error": entry.get("error"),
            }
            events.append(
                PulseEvent(
                    ts=ts,
                    kind="rollback",
                    severity=severity,
                    source="cathedral.rollback",
                    payload=payload,
                )
            )
    except OSError:
        return []
    return events


def _collect_world_events(runtime, cutoff: datetime) -> List[PulseEvent]:
    bus = getattr(runtime, "world_bus", None)
    if bus is None:
        return []
    try:
        world_events = bus.drain_since(cutoff)
    except Exception:
        return []
    pulses: List[PulseEvent] = []
    for event in world_events:
        ts = getattr(event, "ts", None)
        if not isinstance(ts, datetime) or ts <= cutoff:
            continue
        level = str(event.data.get("level") if isinstance(event.data, Mapping) else "").lower()
        severity: Severity = "warn" if level in {"high", "busy"} else "info"
        pulses.append(
            PulseEvent(
                ts=ts,
                kind="world",
                severity=severity,
                source=f"world.{event.kind}",
                payload={"summary": event.summary, "data": dict(event.data)},
            )
        )
    return pulses


def _collect_federation_reports(runtime, cutoff: datetime) -> List[PulseEvent]:
    get_state = getattr(runtime, "get_federation_state", None)
    if not callable(get_state):
        return []
    try:
        state = get_state()
    except Exception:
        return []
    if state is None:
        return []
    ts = getattr(state, "last_poll_ts", None)
    if not isinstance(ts, datetime) or ts <= cutoff:
        return []
    reports = getattr(state, "peer_reports", {}) or {}
    pulses: List[PulseEvent] = []
    for peer, report in reports.items():
        level = getattr(report, "level", "ok")
        reasons = list(getattr(report, "reasons", []))
        severity: Severity
        if level == "incompatible":
            severity = "error"
        elif level in {"drift", "warn"}:
            severity = "warn"
        else:
            severity = "info"
        pulses.append(
            PulseEvent(
                ts=ts,
                kind="federation",
                severity=severity,
                source=f"federation.{peer}",
                payload={"peer": peer, "level": level, "reasons": reasons},
            )
        )
    return pulses


def _collect_persona_reflection(runtime, cutoff: datetime) -> List[PulseEvent]:
    loop = getattr(runtime, "_persona_loop", None)
    if loop is None:
        return []
    state = getattr(loop, "state", None)
    if state is None:
        return []
    ts = getattr(state, "last_update_ts", None)
    if not isinstance(ts, datetime) or ts <= cutoff:
        return []
    reflection = getattr(state, "recent_reflection", None)
    if not reflection:
        return []
    return [
        PulseEvent(
            ts=ts,
            kind="persona",
            severity="info",
            source="persona.loop",
            payload={"reflection": reflection},
        )
    ]


def _get_path(runtime, attr: str, fallback: str) -> Optional[Path]:
    candidate = getattr(runtime, attr, None)
    if candidate is None:
        candidate = getattr(runtime, fallback, None)
    if candidate is None:
        return None
    if isinstance(candidate, Path):
        return candidate
    try:
        return Path(candidate)
    except Exception:
        return None


def _normalize_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_timestamp(raw: Any) -> Optional[datetime]:
    if raw in {None, ""}:
        return None
    if isinstance(raw, datetime):
        return _normalize_timestamp(raw)
    text = str(raw)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _normalize_timestamp(parsed)
