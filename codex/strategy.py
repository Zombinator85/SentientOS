"""Adaptive strategy management for Codex plan execution."""
from __future__ import annotations

import json
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Sequence

from integration_memory import integration_memory

from .intent import PriorityWeights

__all__ = [
    "OutcomeEntry",
    "StrategyAdjustmentEngine",
    "strategy_engine",
    "configure_strategy_root",
]


_DEFAULT_OUTCOME_STATUS = {"success", "failure", "rollback", "override"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_timestamp(value: datetime | str | None = None) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return _now().isoformat()


def _impact_from_metadata(metadata: Mapping[str, Any]) -> str:
    severity = metadata.get("severity")
    if isinstance(severity, (int, float)):
        if float(severity) >= 0.75:
            return "high"
        if float(severity) >= 0.45:
            return "medium"
        return "low"
    if severity:
        text = str(severity).lower()
        if text in {"critical", "high", "severe"}:
            return "high"
        if text in {"warning", "medium"}:
            return "medium"
        return "low"
    impact_hint = metadata.get("impact")
    if isinstance(impact_hint, str):
        text = impact_hint.lower()
        if text in {"critical", "system", "daemon"}:
            return "high"
        if text in {"warning", "environment", "service", "medium"}:
            return "medium"
    return "low"


def _confidence_from_metadata(metadata: Mapping[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(metadata.get("confidence", 0.6))))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0.6


def _integration_impact(status: str, impact: str) -> str:
    if status == "rollback":
        return "failed"
    if impact == "high":
        return "critical"
    if impact == "medium":
        return "warning"
    return "baseline"


@dataclass(frozen=True)
class OutcomeEntry:
    """Serialized record of a plan step execution outcome."""

    plan_id: str
    plan_goal: str
    step_index: int
    step_title: str
    step_action: str
    step_kind: str
    status: str
    impact: str
    operator_action: str
    timestamp: str = field(default_factory=lambda: _serialize_timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "plan_id": self.plan_id,
            "plan_goal": self.plan_goal,
            "step_index": self.step_index,
            "step_title": self.step_title,
            "step_action": self.step_action,
            "step_kind": self.step_kind,
            "status": self.status,
            "impact": self.impact,
            "operator_action": self.operator_action,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }
        return payload


class _OutcomeLogger:
    """Write outcome entries to /integration/outcomes."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, entry: OutcomeEntry) -> Path:
        path = self._base_dir / f"{entry.plan_id}.jsonl"
        line = json.dumps(entry.to_dict(), sort_keys=True)
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return path


class StrategyAdjustmentEngine:
    """Manage adaptive strategy adjustments based on plan outcomes."""

    def __init__(self, root: Path | str = Path("integration"), *, override_threshold: int = 3) -> None:
        self._root = Path(root)
        self._override_threshold = max(1, int(override_threshold))
        self._lock = threading.Lock()
        self._logger = _OutcomeLogger(self._root / "outcomes")
        self._strategy_log_path = self._root / "strategy_log.jsonl"
        self._state_path = self._root / "strategy_state.json"
        self._weights = PriorityWeights().normalized()
        self._version = 1
        self._locked = False
        self._metrics: MutableMapping[str, float] = defaultdict(float)
        self._action_success: Counter[str] = Counter()
        self._action_rollbacks: Counter[str] = Counter()
        self._sequence_counts: Counter[tuple[str, str]] = Counter()
        self._preferred_sequences: Dict[tuple[str, str], int] = {}
        self._load_state()

    # ------------------------------------------------------------------
    # Public properties
    @property
    def strategy_version(self) -> int:
        return self._version

    @property
    def locked(self) -> bool:
        return self._locked

    def weights(self) -> PriorityWeights:
        return PriorityWeights(
            self._weights.severity,
            self._weights.frequency,
            self._weights.impact,
            self._weights.confidence,
        )

    def weights_dict(self) -> Dict[str, float]:
        return {
            "severity": self._weights.severity,
            "frequency": self._weights.frequency,
            "impact": self._weights.impact,
            "confidence": self._weights.confidence,
        }

    # ------------------------------------------------------------------
    def reconfigure(self, root: Path | str) -> None:
        with self._lock:
            self._root = Path(root)
            self._logger = _OutcomeLogger(self._root / "outcomes")
            self._strategy_log_path = self._root / "strategy_log.jsonl"
            self._state_path = self._root / "strategy_state.json"
            self._version = 1
            self._locked = False
            self._metrics = defaultdict(float)
            self._action_success = Counter()
            self._action_rollbacks = Counter()
            self._sequence_counts = Counter()
            self._preferred_sequences = {}
            self._weights = PriorityWeights().normalized()
            self._load_state()

    # ------------------------------------------------------------------
    def record_outcome(
        self,
        *,
        plan_id: str,
        plan_goal: str,
        step_index: int,
        step_title: str,
        step_action: str,
        step_kind: str,
        status: str,
        operator_action: str,
        step_metadata: Mapping[str, Any] | None = None,
        result: Any | None = None,
        error: str | None = None,
    ) -> OutcomeEntry:
        status_key = str(status).lower()
        if status_key not in _DEFAULT_OUTCOME_STATUS:
            status_key = "failure"
        metadata = dict(step_metadata or {})
        if result is not None:
            metadata.setdefault("result", result)
        if error:
            metadata.setdefault("error", error)
        impact = _impact_from_metadata(metadata)
        timestamp = _serialize_timestamp(metadata.get("timestamp"))
        entry = OutcomeEntry(
            plan_id=plan_id,
            plan_goal=plan_goal,
            step_index=step_index,
            step_title=step_title,
            step_action=step_action,
            step_kind=step_kind,
            status=status_key,
            impact=impact,
            operator_action=str(operator_action or "approve"),
            timestamp=timestamp,
            metadata=metadata,
        )
        with self._lock:
            self._logger.log(entry)
            self._update_metrics(entry)
            self._maybe_adjust(entry)
            self._persist_state()
        integration_memory.record_event(
            "plan.outcome",
            source=plan_id,
            impact=_integration_impact(entry.status, entry.impact),
            confidence=_confidence_from_metadata(metadata),
            payload={
                "plan_goal": plan_goal,
                "step_index": step_index,
                "step_title": step_title,
                "status": entry.status,
                "operator_action": entry.operator_action,
                "strategy_version": self._version,
                "override_sequence": metadata.get("override_sequence"),
            },
        )
        return entry

    def set_lock(self, locked: bool, *, operator: str | None = None) -> None:
        with self._lock:
            if self._locked == locked:
                return
            self._locked = locked
            self._version += 1
            self._append_strategy_log(
                "locked" if locked else "unlocked",
                {
                    "operator": operator,
                    "locked": locked,
                },
            )
            self._persist_state()

    def sequence_summary(self) -> str | None:
        if not self._preferred_sequences:
            return None
        key, count = max(self._preferred_sequences.items(), key=lambda item: item[1])
        start, follow = key
        return f"Codex adjusted sequencing of {start} → {follow} based on {count} prior overrides."

    # ------------------------------------------------------------------
    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        weights = payload.get("weights") or {}
        try:
            self._weights = PriorityWeights(
                float(weights.get("severity", 0.4)),
                float(weights.get("frequency", 0.2)),
                float(weights.get("impact", 0.25)),
                float(weights.get("confidence", 0.15)),
            ).normalized()
        except (TypeError, ValueError):  # pragma: no cover - defensive
            self._weights = PriorityWeights().normalized()
        self._version = int(payload.get("version", 1))
        self._locked = bool(payload.get("locked", False))
        self._metrics = defaultdict(float, payload.get("metrics", {}))
        self._action_success = Counter(payload.get("action_success", {}))
        self._action_rollbacks = Counter(payload.get("action_rollbacks", {}))
        raw_sequences = payload.get("sequence_counts", {})
        parsed_sequences: Counter[tuple[str, str]] = Counter()
        for key, count in raw_sequences.items():
            parts = key.split("→")
            if len(parts) == 2:
                parsed_sequences[(parts[0].strip(), parts[1].strip())] = int(count)
        self._sequence_counts = parsed_sequences
        preferred = {}
        for key, count in (payload.get("preferred_sequences", {}) or {}).items():
            parts = key.split("→")
            if len(parts) == 2:
                preferred[(parts[0].strip(), parts[1].strip())] = int(count)
        self._preferred_sequences = preferred

    def _persist_state(self) -> None:
        data = {
            "weights": self.weights_dict(),
            "version": self._version,
            "locked": self._locked,
            "metrics": dict(self._metrics),
            "action_success": dict(self._action_success),
            "action_rollbacks": dict(self._action_rollbacks),
            "sequence_counts": {
                f"{start}→{follow}": count for (start, follow), count in self._sequence_counts.items()
            },
            "preferred_sequences": {
                f"{start}→{follow}": count for (start, follow), count in self._preferred_sequences.items()
            },
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")

    def _append_strategy_log(self, action: str, details: Mapping[str, Any]) -> None:
        record = {
            "timestamp": _serialize_timestamp(),
            "action": action,
            "version": self._version,
            "details": dict(details),
        }
        self._strategy_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._strategy_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _update_metrics(self, entry: OutcomeEntry) -> None:
        action = entry.step_action
        self._metrics["total_steps"] += 1
        if entry.status == "success":
            self._metrics["success"] += 1
            self._action_success[action] += 1
        elif entry.status in {"failure", "rollback"}:
            self._metrics["rollback"] += 1
            self._action_rollbacks[action] += 1
        if entry.operator_action == "override":
            sequence = entry.metadata.get("override_sequence")
            if isinstance(sequence, Sequence) and len(sequence) >= 2:
                start = str(sequence[0])
                follow = str(sequence[1])
                key = (start, follow)
                self._sequence_counts[key] += 1

    def _maybe_adjust(self, entry: OutcomeEntry) -> None:
        if self._locked:
            return
        adjustments: list[str] = []
        total = max(1.0, self._metrics.get("total_steps", 0.0))
        rollback_ratio = self._metrics.get("rollback", 0.0) / total
        if rollback_ratio >= 0.3:
            base = PriorityWeights().normalized()
            penalty = min(0.2, rollback_ratio * 0.2)
            new_weights = PriorityWeights(
                base.severity - penalty,
                base.frequency,
                base.impact,
                base.confidence + penalty,
            ).normalized()
            if any(abs(getattr(self._weights, field) - getattr(new_weights, field)) > 1e-6 for field in ("severity", "frequency", "impact", "confidence")):
                self._weights = new_weights
                self._version += 1
                adjustments.append("weights")
        for key, count in self._sequence_counts.items():
            if count >= self._override_threshold and key not in self._preferred_sequences:
                self._preferred_sequences[key] = count
                self._version += 1
                adjustments.append("sequence")
        if adjustments:
            self._append_strategy_log(
                "adjusted",
                {
                    "adjustments": adjustments,
                    "weights": self.weights_dict(),
                    "preferred_sequences": [
                        {"from": start, "to": follow, "count": count}
                        for (start, follow), count in sorted(
                            self._preferred_sequences.items(), key=lambda item: item[1], reverse=True
                        )
                    ],
                    "rollback_ratio": rollback_ratio,
                },
            )


strategy_engine = StrategyAdjustmentEngine()


def configure_strategy_root(path: Path | str) -> StrategyAdjustmentEngine:
    strategy_engine.reconfigure(path)
    return strategy_engine

