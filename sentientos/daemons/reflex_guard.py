"""Reflex saturation guard daemon.

This module monitors the reflex execution ledger to detect saturation
patterns and persistently failing reflex rules. Offending rules are
suppressed by recording them in a blacklist until a human operator clears
the entry.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from logging_config import get_log_path

try:
    from integration_memory import IntegrationMemory
except Exception:  # pragma: no cover - optional dependency in some envs
    IntegrationMemory = None  # type: ignore[misc, assignment]


DEFAULT_CONFIG = {
    "max_firings_per_window": 10,
    "failure_threshold": 5,
    "saturation_window_seconds": 300,
}


@dataclass
class ReflexRuleSnapshot:
    rule_id: str
    firing_count: int
    failure_count: int
    recent_trials: list[dict]

    def reasons(self, config: dict[str, int]) -> list[str]:
        notes: list[str] = []
        if self.firing_count > int(config["max_firings_per_window"]):
            notes.append("saturation_window_exceeded")
        if self.failure_count >= int(config["failure_threshold"]):
            notes.append("persistent_failures")
        return notes


def _parse_timestamp(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    text = str(raw)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ReflexGuard:
    """Monitor reflex trial logs for overloads and unhealthy patterns."""

    def __init__(
        self,
        *,
        ledger_path: Path | str | None = None,
        blacklist_path: Path | str | None = None,
        config_path: Path | str | None = None,
        digest_path: Path | str | None = None,
        integration_memory: IntegrationMemory | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.ledger_path = Path(ledger_path or "reflections/reflex_trials.jsonl")
        self.blacklist_path = Path(blacklist_path or "reflex_blacklist.json")
        self.config_path = Path(config_path or "config/reflex_config.json")
        self.digest_path = (
            Path(digest_path)
            if digest_path
            else get_log_path("daily_digest.jsonl", "DAILY_DIGEST_LOG")
        )
        self.integration_memory = integration_memory
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self.anomaly_log = get_log_path("reflex_guard.jsonl")

    def load_config(self) -> dict[str, int]:
        if not self.config_path.exists():
            return dict(DEFAULT_CONFIG)
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return dict(DEFAULT_CONFIG)
        config = dict(DEFAULT_CONFIG)
        for key, value in data.items():
            if key in DEFAULT_CONFIG:
                config[key] = int(value)
        return config

    def _load_trials(self) -> list[dict]:
        if not self.ledger_path.exists():
            return []
        trials: list[dict] = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "rule_id" not in data:
                continue
            trials.append(data)
        return trials

    def _summarize_rules(
        self, trials: Iterable[dict], config: dict[str, int]
    ) -> list[ReflexRuleSnapshot]:
        window = timedelta(seconds=int(config["saturation_window_seconds"]))
        cutoff = self._now() - window
        timestamps: dict[str, list[datetime]] = defaultdict(list)
        status_by_rule: dict[str, list[str]] = defaultdict(list)
        recent_trials: dict[str, list[dict]] = defaultdict(list)
        for trial in trials:
            rule_id = str(trial.get("rule_id"))
            ts = _parse_timestamp(str(trial.get("timestamp")))
            status = str(trial.get("status", "unknown")).lower()
            timestamps[rule_id].append(ts)
            status_by_rule[rule_id].append(status)
            if ts >= cutoff:
                recent_trials[rule_id].append(trial)

        snapshots: list[ReflexRuleSnapshot] = []
        for rule_id, times in timestamps.items():
            firings = [ts for ts in times if ts >= cutoff]
            statuses = status_by_rule[rule_id][-20:]
            failures = sum(1 for status in statuses if "fail" in status or status == "error")
            snapshots.append(
                ReflexRuleSnapshot(
                    rule_id=rule_id,
                    firing_count=len(firings),
                    failure_count=failures,
                    recent_trials=recent_trials.get(rule_id, []),
                )
            )
        return snapshots

    def _record_anomaly(self, snapshot: ReflexRuleSnapshot, config: dict[str, int]) -> None:
        payload = {
            "timestamp": self._now().isoformat(),
            "category": "reflex_saturation",
            "rule_id": snapshot.rule_id,
            "firing_count": snapshot.firing_count,
            "failure_count": snapshot.failure_count,
            "window_seconds": int(config["saturation_window_seconds"]),
            "status": "suppressed",
        }
        line = json.dumps(payload, sort_keys=True)
        self.anomaly_log.parent.mkdir(parents=True, exist_ok=True)
        with self.anomaly_log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _emit_integration_notification(
        self, snapshot: ReflexRuleSnapshot, reasons: list[str]
    ) -> None:
        if self.integration_memory is None:
            return
        payload = {
            "rule_id": snapshot.rule_id,
            "anomaly_pattern": "reflex_saturation",
            "reasons": reasons,
            "firing_count": snapshot.firing_count,
            "failure_count": snapshot.failure_count,
        }
        try:
            self.integration_memory.record_event(
                "reflex_guard",
                source="ReflexGuard",
                impact="suppress_reflex",
                confidence=0.8,
                payload=payload,
            )
        except Exception:
            return

    def _append_digest(self, suppressed: list[dict]) -> None:
        if not suppressed:
            return
        entry = {
            "timestamp": self._now().isoformat(),
            "event": "reflex_guard",
            "suppressed": suppressed,
        }
        self.digest_path.parent.mkdir(parents=True, exist_ok=True)
        with self.digest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _load_blacklist(self) -> dict[str, dict]:
        if not self.blacklist_path.exists():
            return {}
        try:
            return json.loads(self.blacklist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_blacklist(self, data: dict[str, dict]) -> None:
        self.blacklist_path.parent.mkdir(parents=True, exist_ok=True)
        self.blacklist_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _suppress_rule(self, snapshot: ReflexRuleSnapshot, reasons: list[str]) -> dict:
        blacklist = self._load_blacklist()
        entry = {
            "suppressed_at": self._now().isoformat(),
            "reasons": reasons,
            "firing_count": snapshot.firing_count,
            "failure_count": snapshot.failure_count,
        }
        blacklist[snapshot.rule_id] = entry
        self._save_blacklist(blacklist)
        return {"rule_id": snapshot.rule_id, **entry}

    def scan_and_suppress(self) -> dict[str, object]:
        config = self.load_config()
        trials = self._load_trials()
        snapshots = self._summarize_rules(trials, config)

        suppressed: list[dict] = []
        for snapshot in snapshots:
            reasons = snapshot.reasons(config)
            if not reasons:
                continue
            suppressed_entry = self._suppress_rule(snapshot, reasons)
            suppressed.append(suppressed_entry)
            self._record_anomaly(snapshot, config)
            self._emit_integration_notification(snapshot, reasons)

        self._append_digest(suppressed)
        return {
            "scanned_rules": len(snapshots),
            "suppressed": suppressed,
            "config": config,
        }

