from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

try:
    from logging_config import get_log_path
except ImportError:
    def get_log_path(name: str, env_var: str | None = None) -> Path:
        return Path(name)

# We rely on ReflexGuard to parse reflex trial logs
from sentientos.daemons.reflex_guard import ReflexGuard

try:
    from integration_memory import IntegrationMemory  # optional integration memory for event recording
except ImportError:
    IntegrationMemory = None  # type: ignore

class ReflexAnomalyForecaster:
    """Forecast reflex-trigger instability, projecting recurrence risk and flagging for council review."""
    def __init__(
        self,
        ledger_path: Path | str | None = None,
        config_path: Path | str | None = None,
        integration_memory: Optional[IntegrationMemory] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.ledger_path = Path(ledger_path or "reflections/reflex_trials.jsonl")
        self.config_path = Path(config_path or "config/reflex_config.json")
        self.integration_memory = integration_memory
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self.forecast_log = get_log_path("reflex_forecast.jsonl")

    def forecast(self) -> dict:
        """Analyze recent reflex trial patterns and flag unstable rules with predicted risk levels."""
        guard = ReflexGuard(ledger_path=self.ledger_path, blacklist_path=None, config_path=self.config_path,
                            digest_path=None, integration_memory=self.integration_memory, now_fn=self._now)
        config = guard.load_config()
        trials = guard._load_trials()
        snapshots = guard._summarize_rules(trials, config)
        flagged: list[dict] = []
        for snapshot in snapshots:
            reasons = snapshot.reasons(config)
            if reasons:
                continue  # skip rules already suppressed or with anomalies
            # Compute instability risk score
            firing_ratio = snapshot.firing_count / float(config.get("max_firings_per_window", 1))
            failure_ratio = snapshot.failure_count / float(config.get("failure_threshold", 1))
            risk_score = max(firing_ratio, failure_ratio)
            if risk_score < 0.4:
                continue  # low risk, ignore
            risk_level = "high" if risk_score >= 0.8 else "medium"
            entry = {
                "timestamp": self._now().isoformat(),
                "rule_id": snapshot.rule_id,
                "firing_count": snapshot.firing_count,
                "failure_count": snapshot.failure_count,
                "risk_level": risk_level,
                "projected_recurrence": "likely" if risk_level == "high" else "possible",
            }
            flagged.append(entry)
            # Append to forecast log
            self.forecast_log.parent.mkdir(parents=True, exist_ok=True)
            with self.forecast_log.open("a", encoding="utf-8") as log_f:
                log_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            # Optionally record an integration event for council or monitoring
            if self.integration_memory is not None:
                try:
                    payload = {
                        "rule_id": snapshot.rule_id,
                        "anomaly_pattern": "reflex_instability",
                        "reasons": [],  # no suppression reasons, just instability
                        "firing_count": snapshot.firing_count,
                        "failure_count": snapshot.failure_count,
                        "risk_level": risk_level,
                    }
                    confidence = 0.9 if risk_level == "high" else 0.7
                    self.integration_memory.record_event(
                        "reflex_forecast",
                        source="ReflexAnomalyForecaster",
                        impact="warning",
                        confidence=confidence,
                        payload=payload,
                    )
                except Exception:
                    pass
        return {"flagged_rules": flagged, "flag_count": len(flagged), "forecast_log": str(self.forecast_log)}
