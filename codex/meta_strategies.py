"""Codex meta-strategy synthesis and storage utilities."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import threading
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

__all__ = [
    "CodexMetaStrategy",
    "MetaStrategyStorage",
    "PatternMiningEngine",
]


def _serialize_instance(instance: Mapping[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for key, value in instance.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[key] = value
        elif isinstance(value, Mapping):
            payload[key] = _serialize_instance(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            payload[key] = [
                _serialize_instance(item)
                if isinstance(item, Mapping)
                else item
                for item in value
            ]
        else:
            payload[key] = repr(value)
    return payload


@dataclass
class CodexMetaStrategy:
    """Reusable Codex meta-strategy template."""

    pattern: str
    abstraction: Dict[str, Any]
    instances: list[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern": self.pattern,
            "abstraction": dict(self.abstraction),
            "instances": [_serialize_instance(instance) for instance in self.instances],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CodexMetaStrategy":
        return cls(
            pattern=str(payload.get("pattern", "")),
            abstraction=dict(payload.get("abstraction", {})),
            instances=[dict(item) for item in payload.get("instances", [])],
            metadata=dict(payload.get("metadata", {})),
        )


class MetaStrategyStorage:
    """Persist Codex meta-strategies under /integration/meta_strategies."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path_for(self, pattern: str) -> Path:
        sanitized = pattern.replace("/", "_").replace(" ", "_")
        return self._root / f"{sanitized}.json"

    def save(self, strategy: CodexMetaStrategy) -> Path:
        payload = json.dumps(strategy.to_dict(), indent=2, sort_keys=True)
        path = self._path_for(strategy.pattern)
        with self._lock:
            path.write_text(payload, encoding="utf-8")
        return path

    def load(self, pattern: str) -> CodexMetaStrategy:
        path = self._path_for(pattern)
        if not path.exists():
            raise KeyError(f"Meta-strategy {pattern} is not stored")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CodexMetaStrategy.from_dict(payload)

    def list_all(self) -> Dict[str, CodexMetaStrategy]:
        stored: Dict[str, CodexMetaStrategy] = {}
        for file in self._root.glob("*.json"):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
                strategy = CodexMetaStrategy.from_dict(payload)
            except json.JSONDecodeError:
                continue
            stored[strategy.pattern] = strategy
        return stored


