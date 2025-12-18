from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, MutableSequence


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
]
