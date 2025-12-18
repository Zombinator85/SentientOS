from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable, Mapping, MutableSequence, Sequence


@dataclass
class ObservationFragment:
    source: str
    timestamp: str
    confidence: float
    payload: Mapping[str, object]
    advisory: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "payload": dict(self.payload),
            "advisory": list(self.advisory),
        }


class CuriosityLimiter:
    """Limit external observation volume and surface advisory signals."""

    def __init__(
        self,
        *,
        daily_cap: int = 50,
        emotional_cooldown_seconds: float = 900.0,
        saturation_threshold: float = 0.8,
        now_fn=None,
    ) -> None:
        self.daily_cap = max(1, int(daily_cap))
        self.emotional_cooldown_seconds = float(emotional_cooldown_seconds)
        self.saturation_threshold = float(saturation_threshold)
        self._now = now_fn or time.time
        self._date = self._current_date()
        self._count = 0
        self._cooldown_until: float | None = None

    def _current_date(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _rollover(self, now: float) -> None:
        current_date = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
        if current_date != self._date:
            self._date = current_date
            self._count = 0
            self._cooldown_until = None

    def assess(self, fragment: Mapping[str, object]) -> tuple[bool, tuple[str, ...]]:
        now = float(self._now())
        self._rollover(now)
        advisories: list[str] = []
        if self._cooldown_until and now < self._cooldown_until:
            advisories.append("cooldown_active")
            return False, tuple(advisories)
        if self._count >= self.daily_cap:
            advisories.append("daily_cap_reached")
            return False, tuple(advisories)
        emotional_density = float(fragment.get("emotional_density", 0.0) or 0.0)
        adversarial = bool(fragment.get("adversarial"))
        if emotional_density >= 0.6 or adversarial:
            self._cooldown_until = now + self.emotional_cooldown_seconds
            advisories.append("cooldown_started")
        self._count += 1
        if self._count >= self.daily_cap * self.saturation_threshold:
            advisories.append("approaching_saturation")
        return True, tuple(advisories)


class CuriosityScheduler:
    """Select read-only observation tasks during idle windows."""

    def __init__(self, limiter: CuriosityLimiter | None = None) -> None:
        self._limiter = limiter or CuriosityLimiter()
        self._log: MutableSequence[ObservationFragment] = []

    @property
    def log(self) -> list[dict[str, object]]:
        return [entry.to_dict() for entry in self._log]

    def run_idle_cycle(
        self,
        tasks: Iterable[Mapping[str, object]],
        *,
        idle: bool,
    ) -> list[dict[str, object]]:
        if not idle:
            return []
        fragments: list[dict[str, object]] = []
        for task in tasks:
            action = str(task.get("action", "observe")).lower()
            if action not in {"observe", "read", "ingest"}:
                raise ValueError("Outbound interaction is not permitted in curiosity scheduler")
            allowed, advisories = self._limiter.assess(task)
            if not allowed:
                fragments.append(
                    ObservationFragment(
                        source=str(task.get("source") or "unknown"),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        confidence=float(task.get("confidence", 0.5)),
                        payload={"skipped": True},
                        advisory=advisories,
                    ).to_dict()
                )
                continue
            fragment = ObservationFragment(
                source=str(task.get("source") or "unknown"),
                timestamp=datetime.now(timezone.utc).isoformat(),
                confidence=float(task.get("confidence", 0.5)),
                payload={k: v for k, v in task.items() if k != "action"},
                advisory=advisories,
            )
            self._log.append(fragment)
            fragments.append(fragment.to_dict())
        return fragments


class ContinuityLedger:
    """Append-only ledger for cross-day observation themes."""

    def __init__(self, path: str | Path = "continuity_ledger.jsonl") -> None:
        self.path = Path(path)
        self._entries: list[dict[str, object]] = list(self._load())
        self._dormant = {entry.get("theme") for entry in self._entries if entry.get("status") == "dormant"}

    def _load(self) -> Iterable[dict[str, object]]:
        if not self.path.exists():
            return []
        entries: list[dict[str, object]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
        return entries

    def _append(self, record: Mapping[str, object]) -> dict[str, object]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(dict(record), ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(serialized + "\n")
        self._entries.append(dict(record))
        if record.get("status") == "dormant" and record.get("theme"):
            self._dormant.add(str(record["theme"]))
        return dict(record)

    def record_observation(
        self,
        *,
        theme: str,
        signal_strength: float,
        source: str,
        timestamp: str | None = None,
        day_hash: str | None = None,
    ) -> dict[str, object]:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        record = {
            "type": "observation",
            "theme": theme,
            "signal_strength": float(signal_strength),
            "source": source,
            "timestamp": ts,
            "date": ts.split("T")[0],
            "day_hash": day_hash,
        }
        return self._append(record)

    def link_new_day(self, event: Mapping[str, object], unresolved_patterns: Sequence[str]) -> dict[str, object]:
        record = {
            "type": "day_link",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "date": str(event.get("date")),
            "day_hash": event.get("day_hash"),
            "unresolved": list(unresolved_patterns),
        }
        return self._append(record)

    def mark_dormant(self, theme: str, *, reason: str, timestamp: str | None = None) -> dict[str, object]:
        record = {
            "type": "status",
            "theme": theme,
            "status": "dormant",
            "reason": reason,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        }
        return self._append(record)

    def history(self, theme: str) -> list[dict[str, object]]:
        return [entry for entry in self._entries if entry.get("theme") == theme or entry.get("unresolved")]

    def _daily_signals(self, theme: str) -> list[tuple[str, float]]:
        daily: dict[str, list[float]] = defaultdict(list)
        for entry in self._entries:
            if entry.get("theme") != theme:
                continue
            if "signal_strength" in entry and entry.get("date"):
                daily[str(entry["date"])].append(float(entry["signal_strength"]))
        return sorted(((date, mean(values)) for date, values in daily.items()), key=lambda item: item[0])

    def is_ongoing(self, theme: str) -> bool:
        if theme in self._dormant:
            return False
        return len({date for date, _ in self._daily_signals(theme)}) >= 2

    def signal_direction(self, theme: str) -> str:
        signals = self._daily_signals(theme)
        if len(signals) < 2:
            return "steady"
        (_, previous), (_, latest) = signals[-2], signals[-1]
        if latest > previous + 0.05:
            return "intensified"
        if latest < previous - 0.05:
            return "decayed"
        return "steady"

    def days_alive(self, theme: str, *, current_date: str | None = None) -> int:
        signals = self._daily_signals(theme)
        if not signals:
            return 0
        first_date = signals[0][0]
        today = current_date or datetime.now(timezone.utc).date().isoformat()
        start = datetime.fromisoformat(first_date).date()
        end = datetime.fromisoformat(today).date()
        return (end - start).days

    def days_without_action(self, theme: str, *, current_date: str | None = None) -> int:
        # No expression intents are recorded; track observational span only.
        return self.days_alive(theme, current_date=current_date)


class NonEscalationEnforcer:
    """Block synthesis-to-expression pathways and surface advisory warnings."""

    def __init__(self, *, convergence_floor: float = 0.05) -> None:
        self.convergence_floor = float(convergence_floor)

    def ensure_internal_only(self, note: Mapping[str, object]) -> None:
        if note.get("intent") or note.get("action") or note.get("recommendation"):
            raise PermissionError("Expression intents are blocked for synthesis notes")

    def review_batch(self, theme: str, *, volatility: float, count: int) -> tuple[str, ...]:
        advisories: list[str] = []
        if volatility < self.convergence_floor and count > 1:
            advisories.append("convergence_warning")
        return tuple(advisories)


class SynthesisDaemon:
    """Cluster observation fragments into internal-only synthesis notes."""

    def __init__(self, *, enforcer: NonEscalationEnforcer | None = None) -> None:
        self._enforcer = enforcer or NonEscalationEnforcer()

    def _summarize(self, fragments: Sequence[Mapping[str, object]]) -> str:
        snippets: list[str] = []
        for fragment in fragments:
            payload = fragment.get("payload") or {}
            if isinstance(payload, Mapping):
                summary = payload.get("summary") or payload.get("observation")
                if summary:
                    snippets.append(str(summary))
        if not snippets:
            return "Internal synthesis with limited detail available"
        return " | ".join(snippets)

    def synthesize(self, fragments: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        grouped: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
        for fragment in fragments:
            payload = fragment.get("payload") or {}
            theme = None
            if isinstance(payload, Mapping):
                theme = payload.get("theme")
            theme_key = str(theme or fragment.get("source") or "unknown")
            grouped[theme_key].append(fragment)

        notes: list[dict[str, object]] = []
        for theme, entries in grouped.items():
            confidences = [float(entry.get("confidence", 0.0)) for entry in entries]
            volatility = pstdev(confidences) if len(confidences) > 1 else 0.0
            note = {
                "theme": theme,
                "summary": self._summarize(entries),
                "confidence": round(mean(confidences), 3) if confidences else 0.0,
                "volatility": round(volatility, 3),
                "expression_permitted": False,
                "intent": None,
                "action": None,
            }
            self._enforcer.ensure_internal_only(note)
            advisory = self._enforcer.review_batch(theme, volatility=volatility, count=len(entries))
            if advisory:
                note["advisory"] = list(advisory)
            notes.append(note)
        return notes


class PatternDormancyDetector:
    """Detect when observation themes have stabilized or decayed."""

    def __init__(
        self,
        *,
        decay_threshold: float = 0.2,
        plateau_tolerance: float = 0.02,
        stability_window: int = 3,
        saturation_floor: float = 0.9,
    ) -> None:
        self.decay_threshold = float(decay_threshold)
        self.plateau_tolerance = float(plateau_tolerance)
        self.stability_window = max(2, int(stability_window))
        self.saturation_floor = float(saturation_floor)

    def evaluate(self, ledger: ContinuityLedger, theme: str) -> dict[str, object] | None:
        signals = ledger._daily_signals(theme)
        if len(signals) < self.stability_window:
            return None
        last_values = [value for _, value in signals[-self.stability_window :]]
        reason: str | None = None
        if last_values[-1] < self.decay_threshold and last_values == sorted(last_values, reverse=True):
            reason = "decayed"
        elif all(value < self.decay_threshold for value in last_values):
            reason = "decayed"
        elif max(last_values) - min(last_values) < self.plateau_tolerance:
            reason = "stabilized"
        elif all(value >= self.saturation_floor for value in last_values):
            reason = "saturated"
        if not reason:
            return None
        record = ledger.mark_dormant(theme, reason=reason)
        return {"theme": theme, "status": record["status"], "reason": reason}


class ExternalWitnessGate:
    """Gate external ingestion to ensure read-only posture and auditing."""

    def __init__(self) -> None:
        self.audit_log: list[dict[str, object]] = []

    def ingest(
        self,
        *,
        source: str,
        content: Mapping[str, object],
        mode: str = "read",
        intent: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        normalized_mode = mode.lower().strip()
        if normalized_mode != "read":
            approved = bool(intent and intent.get("type") == "ExpressionIntent" and intent.get("approved"))
            if not approved:
                raise PermissionError("External ingestion is read-only without approved ExpressionIntent")
        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "source": source,
            "mode": normalized_mode,
            "timestamp": timestamp,
            "non_canonical": True,
            "authoritative": False,
            "content": dict(content),
        }
        self.audit_log.append({"source": source, "timestamp": timestamp, "mode": normalized_mode})
        return record


__all__ = [
    "CuriosityLimiter",
    "CuriosityScheduler",
    "ExternalWitnessGate",
    "ObservationFragment",
    "ContinuityLedger",
    "SynthesisDaemon",
    "PatternDormancyDetector",
    "NonEscalationEnforcer",
]
