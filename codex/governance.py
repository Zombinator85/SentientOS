"""Governance helpers for Codex meta-strategies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from itertools import zip_longest
from pathlib import Path
import threading
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence, TYPE_CHECKING

from integration_memory import integration_memory

from .meta_strategies import CodexMetaStrategy, MetaStrategyStorage

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .strategy import CodexStrategy

__all__ = ["MetaStrategyGovernor", "GovernanceDecision", "SubordinateGovernanceState"]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_sequence(values: Iterable[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, Mapping):
            for item in value.values():
                normalized.extend(_normalize_sequence([item]))
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            normalized.extend(_normalize_sequence(value))
            continue
        text = str(value).strip().lower()
        if text:
            normalized.append(text)
    return normalized


@dataclass
class GovernanceDecision:
    """Projection of a governor action for a subordinate strategy."""

    pattern: str
    strategy_id: str
    status: str
    divergence_score: float
    actions: list[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern": self.pattern,
            "strategy_id": self.strategy_id,
            "status": self.status,
            "divergence_score": self.divergence_score,
            "actions": list(self.actions),
            "details": dict(self.details),
        }


@dataclass
class SubordinateGovernanceState:
    """State tracking for an individual subordinate strategy."""

    pattern: str
    strategy_id: str
    status: str = "pending"
    suspended: bool = False
    divergence_score: float = 0.0
    divergence_history: list[Dict[str, Any]] = field(default_factory=list)
    escalation_count: int = 0
    consecutive_drift: int = 0
    resequenced: bool = False
    last_event: str | None = None

    def to_dashboard(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "status": self.status,
            "suspended": self.suspended,
            "divergence_score": round(self.divergence_score, 3),
            "divergence_events": list(self.divergence_history),
            "escalations": self.escalation_count,
            "consecutive_drift": self.consecutive_drift,
            "resequenced": self.resequenced,
            "last_event": self.last_event,
        }


class MetaStrategyGovernor:
    """Supervise active strategies for compliance with approved meta-strategies."""

    def __init__(
        self,
        root: Path | str = Path("integration"),
        *,
        storage: MetaStrategyStorage | None = None,
        default_tolerance: float = 0.25,
        escalation_threshold: int = 2,
    ) -> None:
        self._root = Path(root)
        self._log_path = self._root / "governance_log.jsonl"
        self._storage = storage or MetaStrategyStorage(self._root / "meta_strategies")
        self._lock = threading.RLock()
        self._enabled = True
        self._default_tolerance = max(0.05, min(0.9, float(default_tolerance)))
        self._global_escalation_threshold = max(1, int(escalation_threshold))
        self._meta_registry: MutableMapping[str, CodexMetaStrategy] = {}
        self._assignments: MutableMapping[str, str] = {}
        self._subordinates: MutableMapping[str, SubordinateGovernanceState] = {}
        self._tolerances: MutableMapping[str, float] = {}
        self._escalation_thresholds: MutableMapping[str, int] = {}
        self._recent_events: list[Dict[str, Any]] = []
        self._anomalies: list[Dict[str, Any]] = []
        self._load_existing_meta()

    # ------------------------------------------------------------------
    # Public controls
    def enable_governance(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)
            self._record_event(
                "governance_toggled",
                pattern="*",
                strategy_id="*",
                payload={"enabled": self._enabled},
                impact="baseline",
                confidence=0.6,
            )

    def set_tolerance(self, pattern: str | None, value: float) -> None:
        clamped = max(0.05, min(0.9, float(value)))
        with self._lock:
            if pattern:
                self._tolerances[pattern] = clamped
            else:
                self._default_tolerance = clamped
            self._record_event(
                "governance_tolerance",
                pattern=pattern or "*",
                strategy_id="*",
                payload={"tolerance": clamped},
                impact="baseline",
                confidence=0.6,
            )

    def set_escalation_threshold(self, pattern: str | None, threshold: int) -> None:
        value = max(1, int(threshold))
        with self._lock:
            if pattern:
                self._escalation_thresholds[pattern] = value
            else:
                self._global_escalation_threshold = value
            self._record_event(
                "governance_escalation_threshold",
                pattern=pattern or "*",
                strategy_id="*",
                payload={"threshold": value},
                impact="baseline",
                confidence=0.6,
            )

    # ------------------------------------------------------------------
    # Meta-strategy registry
    def register_meta_strategy(self, strategy: CodexMetaStrategy) -> None:
        with self._lock:
            self._meta_registry[strategy.pattern] = strategy
            tolerance = strategy.metadata.get("tolerance")
            if tolerance is not None:
                try:
                    self._tolerances[strategy.pattern] = max(0.05, min(0.9, float(tolerance)))
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    pass
            threshold = strategy.metadata.get("escalation_threshold")
            if threshold is not None:
                try:
                    self._escalation_thresholds[strategy.pattern] = max(1, int(threshold))
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    pass
            self._record_event(
                "meta_strategy_registered",
                pattern=strategy.pattern,
                strategy_id="*",
                payload={"metadata": dict(strategy.metadata)},
                impact="baseline",
                confidence=float(strategy.metadata.get("confidence", 0.6) or 0.6),
            )

    def unregister_meta_strategy(self, pattern: str) -> None:
        with self._lock:
            if pattern in self._meta_registry:
                self._meta_registry.pop(pattern)
                self._tolerances.pop(pattern, None)
                self._escalation_thresholds.pop(pattern, None)
                self._record_event(
                    "meta_strategy_unregistered",
                    pattern=pattern,
                    strategy_id="*",
                    payload={},
                    impact="baseline",
                    confidence=0.5,
                )

    # ------------------------------------------------------------------
    def observe(self, strategy: "CodexStrategy", *, pattern: str | None = None, reason: str = "update") -> GovernanceDecision | None:
        with self._lock:
            if not self._enabled:
                return None
            resolved_pattern = self._resolve_pattern(strategy, pattern)
            if resolved_pattern is None:
                return None
            meta = self._ensure_meta(resolved_pattern)
            if meta is None:
                return None
            state = self._subordinates.setdefault(
                strategy.strategy_id,
                SubordinateGovernanceState(pattern=resolved_pattern, strategy_id=strategy.strategy_id),
            )
            self._assignments[strategy.strategy_id] = resolved_pattern
            decision = self._evaluate_locked(strategy, meta, state, reason=reason)
            return decision

    def release(self, strategy_id: str) -> None:
        with self._lock:
            if strategy_id in self._subordinates:
                state = self._subordinates.pop(strategy_id)
                pattern = state.pattern
            else:
                pattern = self._assignments.get(strategy_id)
            self._assignments.pop(strategy_id, None)
            if pattern:
                self._record_event(
                    "strategy_released",
                    pattern=pattern,
                    strategy_id=strategy_id,
                    payload={},
                    impact="baseline",
                    confidence=0.55,
                )

    # ------------------------------------------------------------------
    def merge_subordinates(self, pattern: str, strategy_ids: Sequence[str]) -> GovernanceDecision:
        with self._lock:
            meta = self._ensure_meta(pattern)
            merged_ids = [sid for sid in strategy_ids if self._assignments.get(sid) == pattern]
            payload = {"merged_strategies": merged_ids}
            decision = GovernanceDecision(
                pattern=pattern,
                strategy_id=",".join(sorted(merged_ids)) or "*",
                status="merged",
                divergence_score=0.0,
                actions=["merge"],
                details=payload,
            )
            self._record_event(
                "strategies_merged",
                pattern=pattern,
                strategy_id=decision.strategy_id,
                payload=payload,
                impact="baseline",
                confidence=float(meta.metadata.get("confidence", 0.6) or 0.6),
            )
            return decision

    def operator_override(
        self,
        pattern: str,
        strategy_id: str,
        *,
        operator: str,
        approve: bool,
        rationale: str | None = None,
    ) -> SubordinateGovernanceState:
        with self._lock:
            state = self._subordinates.get(strategy_id)
            if state is None:
                raise KeyError(strategy_id)
            if state.pattern != pattern:
                raise ValueError("Strategy is not governed by the supplied meta-strategy")

            if approve:
                state.status = "escalation_approved"
                state.suspended = True
                state.escalation_count += 1
                state.consecutive_drift = 0
                adjustment = -0.05
                impact = "warning"
                decision = "approve_escalation"
            else:
                state.status = "override"
                state.suspended = False
                state.resequenced = False
                state.divergence_score = 0.0
                state.consecutive_drift = 0
                adjustment = 0.05
                impact = "baseline"
                decision = "override_dismissed"

            tolerance = self._adjust_tolerance(pattern, adjustment)
            state.last_event = _timestamp()
            payload = {
                "operator": operator,
                "approve": approve,
                "rationale": rationale,
                "tolerance": tolerance,
            }
            self._record_event(
                "governance_override",
                pattern=pattern,
                strategy_id=strategy_id,
                payload=payload,
                impact=impact,
                confidence=0.7,
            )
            return state

    # ------------------------------------------------------------------
    # Reporting
    def dashboard_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            meta_rows: list[Dict[str, Any]] = []
            for pattern, meta in self._meta_registry.items():
                states = [state for state in self._subordinates.values() if state.pattern == pattern]
                meta_rows.append(
                    {
                        "pattern": pattern,
                        "tolerance": round(self._tolerances.get(pattern, self._default_tolerance), 3),
                        "escalation_threshold": self._escalation_thresholds.get(pattern, self._global_escalation_threshold),
                        "supervising": [state.to_dashboard() for state in states],
                        "divergence_flags": sum(1 for state in states if state.status in {"suspended", "escalated"}),
                        "metadata": dict(meta.metadata),
                    }
                )
            return {
                "enabled": self._enabled,
                "default_tolerance": round(self._default_tolerance, 3),
                "meta_strategies": meta_rows,
                "operator_controls": {
                    "actions": [
                        "enable",
                        "disable",
                        "set_tolerance",
                        "approve_escalation",
                        "override_escalation",
                    ],
                    "tolerance_bounds": [0.05, 0.9],
                },
                "recent_events": list(self._recent_events[-10:]),
            }

    def anomalies(self) -> list[Dict[str, Any]]:
        with self._lock:
            return list(self._anomalies)

    def recent_events(self) -> list[Dict[str, Any]]:
        with self._lock:
            return list(self._recent_events)

    def state_for(self, strategy_id: str) -> SubordinateGovernanceState | None:
        with self._lock:
            return self._subordinates.get(strategy_id)

    def tolerance_for(self, pattern: str) -> float:
        with self._lock:
            return self._tolerances.get(pattern, self._default_tolerance)

    # ------------------------------------------------------------------
    # Internal helpers
    def _load_existing_meta(self) -> None:
        try:
            stored = self._storage.list_all()
        except Exception:  # pragma: no cover - defensive
            stored = {}
        for meta in stored.values():
            if meta.metadata.get("status") == "approved" or meta.metadata.get("status") is None:
                self.register_meta_strategy(meta)

    def _resolve_pattern(self, strategy: "CodexStrategy", pattern: str | None) -> str | None:
        if pattern:
            return pattern
        meta_hint = strategy.metadata.get("meta_strategy") if isinstance(strategy.metadata, Mapping) else None
        if isinstance(meta_hint, str) and meta_hint.strip():
            return meta_hint
        governed = strategy.metadata.get("governed_by") if isinstance(strategy.metadata, Mapping) else None
        if isinstance(governed, str) and governed.strip():
            return governed
        return self._assignments.get(strategy.strategy_id)

    def _ensure_meta(self, pattern: str) -> CodexMetaStrategy | None:
        meta = self._meta_registry.get(pattern)
        if meta is not None:
            return meta
        try:
            meta = self._storage.load(pattern)
        except KeyError:
            return None
        self._meta_registry[pattern] = meta
        return meta

    def _expected_steps(self, meta: CodexMetaStrategy) -> list[str]:
        abstraction = meta.abstraction or {}
        steps = abstraction.get("step_order") or []
        if isinstance(steps, Sequence) and not isinstance(steps, (str, bytes, bytearray)):
            return [str(item).strip().lower() for item in steps if str(item).strip()]
        return _normalize_sequence([steps])

    def _strategy_steps(self, strategy: "CodexStrategy") -> list[str]:
        steps: list[str] = []
        for plan in getattr(strategy, "plan_chain", []):
            title = getattr(plan, "title", None)
            if title:
                text = str(title).strip().lower()
                if text:
                    steps.append(text)
        return steps

    def _expected_escalation(self, meta: CodexMetaStrategy) -> list[str]:
        metadata = meta.metadata or {}
        abstraction = meta.abstraction or {}
        params = abstraction.get("parameters") if isinstance(abstraction, Mapping) else {}
        hints: list[str] = []
        if metadata.get("escalation_path"):
            hints.extend(_normalize_sequence(metadata["escalation_path"]))
        if metadata.get("escalation"):
            hints.extend(_normalize_sequence(metadata["escalation"]))
        if isinstance(params, Mapping):
            if params.get("escalation_path"):
                hints.extend(_normalize_sequence(params["escalation_path"]))
            if params.get("escalation"):
                hints.extend(_normalize_sequence(params["escalation"]))
        unique: list[str] = []
        for hint in hints:
            if hint not in unique:
                unique.append(hint)
        return unique

    def _strategy_escalation(self, strategy: "CodexStrategy") -> list[str]:
        metadata = getattr(strategy, "metadata", {}) or {}
        escalation = []
        if isinstance(metadata, Mapping):
            if metadata.get("escalation_path"):
                escalation.extend(_normalize_sequence(metadata["escalation_path"]))
            if metadata.get("escalation"):
                escalation.extend(_normalize_sequence(metadata["escalation"]))
        conditions = getattr(strategy, "conditions", {})
        if isinstance(conditions, Mapping):
            escalation.extend(_normalize_sequence(conditions.values()))
        unique: list[str] = []
        for step in escalation:
            if step not in unique:
                unique.append(step)
        return unique

    def _divergence_from_steps(
        self,
        expected: list[str],
        actual: list[str],
    ) -> tuple[float, list[Dict[str, Any]], bool]:
        mismatches: list[Dict[str, Any]] = []
        resequence_possible = False
        for index, (exp, act) in enumerate(zip_longest(expected, actual, fillvalue=None)):
            if exp == act:
                continue
            mismatches.append({"index": index, "expected": exp, "actual": act})
        missing = max(0, len(expected) - len(actual))
        divergence = (len(mismatches) + missing) / max(1, len(expected))
        if mismatches:
            resequence_possible = (
                len(expected) == len(actual)
                and sorted(expected) == sorted(actual)
                and len(expected) > 0
            )
        return divergence, mismatches, resequence_possible

    def _divergence_from_escalation(
        self,
        expected: list[str],
        actual: list[str],
    ) -> tuple[float, list[str]]:
        if not expected:
            return 0.0, []
        missing = [step for step in expected if step not in actual]
        divergence = len(missing) / max(1, len(expected))
        return divergence, missing

    def _evaluate_locked(
        self,
        strategy: "CodexStrategy",
        meta: CodexMetaStrategy,
        state: SubordinateGovernanceState,
        *,
        reason: str,
    ) -> GovernanceDecision:
        expected_steps = self._expected_steps(meta)
        actual_steps = self._strategy_steps(strategy)
        step_divergence, mismatches, resequence_possible = self._divergence_from_steps(expected_steps, actual_steps)
        expected_escalation = self._expected_escalation(meta)
        actual_escalation = self._strategy_escalation(strategy)
        escalation_divergence, missing_escalation = self._divergence_from_escalation(
            expected_escalation,
            actual_escalation,
        )
        divergence_score = max(step_divergence, escalation_divergence)
        tolerance = self._tolerances.get(state.pattern, self._default_tolerance)
        threshold = self._escalation_thresholds.get(state.pattern, self._global_escalation_threshold)

        details = {
            "step_mismatches": mismatches,
            "missing_escalation": missing_escalation,
            "tolerance": tolerance,
            "reason": reason,
        }

        actions: list[str] = []
        if divergence_score <= tolerance:
            state.status = "aligned"
            state.suspended = False
            state.resequenced = False
            state.consecutive_drift = 0
            state.divergence_score = divergence_score
            state.last_event = _timestamp()
            self._record_event(
                "governance_alignment",
                pattern=state.pattern,
                strategy_id=strategy.strategy_id,
                payload={"divergence": divergence_score, "reason": reason},
                impact="baseline",
                confidence=0.7,
            )
        elif resequence_possible:
            state.status = "resequence"
            state.suspended = False
            state.resequenced = True
            state.consecutive_drift = 0
            state.divergence_score = divergence_score
            state.last_event = _timestamp()
            actions.append("resequence")
            details["resequenced"] = True
            self._record_event(
                "governance_resequence",
                pattern=state.pattern,
                strategy_id=strategy.strategy_id,
                payload={"divergence": divergence_score, "reason": reason},
                impact="baseline",
                confidence=0.65,
            )
        else:
            state.suspended = True
            state.status = "suspended"
            state.resequenced = False
            state.consecutive_drift += 1
            state.divergence_score = divergence_score
            state.last_event = _timestamp()
            record = {
                "timestamp": state.last_event,
                "divergence": round(divergence_score, 3),
                "step_mismatches": mismatches,
                "missing_escalation": missing_escalation,
            }
            state.divergence_history.append(record)
            impact = "warning" if divergence_score < 0.75 else "critical"
            self._record_event(
                "governance_divergence",
                pattern=state.pattern,
                strategy_id=strategy.strategy_id,
                payload={
                    "divergence": divergence_score,
                    "consecutive": state.consecutive_drift,
                    "reason": reason,
                },
                impact=impact,
                confidence=0.75,
            )
            anomaly = {
                "pattern": state.pattern,
                "strategy_id": strategy.strategy_id,
                "divergence": round(divergence_score, 3),
                "impact": impact,
                "timestamp": state.last_event,
            }
            self._anomalies.append(anomaly)
            if state.consecutive_drift >= threshold:
                state.status = "escalated"
                state.escalation_count += 1
                actions.append("escalate")
                self._record_event(
                    "governance_escalation",
                    pattern=state.pattern,
                    strategy_id=strategy.strategy_id,
                    payload={
                        "divergence": divergence_score,
                        "threshold": threshold,
                        "reason": reason,
                    },
                    impact="warning",
                    confidence=0.8,
                )

        decision = GovernanceDecision(
            pattern=state.pattern,
            strategy_id=strategy.strategy_id,
            status=state.status,
            divergence_score=divergence_score,
            actions=actions,
            details=details,
        )
        return decision

    def _adjust_tolerance(self, pattern: str, delta: float) -> float:
        tolerance = self._tolerances.get(pattern, self._default_tolerance)
        tolerance = max(0.05, min(0.9, tolerance + delta))
        self._tolerances[pattern] = tolerance
        return tolerance

    def _record_event(
        self,
        event: str,
        *,
        pattern: str,
        strategy_id: str,
        payload: Mapping[str, Any],
        impact: str,
        confidence: float,
    ) -> None:
        record = {
            "timestamp": _timestamp(),
            "event": event,
            "pattern": pattern,
            "strategy_id": strategy_id,
            "payload": dict(payload),
            "impact": impact,
            "confidence": confidence,
        }
        self._recent_events.append(record)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        integration_memory.record_event(
            f"governance.{event}",
            source=pattern,
            impact=impact,
            confidence=confidence,
            payload={
                "strategy_id": strategy_id,
                "details": dict(payload),
            },
        )

