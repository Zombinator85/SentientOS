from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


@dataclass
class ReflexState:
    rule_id: str
    activity_rate: float = 0.0
    suppression_reasons: list[str] = field(default_factory=list)
    suppressed: bool = False
    petition_eligible: bool = False
    petition_trials: int = 0
    forecast_confidence: float = 0.0
    suppression_timestamp: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "activity_rate": round(self.activity_rate, 3),
            "suppression_reasons": list(self.suppression_reasons),
            "suppressed": self.suppressed,
            "petition_eligible": self.petition_eligible,
            "petition_trials": self.petition_trials,
            "forecast_confidence": round(self.forecast_confidence, 3),
            "suppression_timestamp": self.suppression_timestamp,
        }


class ReflexStateIndex:
    """Shared state for guard, forecasting, and petitions."""

    def __init__(self, snapshot_path: Path | str | None = None) -> None:
        self.snapshot_path = Path(snapshot_path or "reflections/reflex_state_index.json")
        self._state: dict[str, ReflexState] = {}
        self._load()

    def update_activity(self, snapshots: Iterable[Mapping[str, object]], window_seconds: int) -> None:
        window = max(1, int(window_seconds))
        for entry in snapshots:
            rule_id = str(entry.get("rule_id"))
            if not rule_id:
                continue
            firing_count = int(entry.get("firing_count", 0))
            activity_rate = firing_count / window
            state = self._state.setdefault(rule_id, ReflexState(rule_id=rule_id))
            state.activity_rate = activity_rate

    def mark_suppressed(self, rule_id: str, reasons: Iterable[str], timestamp: str | None = None) -> None:
        state = self._state.setdefault(rule_id, ReflexState(rule_id=rule_id))
        state.suppressed = True
        state.suppression_reasons = sorted(set(map(str, reasons)))
        state.suppression_timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def mark_forecast(self, rule_id: str, confidence: float) -> None:
        state = self._state.setdefault(rule_id, ReflexState(rule_id=rule_id))
        state.forecast_confidence = max(state.forecast_confidence, float(confidence))

    def mark_petition(self, rule_id: str, eligible: bool, trials: int) -> None:
        state = self._state.setdefault(rule_id, ReflexState(rule_id=rule_id))
        state.petition_eligible = bool(eligible)
        state.petition_trials = max(state.petition_trials, int(trials))

    def mark_reinstated(self, rule_id: str) -> None:
        state = self._state.setdefault(rule_id, ReflexState(rule_id=rule_id))
        state.suppressed = False
        state.suppression_reasons = []
        state.petition_eligible = False

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {rule_id: state.to_dict() for rule_id, state in sorted(self._state.items())}

    def persist(self) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(json.dumps(self.snapshot(), indent=2, sort_keys=True), encoding="utf-8")

    def _load(self) -> None:
        if not self.snapshot_path.exists():
            return
        try:
            payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        for rule_id, data in payload.items():
            self._state[rule_id] = ReflexState(
                rule_id=rule_id,
                activity_rate=float(data.get("activity_rate", 0.0)),
                suppression_reasons=list(data.get("suppression_reasons", [])),
                suppressed=bool(data.get("suppressed", False)),
                petition_eligible=bool(data.get("petition_eligible", False)),
                petition_trials=int(data.get("petition_trials", 0)),
                forecast_confidence=float(data.get("forecast_confidence", 0.0)),
                suppression_timestamp=str(data.get("suppression_timestamp")) if data.get("suppression_timestamp") else None,
            )


__all__ = ["ReflexState", "ReflexStateIndex"]
