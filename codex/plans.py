"""Codex bounded plan orchestration with ledger gating and rollbacks."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional

import json
import uuid

from .strategy import StrategyAdjustmentEngine, strategy_engine


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PlanStep:
    """Single action inside a Codex plan."""

    title: str
    kind: str
    action: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    approved_by: List[str] = field(default_factory=list)
    ledger_confirmed: bool = False
    result: Any | None = None
    error: str | None = None

    def approve(self, operator: str) -> None:
        if operator not in self.approved_by:
            self.approved_by.append(operator)
        if self.status == "pending":
            self.status = "approved"

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "title": self.title,
            "kind": self.kind,
            "action": self.action,
            "metadata": self.metadata,
            "status": self.status,
            "approved_by": list(self.approved_by),
            "ledger_confirmed": self.ledger_confirmed,
            "error": self.error,
        }
        if self.result is not None:
            payload["result"] = self.result
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlanStep":
        step = cls(
            title=str(payload["title"]),
            kind=str(payload["kind"]),
            action=str(payload["action"]),
            metadata=dict(payload.get("metadata") or {}),
            status=str(payload.get("status", "pending")),
            approved_by=list(payload.get("approved_by") or []),
        )
        step.ledger_confirmed = bool(payload.get("ledger_confirmed", False))
        if "result" in payload:
            step.result = payload["result"]
        if payload.get("error"):
            step.error = str(payload["error"])
        return step


@dataclass
class CodexPlan:
    """Structured, reversible Codex plan with explicit operator control."""

    plan_id: str
    goal: str
    steps: List[PlanStep]
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "proposed"
    approved_by: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_default_now)
    updated_at: datetime = field(default_factory=_default_now)

    def approve(self, operator: str) -> None:
        if operator not in self.approved_by:
            self.approved_by.append(operator)
        if self.status in {"proposed", "rejected"}:
            self.status = "approved"

    def reject(self, operator: str | None = None) -> None:
        if operator:
            self.approved_by = [value for value in self.approved_by if value != operator]
        self.status = "rejected"

    def quarantine(self) -> None:
        self.status = "quarantined"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "metadata": self.metadata,
            "status": self.status,
            "approved_by": list(self.approved_by),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CodexPlan":
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        steps = [PlanStep.from_dict(step) for step in payload.get("steps", [])]
        plan = cls(
            plan_id=str(payload["plan_id"]),
            goal=str(payload["goal"]),
            steps=steps,
            metadata=dict(payload.get("metadata") or {}),
            status=str(payload.get("status", "proposed")),
            approved_by=list(payload.get("approved_by") or []),
            created_at=created_at,
            updated_at=updated_at,
        )
        return plan

    @classmethod
    def create(
        cls,
        goal: str,
        steps: Iterable[PlanStep | Mapping[str, Any]],
        metadata: Optional[Mapping[str, Any]] = None,
        *,
        plan_id: str | None = None,
        now: Callable[[], datetime] = _default_now,
    ) -> "CodexPlan":
        parsed_steps: List[PlanStep] = []
        for entry in steps:
            if isinstance(entry, PlanStep):
                parsed_steps.append(entry)
            else:
                parsed_steps.append(
                    PlanStep(
                        title=str(entry["title"]),
                        kind=str(entry.get("kind", "action")),
                        action=str(entry.get("action") or entry["title"]),
                        metadata=dict(entry.get("metadata") or {}),
                    )
                )
        timestamp = now()
        identifier = plan_id or f"plan-{timestamp.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        metadata_payload = dict(metadata or {})
        metadata_payload.setdefault("strategy_version", strategy_engine.strategy_version)
        return cls(
            plan_id=identifier,
            goal=goal,
            steps=parsed_steps,
            metadata=metadata_payload,
            status="proposed",
            created_at=timestamp,
            updated_at=timestamp,
        )

    def next_step_index(self) -> Optional[int]:
        for index, step in enumerate(self.steps):
            if step.status != "completed":
                return index
        return None

    def completed(self) -> bool:
        return all(step.status == "completed" for step in self.steps)


class PlanStorage:
    """Persist Codex plans in /integration/plans."""

    def __init__(self, base_dir: Path | str = Path("integration/plans"), *, now: Callable[[], datetime] = _default_now) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._now = now

    def save_plan(self, plan: CodexPlan) -> Path:
        plan.updated_at = self._now()
        path = self._plan_path(plan.plan_id)
        path.write_text(json.dumps(plan.to_dict(), sort_keys=True, indent=2), encoding="utf-8")
        return path

    def load_plan(self, plan_id: str) -> CodexPlan:
        path = self._plan_path(plan_id)
        if not path.exists():
            raise FileNotFoundError(f"Plan {plan_id} not found")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CodexPlan.from_dict(payload)

    def iter_plans(self) -> Iterator[CodexPlan]:
        if not self._base_dir.exists():
            return
        for entry in sorted(self._base_dir.glob("*.json")):
            payload = json.loads(entry.read_text(encoding="utf-8"))
            yield CodexPlan.from_dict(payload)

    def _plan_path(self, plan_id: str) -> Path:
        filename = f"{plan_id}.json"
        return self._base_dir / filename


class PlanLedger:
    """Interface used to gate Codex plan steps through the ledger."""

    def confirm_step(self, plan: CodexPlan, step: PlanStep) -> bool:  # pragma: no cover - interface method
        raise NotImplementedError


class PlanController:
    """Operator controls for Codex plans."""

    def __init__(self, storage: PlanStorage) -> None:
        self._storage = storage

    def approve_plan(self, plan_id: str, operator: str) -> CodexPlan:
        plan = self._storage.load_plan(plan_id)
        plan.approve(operator)
        plan.status = "approved"
        self._storage.save_plan(plan)
        return plan

    def approve_step(self, plan_id: str, index: int, operator: str) -> PlanStep:
        plan = self._storage.load_plan(plan_id)
        if index < 0 or index >= len(plan.steps):
            raise IndexError("Invalid plan step index")
        step = plan.steps[index]
        expected_index = plan.next_step_index()
        if expected_index is None:
            expected_index = index
        if index != expected_index:
            step.metadata.setdefault("override_sequence", [plan.steps[expected_index].action if expected_index < len(plan.steps) else step.action, step.action])
            step.metadata["operator_action"] = "override"
        else:
            step.metadata.setdefault("operator_action", "approve")
        step.approve(operator)
        self._storage.save_plan(plan)
        return step

    def reject_plan(self, plan_id: str) -> CodexPlan:
        plan = self._storage.load_plan(plan_id)
        plan.reject()
        self._storage.save_plan(plan)
        return plan

    def quarantine_plan(self, plan_id: str) -> CodexPlan:
        plan = self._storage.load_plan(plan_id)
        plan.quarantine()
        self._storage.save_plan(plan)
        return plan


class PlanExecutor:
    """Execute Codex plan steps sequentially with ledger gating and rollbacks."""

    def __init__(
        self,
        ledger: PlanLedger,
        storage: PlanStorage,
        *,
        rollback_dir: Path | str = Path("integration/rollbacks"),
        now: Callable[[], datetime] = _default_now,
        strategy: StrategyAdjustmentEngine | None = None,
    ) -> None:
        self._ledger = ledger
        self._storage = storage
        self._rollback_dir = Path(rollback_dir)
        self._rollback_dir.mkdir(parents=True, exist_ok=True)
        self._now = now
        self._strategy = strategy or strategy_engine

    def execute_next(self, plan_id: str, runner: Callable[[PlanStep], Any]) -> Any:
        plan = self._storage.load_plan(plan_id)
        if plan.status not in {"approved", "in_progress"}:
            raise PermissionError("Plan must be approved before execution")

        index = plan.next_step_index()
        if index is None:
            raise RuntimeError("Plan already completed")

        step = plan.steps[index]

        for previous in plan.steps[:index]:
            if previous.status != "completed":
                raise RuntimeError("Previous steps must be completed before executing the next step")

        if step.status != "approved":
            raise PermissionError("Plan step requires operator approval")

        plan.status = "in_progress"
        self._storage.save_plan(plan)

        operator_action = step.metadata.get("operator_action", "approve")

        if not self._ledger.confirm_step(plan, step):
            step.status = "failed"
            step.error = "ledger_rejected"
            self._storage.save_plan(plan)
            self._record_outcome(
                plan,
                step,
                index,
                status="rollback",
                operator_action=operator_action,
                extra_metadata={"reason": "ledger_rejected"},
            )
            self._log_rollback(plan, step, reason="ledger_rejected")
            plan.status = "failed"
            self._storage.save_plan(plan)
            raise PermissionError("Ledger rejected the plan step")

        step.ledger_confirmed = True
        step.status = "executing"
        self._storage.save_plan(plan)

        try:
            result = runner(step)
        except Exception as exc:  # pragma: no cover - exercised in tests
            step.status = "failed"
            step.error = str(exc)
            self._storage.save_plan(plan)
            self._record_outcome(
                plan,
                step,
                index,
                status="failure",
                operator_action=operator_action,
                extra_metadata={"rolled_back": True},
                error=str(exc),
            )
            self._log_rollback(plan, step, reason=str(exc))
            plan.status = "failed"
            self._storage.save_plan(plan)
            raise

        step.status = "completed"
        step.result = result
        self._storage.save_plan(plan)

        self._record_outcome(
            plan,
            step,
            index,
            status="success",
            operator_action=operator_action,
        )

        if plan.completed():
            plan.status = "completed"
        self._storage.save_plan(plan)
        return result

    def rollback_log_path(self, plan_id: str) -> Path:
        return self._rollback_dir / f"{plan_id}.jsonl"

    def _log_rollback(self, plan: CodexPlan, step: PlanStep, *, reason: str) -> None:
        payload = {
            "timestamp": self._now().isoformat(),
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "step": {
                "title": step.title,
                "action": step.action,
                "kind": step.kind,
                "metadata": step.metadata,
                "status": step.status,
                "error": step.error,
            },
            "reason": reason,
        }
        path = self.rollback_log_path(plan.plan_id)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _record_outcome(
        self,
        plan: CodexPlan,
        step: PlanStep,
        index: int,
        *,
        status: str,
        operator_action: str,
        extra_metadata: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        metadata = dict(step.metadata)
        if extra_metadata:
            metadata.update(extra_metadata)
        try:
            self._strategy.record_outcome(
                plan_id=plan.plan_id,
                plan_goal=plan.goal,
                step_index=index,
                step_title=step.title,
                step_action=step.action,
                step_kind=step.kind,
                status=status,
                operator_action=operator_action,
                step_metadata=metadata,
                result=step.result,
                error=error or step.error,
            )
        except Exception:  # pragma: no cover - defensive to avoid execution failure
            return


class PlanDashboard:
    """Summarize Codex plans for operator review."""

    def __init__(self, storage: PlanStorage, *, rollback_dir: Path | str = Path("integration/rollbacks")) -> None:
        self._storage = storage
        self._rollback_dir = Path(rollback_dir)

    def rows(self) -> Iterator[Dict[str, Any]]:
        strategy_version = strategy_engine.strategy_version
        strategy_locked = strategy_engine.locked
        summary = strategy_engine.sequence_summary()
        for plan in self._storage.iter_plans():
            yield {
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "status": plan.status,
                "steps": len(plan.steps),
                "completed_steps": sum(1 for step in plan.steps if step.status == "completed"),
                "estimated_impact": plan.metadata.get("estimated_impact"),
                "rollback_path": str(self._rollback_dir / f"{plan.plan_id}.jsonl"),
                "strategy_version": plan.metadata.get("strategy_version", strategy_version),
                "strategy_locked": strategy_locked,
                "strategy_summary": summary,
            }

