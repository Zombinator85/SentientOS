from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping


class PatternVolatilityScanner:
    """Monitor event frequencies to flag destabilizing spikes."""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.alert_path = self.workspace / "integration_anomalies.jsonl"

    def scan(
        self,
        events: Iterable[Mapping[str, object]],
        *,
        baseline: Iterable[Mapping[str, object]] | None = None,
        threshold_ratio: float = 3.0,
    ) -> list[dict]:
        current_events = list(events)
        baseline_events = list(baseline or [])
        current_counts = self._count_reflexes(current_events)
        baseline_counts = self._count_reflexes(baseline_events)

        alerts: list[dict] = []
        for reflex, count in current_counts.items():
            baseline_count = baseline_counts.get(reflex, 0)
            ratio = count / max(1, baseline_count)
            if ratio >= threshold_ratio:
                risk = min(1.0, round(ratio / (threshold_ratio * 2), 3))
                alert = {
                    "reflex": reflex,
                    "ratio": round(ratio, 3),
                    "instability_risk": risk,
                    "events_seen": count,
                    "baseline_events": baseline_count,
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                }
                alerts.append(alert)
        if alerts:
            self._write_alerts(alerts)
        return alerts

    def _count_reflexes(self, events: Iterable[Mapping[str, object]]) -> Counter:
        counter: Counter = Counter()
        for event in events:
            label = str(event.get("reflex") or event.get("type") or "unknown")
            counter[label] += 1
        return counter

    def _write_alerts(self, alerts: Iterable[Mapping[str, object]]) -> None:
        with self.alert_path.open("a", encoding="utf-8") as handle:
            for alert in alerts:
                handle.write(json.dumps(alert) + "\n")


__all__ = ["PatternVolatilityScanner"]
