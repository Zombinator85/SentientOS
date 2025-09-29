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
from .meta_strategies import CodexMetaStrategy, PatternMiningEngine

__all__ = [
    "CodexStrategy",
    "OutcomeEntry",
    "StrategyAdjustmentEngine",
    "StrategyBranch",
    "StrategyLedger",
    "StrategyPlan",
    "StrategyStorage",
    "strategy_engine",
    "configure_strategy_root",
]


_DEFAULT_OUTCOME_STATUS = {"success", "failure", "rollback", "override"}
_DEFAULT_STRATEGY_STATUS = {"proposed", "active", "checkpoint", "completed", "rolled_back"}


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
        self._lock = threading.RLock()

    def log(self, entry: OutcomeEntry) -> Path:
        path = self._base_dir / f"{entry.plan_id}.jsonl"
        line = json.dumps(entry.to_dict(), sort_keys=True)
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return path


@dataclass
class StrategyBranch:
    """Conditional branch mapping for a strategy checkpoint."""

    condition: str
    next_plan: str | None
    label: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition": self.condition,
            "next_plan": self.next_plan,
            "label": self.label,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyBranch":
        return cls(
            condition=str(payload.get("condition", "default")),
            next_plan=payload.get("next_plan"),
            label=payload.get("label"),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass
class StrategyPlan:
    """Plan segment within a multi-cycle Codex strategy."""

    plan_id: str
    title: str
    checkpoint: bool = True
    branches: list[StrategyBranch] = field(default_factory=list)
    status: str = "pending"
    ledger_confirmed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "title": self.title,
            "checkpoint": self.checkpoint,
            "branches": [branch.to_dict() for branch in self.branches],
            "status": self.status,
            "ledger_confirmed": self.ledger_confirmed,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyPlan":
        return cls(
            plan_id=str(payload.get("plan_id")),
            title=str(payload.get("title", "")),
            checkpoint=bool(payload.get("checkpoint", True)),
            branches=[StrategyBranch.from_dict(branch) for branch in payload.get("branches", [])],
            status=str(payload.get("status", "pending")),
            ledger_confirmed=bool(payload.get("ledger_confirmed", False)),
        )


@dataclass
class CodexStrategy:
    """Structured, multi-cycle strategy arc with conditional branching."""

    strategy_id: str
    goal: str
    plan_chain: list[StrategyPlan]
    conditions: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "proposed"
    current_plan_index: int = 0
    history: list[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in _DEFAULT_STRATEGY_STATUS:
            self.status = "proposed"
        if not self.plan_chain:
            raise ValueError("CodexStrategy requires at least one plan in the chain")
        self.current_plan_index = max(0, min(self.current_plan_index, len(self.plan_chain) - 1))

    @property
    def current_plan(self) -> StrategyPlan:
        return self.plan_chain[self.current_plan_index]

    def add_history(self, action: str, operator: str | None, details: Mapping[str, Any] | None = None) -> None:
        entry = {
            "timestamp": _serialize_timestamp(),
            "action": action,
            "operator": operator,
            "status": self.status,
        }
        if details:
            entry.update({"details": dict(details)})
        self.history.append(entry)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "goal": self.goal,
            "plan_chain": [plan.to_dict() for plan in self.plan_chain],
            "conditions": dict(self.conditions),
            "metadata": dict(self.metadata),
            "status": self.status,
            "current_plan_index": self.current_plan_index,
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CodexStrategy":
        return cls(
            strategy_id=str(payload.get("strategy_id")),
            goal=str(payload.get("goal", "")),
            plan_chain=[StrategyPlan.from_dict(item) for item in payload.get("plan_chain", [])],
            conditions=dict(payload.get("conditions", {})),
            metadata=dict(payload.get("metadata", {})),
            status=str(payload.get("status", "proposed")),
            current_plan_index=int(payload.get("current_plan_index", 0)),
            history=list(payload.get("history", [])),
        )

    def activate(self, operator: str | None = None) -> None:
        if self.status != "proposed":
            return
        self.status = "active"
        self.current_plan.status = "active"
        self.add_history("activated", operator)

    def mark_checkpoint(self, operator: str | None = None) -> None:
        self.status = "checkpoint"
        self.current_plan.status = "completed"
        self.add_history("checkpoint", operator)

    def pause(self, operator: str | None = None) -> None:
        self.metadata["paused"] = True
        self.add_history("paused", operator)

    def resume(self, operator: str | None = None) -> None:
        if self.metadata.pop("paused", False):
            self.add_history("resumed", operator)

    def set_ledger_confirmed(self) -> None:
        self.current_plan.ledger_confirmed = True

    def complete(self, operator: str | None = None) -> None:
        self.status = "completed"
        self.add_history("completed", operator)

    def rollback(self, operator: str | None = None) -> None:
        self.status = "rolled_back"
        self.add_history("rolled_back", operator)

    def advance_to_plan(self, plan_id: str, operator: str | None = None) -> None:
        for index, plan in enumerate(self.plan_chain):
            if plan.plan_id == plan_id:
                self.current_plan_index = index
                plan.status = "active"
                self.status = "active"
                self.add_history("advanced", operator, {"plan_id": plan_id})
                return
        raise KeyError(f"Plan {plan_id} not found in strategy {self.strategy_id}")


class StrategyLedger:
    """Ledger gate for strategy checkpoints and branches."""

    def confirm_checkpoint(self, strategy: CodexStrategy, plan: StrategyPlan) -> bool:  # pragma: no cover - interface default
        return True

    def confirm_branch(
        self,
        strategy: CodexStrategy,
        plan: StrategyPlan,
        branch: StrategyBranch,
    ) -> bool:  # pragma: no cover - interface default
        return True


class StrategyStorage:
    """Persist Codex strategies to /integration/strategies."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def path_for(self, strategy_id: str) -> Path:
        return self._root / f"{strategy_id}.json"

    def save(self, strategy: CodexStrategy) -> Path:
        data = json.dumps(strategy.to_dict(), indent=2, sort_keys=True)
        path = self.path_for(strategy.strategy_id)
        with self._lock:
            path.write_text(data, encoding="utf-8")
        return path

    def load(self, strategy_id: str) -> CodexStrategy:
        path = self.path_for(strategy_id)
        if not path.exists():
            raise KeyError(f"Strategy {strategy_id} is not stored")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CodexStrategy.from_dict(payload)

    def list_all(self) -> Dict[str, CodexStrategy]:
        strategies: Dict[str, CodexStrategy] = {}
        for file in self._root.glob("*.json"):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            try:
                strategy = CodexStrategy.from_dict(payload)
            except (ValueError, KeyError):
                continue
            strategies[strategy.strategy_id] = strategy
        return strategies


class StrategyAdjustmentEngine:
    """Manage adaptive strategy adjustments based on plan outcomes."""

    def __init__(self, root: Path | str = Path("integration"), *, override_threshold: int = 3) -> None:
        self._root = Path(root)
        self._override_threshold = max(1, int(override_threshold))
        self._lock = threading.RLock()
        self._logger = _OutcomeLogger(self._root / "outcomes")
        self._strategy_log_path = self._root / "strategy_log.jsonl"
        self._state_path = self._root / "strategy_state.json"
        self._strategy_storage = StrategyStorage(self._root / "strategies")
        self._meta_strategy_engine = PatternMiningEngine(self._root)
        self._weights = PriorityWeights().normalized()
        self._version = 1
        self._locked = False
        self._metrics: MutableMapping[str, float] = defaultdict(float)
        self._action_success: Counter[str] = Counter()
        self._action_rollbacks: Counter[str] = Counter()
        self._sequence_counts: Counter[tuple[str, str]] = Counter()
        self._preferred_sequences: Dict[tuple[str, str], int] = {}
        self._strategies: Dict[str, CodexStrategy] = self._strategy_storage.list_all()
        self._branch_usage: Counter[str] = Counter()
        self._strategy_ledger: StrategyLedger = StrategyLedger()
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

    def meta_strategy_engine(self) -> PatternMiningEngine:
        return self._meta_strategy_engine

    def set_strategy_ledger(self, ledger: StrategyLedger) -> None:
        with self._lock:
            self._strategy_ledger = ledger

    # ------------------------------------------------------------------
    # Meta-strategy management
    def propose_meta_strategies(self, arcs: Sequence[Mapping[str, Any]]) -> Sequence[CodexMetaStrategy]:
        proposals = self._meta_strategy_engine.analyze(arcs)
        for meta in proposals:
            integration_memory.record_event(
                "strategy.meta_strategy.proposed",
                source=meta.pattern,
                impact="baseline",
                confidence=float(meta.metadata.get("confidence", 0.6) or 0.6),
                payload=meta.to_dict(),
            )
        return proposals

    def meta_strategy_dashboard(self) -> list[Dict[str, Any]]:
        return list(self._meta_strategy_engine.dashboard_payload())

    def approve_meta_strategy(self, pattern: str, *, operator: str | None = None) -> CodexMetaStrategy:
        strategy = self._meta_strategy_engine.approve(pattern, operator=operator)
        integration_memory.record_event(
            "strategy.meta_strategy.approved",
            source=strategy.pattern,
            impact="baseline",
            confidence=float(strategy.metadata.get("confidence", 0.6) or 0.6),
            payload={"operator": operator, "meta_strategy": strategy.to_dict()},
        )
        return strategy

    def reject_meta_strategy(self, pattern: str, *, operator: str | None = None) -> None:
        self._meta_strategy_engine.reject(pattern, operator=operator)
        integration_memory.record_event(
            "strategy.meta_strategy.rejected",
            source=pattern,
            impact="baseline",
            confidence=0.5,
            payload={"operator": operator},
        )

    def apply_meta_strategy(
        self,
        pattern: str,
        *,
        outcome: str,
        context: Mapping[str, Any] | None = None,
    ) -> str:
        message = self._meta_strategy_engine.applied_message(pattern)
        self._meta_strategy_engine.record_application(pattern, outcome=outcome, context=context)
        stored = self._meta_strategy_engine.get(pattern)
        confidence = 0.6
        if stored is not None:
            try:
                confidence = float(stored.metadata.get("confidence", 0.6) or 0.6)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                confidence = 0.6
        impact = "baseline" if outcome in {"success", "completed"} else "failed"
        payload = {"message": message, "outcome": outcome}
        if context:
            payload["context"] = dict(context)
        integration_memory.record_event(
            "strategy.meta_strategy.applied",
            source=pattern,
            impact=impact,
            confidence=confidence,
            payload=payload,
        )
        return message

    # ------------------------------------------------------------------
    # Strategy arc management
    def list_strategies(self) -> Sequence[CodexStrategy]:
        with self._lock:
            return list(self._strategies.values())

    def register_strategy(self, strategy: CodexStrategy, *, operator: str | None = None) -> CodexStrategy:
        with self._lock:
            self._strategies[strategy.strategy_id] = strategy
            self._strategy_storage.save(strategy)
            payload = {"goal": strategy.goal, "horizon": strategy.metadata.get("horizon")}
        self._log_strategy_event("strategy_registered", strategy, operator, payload)
        return strategy

    def load_strategy(self, strategy_id: str) -> CodexStrategy:
        with self._lock:
            if strategy_id not in self._strategies:
                strategy = self._strategy_storage.load(strategy_id)
                self._strategies[strategy.strategy_id] = strategy
            return self._strategies[strategy_id]

    def activate_strategy(self, strategy_id: str, *, operator: str | None = None) -> CodexStrategy:
        with self._lock:
            strategy = self.load_strategy(strategy_id)
            strategy.activate(operator)
            self._strategy_storage.save(strategy)
            payload = {"plan": strategy.current_plan.plan_id}
        self._log_strategy_event("strategy_activated", strategy, operator, payload)
        return strategy

    def checkpoint_strategy(self, strategy_id: str, *, operator: str | None = None) -> CodexStrategy:
        with self._lock:
            strategy = self.load_strategy(strategy_id)
            plan = strategy.current_plan
            if not plan.checkpoint:
                return strategy
            if not self._strategy_ledger.confirm_checkpoint(strategy, plan):
                raise PermissionError("Strategy checkpoint not confirmed by ledger")
            strategy.mark_checkpoint(operator)
            strategy.set_ledger_confirmed()
            self._strategy_storage.save(strategy)
            payload = {"plan": plan.plan_id, "title": plan.title}
        self._log_strategy_event("strategy_checkpoint", strategy, operator, payload)
        return strategy

    def advance_strategy(
        self,
        strategy_id: str,
        condition_key: str,
        *,
        operator: str | None = None,
        condition_payload: Mapping[str, Any] | None = None,
    ) -> CodexStrategy:
        with self._lock:
            strategy = self.load_strategy(strategy_id)
            if strategy.status != "checkpoint":
                raise RuntimeError("Strategy must be at a checkpoint before advancing")
            plan = strategy.current_plan
            matched_branch: StrategyBranch | None = None
            for branch in plan.branches:
                if branch.condition == condition_key:
                    matched_branch = branch
                    break
            if matched_branch is None:
                for branch in plan.branches:
                    if branch.condition in {"default", "*"}:
                        matched_branch = branch
                        break
            if matched_branch is None:
                raise KeyError(f"No branch matching condition {condition_key}")
            if not self._strategy_ledger.confirm_branch(strategy, plan, matched_branch):
                raise PermissionError("Strategy branch not confirmed by ledger")
            self._branch_usage[matched_branch.condition] += 1
            next_plan = matched_branch.next_plan
            if next_plan:
                strategy.advance_to_plan(next_plan, operator)
            else:
                strategy.complete(operator)
            strategy.metadata.setdefault("last_condition", condition_key)
            if condition_payload:
                strategy.metadata.setdefault("condition_log", []).append(dict(condition_payload))
            adjust = self._maybe_adjust_strategy_horizon(strategy, matched_branch.condition)
            self._strategy_storage.save(strategy)
            payload = {
                "from_plan": plan.plan_id,
                "branch": matched_branch.condition,
                "next_plan": next_plan,
            }
        self._log_strategy_event("strategy_advanced", strategy, operator, payload)
        if adjust is not None:
            self._log_strategy_event("strategy_horizon_adjusted", strategy, operator=None, extra=adjust)
        return strategy

    def pause_strategy(self, strategy_id: str, *, operator: str | None = None) -> CodexStrategy:
        with self._lock:
            strategy = self.load_strategy(strategy_id)
            strategy.pause(operator)
            self._strategy_storage.save(strategy)
        self._log_strategy_event("strategy_paused", strategy, operator, {})
        return strategy

    def resume_strategy(self, strategy_id: str, *, operator: str | None = None) -> CodexStrategy:
        with self._lock:
            strategy = self.load_strategy(strategy_id)
            strategy.resume(operator)
            self._strategy_storage.save(strategy)
        self._log_strategy_event("strategy_resumed", strategy, operator, {})
        return strategy

    def terminate_strategy(
        self,
        strategy_id: str,
        *,
        operator: str | None = None,
        rolled_back: bool = True,
    ) -> CodexStrategy:
        with self._lock:
            strategy = self.load_strategy(strategy_id)
            if rolled_back:
                strategy.rollback(operator)
            else:
                strategy.complete(operator)
            self._strategy_storage.save(strategy)
            payload = {"rolled_back": rolled_back}
        self._log_strategy_event("strategy_terminated", strategy, operator, payload)
        return strategy

    # ------------------------------------------------------------------
    def reconfigure(self, root: Path | str) -> None:
        with self._lock:
            self._root = Path(root)
            self._logger = _OutcomeLogger(self._root / "outcomes")
            self._strategy_log_path = self._root / "strategy_log.jsonl"
            self._state_path = self._root / "strategy_state.json"
            self._strategy_storage = StrategyStorage(self._root / "strategies")
            self._version = 1
            self._locked = False
            self._metrics = defaultdict(float)
            self._action_success = Counter()
            self._action_rollbacks = Counter()
            self._sequence_counts = Counter()
            self._preferred_sequences = {}
            self._strategies = self._strategy_storage.list_all()
            self._branch_usage = Counter()
            self._strategy_ledger = StrategyLedger()
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
        self._branch_usage = Counter(payload.get("branch_usage", {}))
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
        threshold = payload.get("meta_strategy_threshold")
        if threshold is not None:
            try:
                self._meta_strategy_engine.set_threshold(float(threshold))
            except (TypeError, ValueError):  # pragma: no cover - defensive
                pass

    def _persist_state(self) -> None:
        data = {
            "weights": self.weights_dict(),
            "version": self._version,
            "locked": self._locked,
            "metrics": dict(self._metrics),
            "action_success": dict(self._action_success),
            "action_rollbacks": dict(self._action_rollbacks),
            "branch_usage": dict(self._branch_usage),
            "sequence_counts": {
                f"{start}→{follow}": count for (start, follow), count in self._sequence_counts.items()
            },
            "preferred_sequences": {
                f"{start}→{follow}": count for (start, follow), count in self._preferred_sequences.items()
            },
            "meta_strategy_threshold": self._meta_strategy_engine.confidence_threshold,
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

    def _log_strategy_event(
        self,
        action: str,
        strategy: CodexStrategy,
        operator: str | None,
        extra: Mapping[str, Any],
    ) -> None:
        payload = {
            "strategy_id": strategy.strategy_id,
            "goal": strategy.goal,
            "status": strategy.status,
            "operator": operator,
            "horizon": strategy.metadata.get("horizon"),
            "confidence": strategy.metadata.get("confidence"),
            "current_plan": strategy.current_plan.plan_id if strategy.plan_chain else None,
        }
        payload.update(dict(extra))
        self._append_strategy_log(action, payload)
        impact = "failed" if strategy.status == "rolled_back" else "baseline"
        integration_memory.record_event(
            "strategy.event",
            source=strategy.strategy_id,
            impact=impact,
            confidence=float(strategy.metadata.get("confidence", 0.6) or 0.6),
            payload=payload,
        )

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

    def _maybe_adjust_strategy_horizon(
        self, strategy: CodexStrategy, condition: str
    ) -> Mapping[str, Any] | None:
        horizon_value = strategy.metadata.get("horizon")
        if horizon_value is None:
            return None
        try:
            horizon = int(horizon_value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None
        usage = self._branch_usage.get(condition, 0)
        if usage >= 2 and horizon > 1:
            new_horizon = max(1, horizon - 1)
            if new_horizon != horizon:
                strategy.metadata["horizon"] = new_horizon
                return {"condition": condition, "previous": horizon, "updated": new_horizon}
        return None


strategy_engine = StrategyAdjustmentEngine()


def configure_strategy_root(path: Path | str) -> StrategyAdjustmentEngine:
    strategy_engine.reconfigure(path)
    return strategy_engine

