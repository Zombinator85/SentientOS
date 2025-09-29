"""Strategy orchestration and conflict management for Codex."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

from .strategy import CodexStrategy

__all__ = ["StrategyOrchestrator", "StrategyConflict", "ActiveStrategyRecord"]


def _as_set(payload: Mapping[str, Any], *keys: str) -> set[str]:
    resources: set[str] = set()
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            resources.add(value)
        elif isinstance(value, Sequence):
            for item in value:
                if isinstance(item, str):
                    resources.add(item)
    return resources


def _normalize_priority(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        mapping = {
            "critical": 1.0,
            "high": 0.85,
            "medium": 0.6,
            "low": 0.3,
        }
        if text in mapping:
            return mapping[text]
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _normalize_horizon(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        mapping = {
            "immediate": 0.0,
            "short": 1.0,
            "medium": 4.0,
            "long": 8.0,
        }
        if text in mapping:
            return mapping[text]
        try:
            return float(text)
        except ValueError:
            return None
    return None


@dataclass
class ActiveStrategyRecord:
    """Projection of an active strategy for orchestration."""

    strategy_id: str
    goal: str
    status: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    resources: set[str] = field(default_factory=set)
    horizon: float | None = None
    priority: float | None = None

    @classmethod
    def from_strategy(cls, strategy: CodexStrategy) -> "ActiveStrategyRecord":
        metadata = dict(strategy.metadata)
        resources = _as_set(
            metadata,
            "channels",
            "resources",
            "targets",
            "daemons",
            "embodiment_channels",
        )
        # fallback to goal key hints
        if not resources:
            hints = metadata.get("resource_hints")
            if isinstance(hints, Mapping):
                resources = _as_set(hints, *hints.keys())
        horizon = _normalize_horizon(metadata.get("horizon"))
        priority = _normalize_priority(metadata.get("priority"))
        return cls(
            strategy_id=strategy.strategy_id,
            goal=strategy.goal,
            status=strategy.status,
            metadata=metadata,
            resources=resources,
            horizon=horizon,
            priority=priority,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "goal": self.goal,
            "status": self.status,
            "metadata": dict(self.metadata),
            "resources": sorted(self.resources),
            "horizon": self.horizon,
            "priority": self.priority,
        }


@dataclass
class StrategyConflict:
    """Conflict detected between active strategies."""

    conflict_id: str
    strategies: tuple[str, str]
    classes: tuple[str, ...]
    proposed_resolution: str
    resolution: str
    status: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "strategies": list(self.strategies),
            "classes": list(self.classes),
            "proposed_resolution": self.proposed_resolution,
            "resolution": self.resolution,
            "status": self.status,
            "metadata": dict(self.metadata),
        }


class StrategyOrchestrator:
    """Coordinate multiple active Codex strategies."""

    HORIZON_THRESHOLD = 2.5
    PRIORITY_THRESHOLD = 0.35

    def __init__(self, root: Path | str = Path("integration")) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._active_path = self._root / "strategies" / "active.jsonl"
        self._log_path = self._root / "orchestration_log.jsonl"
        self._state_path = self._root / "orchestration_state.json"
        pulse_root = self._root.parent / "pulse"
        self._conflicts_dir = pulse_root / "conflicts"
        self._conflicts_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._active: MutableMapping[str, ActiveStrategyRecord] = {}
        self._conflicts: MutableMapping[str, StrategyConflict] = {}
        self._resolution_memory: Dict[str, str] = {}
        self._load_state()

    # ------------------------------------------------------------------
    # Public API
    def track_strategy(self, strategy: CodexStrategy) -> ActiveStrategyRecord:
        """Register or update an active strategy and refresh conflicts."""

        record = ActiveStrategyRecord.from_strategy(strategy)
        with self._lock:
            self._active[record.strategy_id] = record
            self._persist_active_locked()
            self._log_action("strategy_tracked", record.to_dict())
            self._detect_conflicts_locked()
        return record

    def resolve_strategy(self, strategy_id: str) -> None:
        """Remove a completed strategy from orchestration tracking."""

        with self._lock:
            if strategy_id not in self._active:
                return
            self._active.pop(strategy_id)
            self._persist_active_locked()
            self._log_action("strategy_resolved", {"strategy_id": strategy_id})
            self._detect_conflicts_locked()

    def scan(self) -> list[StrategyConflict]:
        """Return the current set of conflicts."""

        with self._lock:
            return list(self._conflicts.values())

    def dashboard_snapshot(self) -> Dict[str, Any]:
        """Summarize orchestrator state for dashboards."""

        with self._lock:
            return {
                "active": [record.to_dict() for record in self._active.values()],
                "conflicts": [conflict.to_dict() for conflict in self._conflicts.values()],
                "operator_controls": {
                    "decisions": ["approve", "merge", "sequence", "escalate", "quarantine"],
                },
            }

    def apply_decision(
        self,
        conflict_id: str,
        *,
        decision: str,
        operator: str,
        new_resolution: str | None = None,
        target_strategy: str | None = None,
        rationale: str | None = None,
    ) -> StrategyConflict:
        """Record an operator decision for a conflict."""

        with self._lock:
            if conflict_id not in self._conflicts:
                raise KeyError(conflict_id)
            conflict = self._conflicts[conflict_id]
            previous_resolution = conflict.resolution
            if decision == "approve":
                conflict.status = "operator_approved"
            elif decision in {"merge", "sequence", "escalate"}:
                conflict.resolution = decision
                conflict.status = (
                    "operator_approved"
                    if decision == conflict.proposed_resolution
                    else "operator_override"
                )
            elif decision == "quarantine":
                conflict.resolution = "quarantine"
                conflict.status = "operator_override"
                if target_strategy and target_strategy in self._active:
                    record = self._active[target_strategy]
                    record.metadata["quarantined"] = True
                    self._active[target_strategy] = record
                    self._persist_active_locked()
            elif decision == "override":
                if not new_resolution:
                    raise ValueError("override decision requires new_resolution")
                conflict.resolution = new_resolution
                conflict.status = "operator_override"
            else:
                raise ValueError(f"Unsupported decision: {decision}")

            conflict.metadata["operator"] = operator
            if rationale:
                conflict.metadata["rationale"] = rationale

            self._remember_resolution(conflict)
            self._persist_conflict_locked(conflict)
            self._persist_state_locked()
            self._log_action(
                "operator_decision",
                {
                    "conflict_id": conflict_id,
                    "decision": decision,
                    "previous_resolution": previous_resolution,
                    "resolution": conflict.resolution,
                    "operator": operator,
                },
            )
            return conflict

    # ------------------------------------------------------------------
    # Internal orchestration helpers
    def _detect_conflicts_locked(self) -> None:
        pairs = list(self._active.values())
        seen: set[str] = set()
        for left in pairs:
            for right in pairs:
                if left.strategy_id >= right.strategy_id:
                    continue
                key = self._conflict_key(left.strategy_id, right.strategy_id)
                seen.add(key)
                classes, metadata = self._analyze_pair(left, right)
                if not classes:
                    if key in self._conflicts:
                        conflict = self._conflicts.pop(key)
                        conflict.status = "resolved"
                        self._persist_conflict_locked(conflict)
                    continue
                conflict = self._conflicts.get(key)
                if conflict is None:
                    proposed = self._choose_resolution(classes, metadata, left, right)
                    resolution = proposed
                    metadata.setdefault("origin", "heuristic")
                    conflict = StrategyConflict(
                        conflict_id=key,
                        strategies=(left.strategy_id, right.strategy_id),
                        classes=tuple(sorted(classes)),
                        proposed_resolution=proposed,
                        resolution=resolution,
                        status="pending_operator"
                        if resolution == "escalate"
                        else "proposed",
                        metadata=metadata,
                    )
                    self._conflicts[key] = conflict
                    self._persist_conflict_locked(conflict)
                    self._log_action(
                        "conflict_detected",
                        {
                            "conflict_id": key,
                            "strategies": list(conflict.strategies),
                            "classes": list(conflict.classes),
                            "resolution": conflict.resolution,
                        },
                    )
                else:
                    conflict.classes = tuple(sorted(classes))
                    conflict.metadata.update(metadata)
                    if conflict.status in {"proposed", "pending_operator"}:
                        learned = self._memory_resolution(conflict)
                        if learned and learned != conflict.resolution:
                            conflict.proposed_resolution = learned
                            conflict.resolution = learned
                            conflict.metadata["origin"] = "learned"
                    self._persist_conflict_locked(conflict)

        stale = [key for key in self._conflicts if key not in seen]
        for key in stale:
            conflict = self._conflicts.pop(key)
            conflict.status = "resolved"
            self._persist_conflict_locked(conflict)

    def _analyze_pair(
        self, left: ActiveStrategyRecord, right: ActiveStrategyRecord
    ) -> tuple[set[str], Dict[str, Any]]:
        classes: set[str] = set()
        metadata: Dict[str, Any] = {
            "resources": sorted(left.resources & right.resources),
        }
        if metadata["resources"]:
            classes.add("resource")

        if left.horizon is not None and right.horizon is not None:
            diff = abs(left.horizon - right.horizon)
            metadata["horizon_delta"] = diff
            if diff > self.HORIZON_THRESHOLD:
                classes.add("temporal")

        if left.priority is not None and right.priority is not None:
            delta = abs(left.priority - right.priority)
            metadata["priority_delta"] = delta
            if delta > self.PRIORITY_THRESHOLD:
                classes.add("priority")

        if not metadata["resources"] and "priority" not in classes and "temporal" not in classes:
            return set(), {}
        return classes, metadata

    def _memory_key(self, conflict: StrategyConflict) -> str:
        resources = tuple(sorted(conflict.metadata.get("resources", [])))
        classes = "|".join(sorted(conflict.classes))
        return f"{classes}:{'&'.join(resources)}"

    def _memory_resolution(self, conflict: StrategyConflict) -> str | None:
        key = self._memory_key(conflict)
        return self._resolution_memory.get(key)

    def _remember_resolution(self, conflict: StrategyConflict) -> None:
        if conflict.status not in {"operator_approved", "operator_override"}:
            return
        key = self._memory_key(conflict)
        self._resolution_memory[key] = conflict.resolution

    def _choose_resolution(
        self,
        classes: Iterable[str],
        metadata: Mapping[str, Any],
        left: ActiveStrategyRecord,
        right: ActiveStrategyRecord,
    ) -> str:
        conflict = StrategyConflict(
            conflict_id=str(uuid.uuid4()),
            strategies=(left.strategy_id, right.strategy_id),
            classes=tuple(sorted(classes)),
            proposed_resolution="",
            resolution="",
            status="",
            metadata=dict(metadata),
        )
        learned = self._memory_resolution(conflict)
        if learned:
            return learned

        classes_set = set(classes)
        if "priority" in classes_set:
            return "escalate"
        if "temporal" in classes_set:
            return "sequence"
        if "resource" in classes_set:
            delta = metadata.get("priority_delta") or 0.0
            if delta and delta > self.PRIORITY_THRESHOLD:
                return "escalate"
            horizon_delta = metadata.get("horizon_delta") or 0.0
            return "merge" if horizon_delta <= self.HORIZON_THRESHOLD else "sequence"
        return "merge"

    def _conflict_key(self, left_id: str, right_id: str) -> str:
        return f"{left_id}__{right_id}"

    # ------------------------------------------------------------------
    # Persistence helpers
    def _load_state(self) -> None:
        if self._active_path.exists():
            for line in self._active_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                record = ActiveStrategyRecord(
                    strategy_id=payload.get("strategy_id", ""),
                    goal=payload.get("goal", ""),
                    status=payload.get("status", ""),
                    metadata=dict(payload.get("metadata", {})),
                    resources=set(payload.get("resources", [])),
                    horizon=_normalize_horizon(payload.get("horizon")),
                    priority=_normalize_priority(payload.get("priority")),
                )
                if record.strategy_id:
                    self._active[record.strategy_id] = record

        if self._state_path.exists():
            try:
                payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            self._resolution_memory = dict(payload.get("resolution_memory", {}))

        for file in self._conflicts_dir.glob("*.json"):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            conflict = StrategyConflict(
                conflict_id=payload.get("conflict_id", file.stem),
                strategies=tuple(payload.get("strategies", [])) or ("", ""),
                classes=tuple(payload.get("classes", [])),
                proposed_resolution=payload.get("proposed_resolution", "merge"),
                resolution=payload.get("resolution", "merge"),
                status=payload.get("status", "proposed"),
                metadata=dict(payload.get("metadata", {})),
            )
            if all(conflict.strategies):
                self._conflicts[conflict.conflict_id] = conflict

    def _persist_active_locked(self) -> None:
        self._active_path.parent.mkdir(parents=True, exist_ok=True)
        with self._active_path.open("w", encoding="utf-8") as handle:
            for record in self._active.values():
                handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")

    def _persist_conflict_locked(self, conflict: StrategyConflict) -> None:
        path = self._conflicts_dir / f"{conflict.conflict_id}.json"
        path.write_text(json.dumps(conflict.to_dict(), sort_keys=True, indent=2), encoding="utf-8")

    def _persist_state_locked(self) -> None:
        payload = {
            "resolution_memory": dict(self._resolution_memory),
        }
        self._state_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    def _log_action(self, action: str, payload: Mapping[str, Any]) -> None:
        record = {
            "action": action,
            "details": dict(payload),
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