class PatternMiningEngine:
    """Mine recurring Codex arcs to propose reusable meta-strategies."""

    def __init__(
        self,
        root: Path | str = Path("integration"),
        *,
        confidence_threshold: float = 0.65,
        storage: MetaStrategyStorage | None = None,
        log_path: Path | None = None,
    ) -> None:
        self._root = Path(root)
        self._lock = threading.RLock()
        self._storage = storage or MetaStrategyStorage(self._root / "meta_strategies")
        self._log_path = log_path or (self._root / "meta_strategy_log.jsonl")
        self._proposals: Dict[str, CodexMetaStrategy] = {}
        self._usage_stats: MutableMapping[str, int] = defaultdict(int)
        self._confidence_threshold = float(confidence_threshold)
        self._state_path = self._root / "meta_strategy_state.json"
        self._load_state()

    # ------------------------------------------------------------------
    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold

    def set_threshold(self, value: float) -> None:
        with self._lock:
            self._confidence_threshold = max(0.1, min(0.95, float(value)))
            self._persist_state()

    # ------------------------------------------------------------------
    def analyze(self, arcs: Iterable[Mapping[str, Any]]) -> Sequence[CodexMetaStrategy]:
        clusters: Dict[tuple[str, tuple[str, ...], str], list[Dict[str, Any]]] = defaultdict(list)
        for arc in arcs:
            goal = str(arc.get("goal", "")).strip().lower()
            steps_raw = arc.get("steps") or []
            steps: tuple[str, ...]
            if isinstance(steps_raw, Sequence) and not isinstance(steps_raw, (str, bytes, bytearray)):
                steps = tuple(str(step).strip().lower() for step in steps_raw)
            else:
                steps = (str(steps_raw).strip().lower(),)
            operator = str(arc.get("operator_response", "none")).strip().lower()
            key = (goal, steps, operator)
            clusters[key].append(dict(arc))

        proposals: list[CodexMetaStrategy] = []
        for (goal, steps, operator), entries in clusters.items():
            if len(entries) < 2:
                continue
            status_counts = Counter(str(item.get("status", "success")).lower() for item in entries)
            successes = status_counts.get("success", 0)
            total = sum(status_counts.values())
            success_rate = successes / total if total else 0.0
            confidence = self._calculate_confidence(total, success_rate)
            if confidence < self._confidence_threshold:
                continue
            pattern = self._pattern_label(goal, steps, operator)
            abstraction = {
                "goal": goal,
                "step_order": list(steps),
                "operator": operator,
                "parameters": arc_parameters(entries),
            }
            metadata = {
                "confidence": round(confidence, 3),
                "success_rate": round(success_rate, 3),
                "instances": total,
                "operator_overrides": [],
                "adaptive_weightings": {
                    "success_rate": round(success_rate, 3),
                    "frequency": total,
                },
            }
            strategy = CodexMetaStrategy(
                pattern=pattern,
                abstraction=abstraction,
                instances=[_serialize_instance(entry) for entry in entries],
                metadata=metadata,
            )
            proposals.append(strategy)

        proposals.sort(key=lambda item: item.metadata.get("confidence", 0.0), reverse=True)
        with self._lock:
            self._proposals = {item.pattern: item for item in proposals}
        return proposals

    def dashboard_payload(self) -> list[Dict[str, Any]]:
        with self._lock:
            proposals = list(self._proposals.values())
        rows = [
            {
                "pattern": proposal.pattern,
                "abstraction": proposal.abstraction,
                "confidence": proposal.metadata.get("confidence", 0.0),
                "success_rate": proposal.metadata.get("success_rate", 0.0),
                "instances": proposal.metadata.get("instances", 0),
                "status": "proposed",
            }
            for proposal in proposals
        ]
        seen = {proposal.pattern for proposal in proposals}
        for stored in self._storage.list_all().values():
            if stored.pattern in seen:
                continue
            rows.append(
                {
                    "pattern": stored.pattern,
                    "abstraction": stored.abstraction,
                    "confidence": stored.metadata.get("confidence", 0.0),
                    "success_rate": stored.metadata.get("success_rate", 0.0),
                    "instances": stored.metadata.get("instances", len(stored.instances)),
                    "status": stored.metadata.get("status", "approved"),
                }
            )
        return rows

    def get(self, pattern: str) -> CodexMetaStrategy | None:
        try:
            return self._storage.load(pattern)
        except KeyError:
            return None

    def approve(self, pattern: str, *, operator: str | None = None) -> CodexMetaStrategy:
        with self._lock:
            if pattern not in self._proposals:
                raise KeyError(f"Meta-strategy {pattern} is not proposed")
            strategy = self._proposals.pop(pattern)
        strategy.metadata["status"] = "approved"
        if operator:
            strategy.metadata.setdefault("operator_overrides", []).append({
                "operator": operator,
                "action": "approved",
                "timestamp": _serialize_timestamp(),
            })
        self._storage.save(strategy)
        self._log_usage("approved", strategy.pattern, strategy.metadata)
        self._usage_stats["approvals"] += 1
        self._adjust_threshold(feedback="approval")
        return strategy

    def reject(self, pattern: str, *, operator: str | None = None) -> None:
        with self._lock:
            if pattern not in self._proposals:
                raise KeyError(f"Meta-strategy {pattern} is not proposed")
            strategy = self._proposals.pop(pattern)
        metadata = {
            "status": "rejected",
            "operator": operator,
        }
        self._log_usage("rejected", pattern, metadata)
        self._usage_stats["rejections"] += 1
        self._adjust_threshold(feedback="rejection")

    def applied_message(self, pattern: str) -> str:
        stored = self._storage.list_all()
        strategy = stored.get(pattern)
        if strategy is None:
            return f"Codex applied {pattern}."
        rate = strategy.metadata.get("success_rate")
        if rate is None:
            return f"Codex applied {pattern}."
        percent = int(round(float(rate) * 100))
        return f"Codex applied {pattern} (success rate {percent}%)."

    def record_application(self, pattern: str, *, outcome: str, context: Mapping[str, Any] | None = None) -> None:
        metadata = {"outcome": outcome}
        if context:
            metadata.update(_serialize_instance(context))
        self._log_usage("applied", pattern, metadata)

    # ------------------------------------------------------------------
    def _calculate_confidence(self, total: int, success_rate: float) -> float:
        baseline = 0.4 + min(0.3, math.log2(max(2, total)) / 5)
        weight = success_rate * 0.5
        return max(0.0, min(0.95, baseline + weight))

    def _pattern_label(self, goal: str, steps: Sequence[str], operator: str) -> str:
        steps_text = " → ".join(step for step in steps if step)
        goal_text = goal or "unknown_goal"
        operator_text = operator or "operator"
        return f"{goal_text} | {steps_text} | {operator_text}"

    def _log_usage(self, action: str, pattern: str, metadata: Mapping[str, Any]) -> None:
        record = {
            "timestamp": _serialize_timestamp(),
            "pattern": pattern,
            "action": action,
            "metadata": dict(metadata),
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _adjust_threshold(self, *, feedback: str) -> None:
        with self._lock:
            if feedback == "approval":
                self._confidence_threshold = max(0.35, self._confidence_threshold - 0.05)
            elif feedback == "rejection":
                self._confidence_threshold = min(0.9, self._confidence_threshold + 0.05)
            self._persist_state()

    def _persist_state(self) -> None:
        payload = {
            "confidence_threshold": self._confidence_threshold,
            "usage": dict(self._usage_stats),
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        threshold = payload.get("confidence_threshold")
        if threshold is not None:
            try:
                self._confidence_threshold = max(0.1, min(0.95, float(threshold)))
            except (TypeError, ValueError):  # pragma: no cover - defensive
                self._confidence_threshold = float(self._confidence_threshold)
        self._usage_stats = defaultdict(int, payload.get("usage", {}))


def arc_parameters(entries: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Derive parameter hints for a cluster of arc entries."""

    parameters: Dict[str, Any] = {}
    for entry in entries:
        for key, value in entry.items():
            if key in {"goal", "steps", "operator_response", "status"}:
                continue
            parameters.setdefault(key, set()).add(str(value))
    return {key: sorted(values) for key, values in parameters.items()}


def _serialize_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
