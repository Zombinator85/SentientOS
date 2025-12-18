"""Observer emission index for read-only daemons.

The index does not alter observer behavior. It simply consolidates emitted
signals, suppressing redundant chatter while preserving a complete audit log of
what was observed. Only read-only metadata is stored; no observer gains write
authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping


@dataclass
class ObserverRegistration:
    name: str
    signal: str
    frequency: str | float
    last_delta: float | None = None
    emissions: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "observer": self.name,
            "signal": self.signal,
            "frequency": self.frequency,
            "last_delta": self.last_delta,
            "emissions": self.emissions,
        }


@dataclass
class ObserverReport:
    observer: str
    signal: str
    delta: float
    confidence: float
    frequency: str | float
    suppressed: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, object]:
        return {
            "observer": self.observer,
            "signal": self.signal,
            "delta": self.delta,
            "confidence": self.confidence,
            "frequency": self.frequency,
            "suppressed": self.suppressed,
            "timestamp": self.timestamp,
        }


class ObserverIndex:
    """Track read-only observers and consolidate their emissions."""

    def __init__(self, confidence_threshold: float = 0.0) -> None:
        self.confidence_threshold = float(confidence_threshold)
        self._registry: dict[str, ObserverRegistration] = {}
        self._audit_log: list[ObserverReport] = []

    @property
    def audit_log(self) -> list[dict[str, object]]:
        return [entry.to_dict() for entry in self._audit_log]

    def register(self, name: str, signal: str, frequency: str | float) -> None:
        self._registry[name] = ObserverRegistration(name=name, signal=signal, frequency=frequency)

    def heartbeat(self, observations: Iterable[Mapping[str, object]]) -> dict[str, object]:
        emissions: list[dict[str, object]] = []
        for observation in observations:
            name = str(observation.get("observer") or observation.get("name") or "").strip()
            signal = str(observation.get("signal") or "").strip()
            delta_raw = observation.get("delta")
            confidence = float(observation.get("confidence", 1.0))
            frequency = observation.get("frequency", "unspecified")

            if name and name not in self._registry:
                self.register(name, signal=signal, frequency=frequency)

            if name not in self._registry:
                continue

            registration = self._registry[name]
            delta = float(delta_raw) if delta_raw is not None else 0.0
            should_suppress = self._should_suppress(registration, delta, confidence)

            report = ObserverReport(
                observer=name,
                signal=registration.signal,
                delta=delta,
                confidence=confidence,
                frequency=registration.frequency,
                suppressed=should_suppress,
            )
            self._audit_log.append(report)

            if should_suppress:
                continue

            registration.last_delta = delta
            registration.emissions += 1
            emissions.append(
                {
                    "observer": name,
                    "signal": registration.signal,
                    "delta": delta,
                    "confidence": confidence,
                    "frequency": registration.frequency,
                }
            )

        heartbeat = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "emissions": emissions,
            "registry": [entry.to_dict() for entry in self._registry.values()],
            "audit_log": self.audit_log,
        }
        return heartbeat

    def _should_suppress(self, registration: ObserverRegistration, delta: float, confidence: float) -> bool:
        if registration.last_delta is not None and delta == registration.last_delta:
            return True
        if confidence < self.confidence_threshold:
            return True
        return False


__all__ = ["ObserverIndex", "ObserverRegistration", "ObserverReport"]
