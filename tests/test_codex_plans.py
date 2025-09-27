from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import json

import pytest

from codex import (
    CodexPlan,
    PlanController,
    PlanDashboard,
    PlanExecutor,
    PlanLedger,
    PlanStep,
    PlanStorage,
)


def _fixed_now() -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


class RecordingLedger(PlanLedger):
    def __init__(self, approvals: Dict[str, bool] | None = None) -> None:
        self.approvals = approvals or {}
        self.confirmations: List[tuple[str, str]] = []

    def confirm_step(self, plan: CodexPlan, step: PlanStep) -> bool:
        self.confirmations.append((plan.plan_id, step.action))
        return self.approvals.get(step.action, True)


def _build_plan(storage: PlanStorage) -> CodexPlan:
    plan = CodexPlan.create(
        "Restore embodiment channel",
        [
            {
                "title": "Restart embodiment channel (camera offline)",
                "kind": "daemon",
                "action": "restart_channel",
                "metadata": {
                    "confidence": 0.82,
                    "dependencies": ["embodiment:camera"],
                    "rollback": "Revert daemon restart",
                },
            },
            {
                "title": "Verify stream re-established",
                "kind": "check",
                "action": "verify_stream",
                "metadata": {
                    "confidence": 0.91,
                    "dependencies": ["restart_channel"],
                },
            },
            {
                "title": "Quarantine noise anomalies if unresolved",
                "kind": "remediation",
                "action": "quarantine_noise",
                "metadata": {
                    "confidence": 0.7,
                    "rollback": "Release quarantine when signal stable",
                },
            },
        ],
        metadata={
            "confidence": 0.78,
            "dependencies": ["daemon:embodiment", "sensor:camera"],
            "rollback_strategy": "Restore prior embodiment configuration",
            "estimated_impact": "Embodiment camera availability",
        },
        plan_id="plan-camera-recovery",
        now=_fixed_now,
    )
    storage.save_plan(plan)
    return plan


def test_codex_plan_flow_and_rollback(tmp_path: Path) -> None:
    plan_dir = tmp_path / "integration" / "plans"
    rollback_dir = tmp_path / "integration" / "rollbacks"
    storage = PlanStorage(plan_dir, now=_fixed_now)
    plan = _build_plan(storage)

    ledger = RecordingLedger()
    executor = PlanExecutor(ledger, storage, rollback_dir=rollback_dir, now=_fixed_now)
    controller = PlanController(storage)

    loaded = storage.load_plan(plan.plan_id)
    assert loaded.goal == "Restore embodiment channel"
    assert [step.action for step in loaded.steps] == [
        "restart_channel",
        "verify_stream",
        "quarantine_noise",
    ]
    assert loaded.metadata["rollback_strategy"] == "Restore prior embodiment configuration"

    def runner(step: PlanStep) -> Dict[str, Any]:
        if step.action == "quarantine_noise":
            raise RuntimeError("Noise anomalies persisted")
        return {"status": "ok", "action": step.action}

    with pytest.raises(PermissionError):
        executor.execute_next(plan.plan_id, runner)

    controller.approve_plan(plan.plan_id, operator="keeper")

    with pytest.raises(PermissionError):
        executor.execute_next(plan.plan_id, runner)

    controller.approve_step(plan.plan_id, 0, operator="keeper")
    first_result = executor.execute_next(plan.plan_id, runner)
    assert first_result == {"status": "ok", "action": "restart_channel"}
    assert ledger.confirmations[0] == (plan.plan_id, "restart_channel")

    controller.approve_step(plan.plan_id, 1, operator="keeper")
    second_result = executor.execute_next(plan.plan_id, runner)
    assert second_result == {"status": "ok", "action": "verify_stream"}
    assert ledger.confirmations[1] == (plan.plan_id, "verify_stream")

    controller.approve_step(plan.plan_id, 2, operator="keeper")
    with pytest.raises(RuntimeError):
        executor.execute_next(plan.plan_id, runner)

    # Third confirmation is still recorded because ledger gating occurs before execution
    assert ledger.confirmations[2] == (plan.plan_id, "quarantine_noise")

    updated = storage.load_plan(plan.plan_id)
    assert updated.status == "failed"
    assert [step.status for step in updated.steps] == [
        "completed",
        "completed",
        "failed",
    ]
    assert updated.steps[0].approved_by == ["keeper"]
    assert updated.steps[2].error == "Noise anomalies persisted"

    rollback_path = executor.rollback_log_path(plan.plan_id)
    assert rollback_path.exists()
    entries = [json.loads(line) for line in rollback_path.read_text(encoding="utf-8").splitlines()]
    assert entries[-1]["reason"] == "Noise anomalies persisted"
    assert entries[-1]["step"]["action"] == "quarantine_noise"

    dashboard = PlanDashboard(storage, rollback_dir=rollback_dir)
    rows = list(dashboard.rows())
    assert rows == [
        {
            "plan_id": plan.plan_id,
            "goal": "Restore embodiment channel",
            "status": "failed",
            "steps": 3,
            "completed_steps": 2,
            "estimated_impact": "Embodiment camera availability",
            "rollback_path": str(rollback_path),
        }
    ]

