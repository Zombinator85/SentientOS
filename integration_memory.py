"""Integration memory subsystem for Codex persistent state."""
from __future__ import annotations

import json
import os
import threading
import uuid
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Mapping, MutableMapping

__all__ = [
    "IntegrationEntry",
    "IntegrationMemory",
    "integration_memory",
    "configure_integration_root",
]


def _default_root() -> Path:
    """Resolve the root path for the integration mount."""

    root = os.getenv("INTEGRATION_ROOT", "/integration")
    return Path(root)


def _ensure_timestamp(value: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    if value:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = now
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    return now.isoformat()


def _parse_timestamp(value: str) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class IntegrationEntry:
    """One line in the integration ledger."""

    id: str
    timestamp: str
    source: str
    event_type: str
    impact: str
    confidence: float
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "event_type": self.event_type,
            "impact": self.impact,
            "confidence": self.confidence,
            "payload": dict(self.payload),
        }


class _StateIndex:
    """In-memory projection of integration state vectors."""

    def __init__(self, *, window: timedelta = timedelta(hours=1)) -> None:
        self.window = window
        self.by_source: dict[str, MutableMapping[str, Any]] = {}
        self.history: dict[tuple[str, str], Deque[datetime]] = defaultdict(deque)
        self.impacts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        self.lock = threading.Lock()

    def reset(self) -> None:
        with self.lock:
            self.by_source.clear()
            self.history.clear()
            self.impacts.clear()

    def update(self, entry: IntegrationEntry) -> None:
        key = (entry.source, entry.payload.get("anomaly_pattern") or entry.event_type)
        timestamp = _parse_timestamp(entry.timestamp)
        with self.lock:
            data = self.by_source.setdefault(
                entry.source,
                {
                    "total_events": 0,
                    "event_counts": Counter(),
                    "impact_counts": Counter(),
                    "last_event": entry.timestamp,
                },
            )
            data["total_events"] += 1
            data["event_counts"][entry.event_type] += 1
            data["impact_counts"][entry.impact] += 1
            data["last_event"] = entry.timestamp
            history = self.history[key]
            if entry.impact in {"degraded", "anomaly", "warning"}:
                history.append(timestamp)
            elif entry.impact in {"stabilized", "patched"}:
                history.clear()
            else:
                history.append(timestamp)
            self.impacts[key][entry.impact] += 1
            self._prune(history)

    def _prune(self, history: Deque[datetime]) -> None:
        threshold = datetime.now(timezone.utc) - self.window
        while history and history[0] < threshold:
            history.popleft()

    def snapshot(self, source: str | None = None) -> dict[str, Any]:
        with self.lock:
            if source is not None:
                return dict(self.by_source.get(source, {}))
            return {key: dict(value) for key, value in self.by_source.items()}

    def projection(self, source: str, pattern: str | None = None) -> dict[str, Any]:
        key = (source, pattern or "*")
        with self.lock:
            if pattern is None:
                histories = [
                    (k, deque(history))
                    for k, history in self.history.items()
                    if k[0] == source
                ]
                impacts = Counter()
                counts = 0
                timeline: list[str] = []
                for (src, pat), hist in histories:
                    counts += len(hist)
                    timeline.extend(dt.isoformat() for dt in hist)
                    impacts.update(self.impacts[(src, pat)])
                trend = "stable"
                if len(timeline) >= 2:
                    timeline_sorted = sorted(timeline)
                    trend = "increasing" if timeline_sorted[-1] > timeline_sorted[-2] else "stable"
                priority = self._priority(counts, impacts)
                return {
                    "source": source,
                    "event_type": "*",
                    "count": counts,
                    "priority": priority,
                    "trend": trend,
                    "window_minutes": int(self.window.total_seconds() // 60),
                    "confidence": min(1.0, 0.4 + 0.1 * counts),
                    "trajectory": sorted(timeline),
                    "impacts": dict(impacts),
                }
            history = deque(self.history.get((source, pattern or ""), ()))
            impacts = self.impacts.get((source, pattern or ""), Counter())
        count = len(history)
        priority = self._priority(count, impacts)
        trajectory = sorted(dt.isoformat() for dt in history)
        trend = "stable"
        if len(trajectory) >= 2 and trajectory[-1] > trajectory[-2]:
            trend = "increasing"
        return {
            "source": source,
            "event_type": pattern or "*",
            "count": count,
            "priority": priority,
            "trend": trend,
            "window_minutes": int(self.window.total_seconds() // 60),
            "confidence": min(1.0, 0.4 + 0.15 * count),
            "trajectory": trajectory,
            "impacts": dict(impacts),
        }

    @staticmethod
    def _priority(count: int, impacts: Counter[str]) -> str:
        if impacts.get("critical") or impacts.get("failed"):
            return "critical"
        if count >= 3:
            return "critical"
        if count == 2:
            return "elevated"
        if impacts.get("degraded"):
            return "warning"
        return "baseline"


class IntegrationMemory:
    """Manage the /integration mount, ledger, and projection state."""

    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.Lock()
        self.root = root or _default_root()
        self.ledger_path = self.root / "ledger.jsonl"
        self.state_path = self.root / "state_vectors.json"
        self.locks_path = self.root / "locks.json"
        self._state = _StateIndex()
        self._locked: set[str] = set()
        self._ensure_root()
        self._load_locks()
        self._reload_state()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _load_locks(self) -> None:
        if self.locks_path.exists():
            try:
                data = json.loads(self.locks_path.read_text(encoding="utf-8"))
                self._locked = {str(item) for item in data}
            except json.JSONDecodeError:
                self._locked = set()
        else:
            self._locked = set()

    def _save_locks(self) -> None:
        self.locks_path.write_text(json.dumps(sorted(self._locked)), encoding="utf-8")

    def _reload_state(self) -> None:
        self._state.reset()
        for entry in self.load_events(limit=None):
            self._state.update(entry)

    def reconfigure(self, root: Path) -> None:
        with self._lock:
            self.root = root
            self.ledger_path = self.root / "ledger.jsonl"
            self.state_path = self.root / "state_vectors.json"
            self.locks_path = self.root / "locks.json"
            self._ensure_root()
            self._load_locks()
            self._reload_state()

    # Public API ---------------------------------------------------------
    def record_event(
        self,
        event_type: str,
        *,
        source: str,
        impact: str,
        confidence: float = 0.5,
        timestamp: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> IntegrationEntry:
        entry = IntegrationEntry(
            id=str(uuid.uuid4()),
            timestamp=_ensure_timestamp(timestamp),
            source=source,
            event_type=event_type,
            impact=impact,
            confidence=max(0.0, min(1.0, float(confidence))),
            payload=dict(payload or {}),
        )
        line = json.dumps(entry.to_dict(), sort_keys=True)
        with self._lock:
            self._ensure_root()
            with self.ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._state.update(entry)
            self._persist_state()
        return entry

    def load_events(self, limit: int | None = 50) -> list[IntegrationEntry]:
        if not self.ledger_path.exists():
            return []
        entries: list[IntegrationEntry] = []
        with self.ledger_path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        if limit is not None:
            lines = lines[-limit:]
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            entry = IntegrationEntry(
                id=str(data.get("id", uuid.uuid4())),
                timestamp=_ensure_timestamp(str(data.get("timestamp"))),
                source=str(data.get("source", "unknown")),
                event_type=str(data.get("event_type", "unknown")),
                impact=str(data.get("impact", "baseline")),
                confidence=float(data.get("confidence", 0.0)),
                payload=dict(data.get("payload", {})),
            )
            entries.append(entry)
        return entries

    def state_vector(self, source: str | None = None) -> dict[str, Any]:
        return self._state.snapshot(source)

    def project_state(self, source: str, event_type: str | None = None) -> dict[str, Any]:
        return self._state.projection(source, event_type)

    def locked_entries(self) -> set[str]:
        return set(self._locked)

    def lock_entry(self, entry_id: str) -> None:
        with self._lock:
            self._locked.add(entry_id)
            self._save_locks()

    def unlock_entry(self, entry_id: str) -> None:
        with self._lock:
            self._locked.discard(entry_id)
            self._save_locks()

    def prune(
        self,
        *,
        before: str | datetime | None = None,
        source: str | None = None,
        keep_locked: bool = True,
    ) -> int:
        """Remove entries matching filters and return count pruned."""

        before_ts: datetime | None = None
        if isinstance(before, datetime):
            before_ts = before.astimezone(timezone.utc)
        elif isinstance(before, str):
            before_ts = _parse_timestamp(before)
        elif before is None:
            before_ts = None

        entries = self.load_events(limit=None)
        kept: list[IntegrationEntry] = []
        pruned = 0
        for entry in entries:
            if keep_locked and entry.id in self._locked:
                kept.append(entry)
                continue
            if source is not None and entry.source != source:
                kept.append(entry)
                continue
            if before_ts is not None and _parse_timestamp(entry.timestamp) >= before_ts:
                kept.append(entry)
                continue
            pruned += 1
        if pruned:
            with self._lock:
                self._ensure_root()
                with self.ledger_path.open("w", encoding="utf-8") as handle:
                    for entry in kept:
                        handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
                self._reload_state()
        return pruned

    def replay(self, entry_id: str) -> IntegrationEntry | None:
        entries = self.load_events(limit=None)
        for entry in entries:
            if entry.id == entry_id:
                payload = dict(entry.payload)
                payload["replay_of"] = entry.id
                return self.record_event(
                    entry.event_type,
                    source=entry.source,
                    impact="stabilized" if entry.impact == "degraded" else entry.impact,
                    confidence=entry.confidence,
                    payload=payload,
                )
        return None

    def _persist_state(self) -> None:
        snapshot = {
            "vectors": self._state.snapshot(),
        }
        self.state_path.write_text(json.dumps(snapshot, sort_keys=True, indent=2), encoding="utf-8")


integration_memory = IntegrationMemory()


def configure_integration_root(path: Path | str) -> IntegrationMemory:
    root = path if isinstance(path, Path) else Path(path)
    integration_memory.reconfigure(root)
    return integration_memory
