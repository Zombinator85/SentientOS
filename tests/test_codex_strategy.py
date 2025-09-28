from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codex.plans import CodexPlan, PlanController, PlanDashboard, PlanExecutor, PlanLedger, PlanStorage
from codex.strategy import configure_strategy_root, strategy_engine
from integration_memory import configure_integration_root, integration_memory


class _AcceptLedger(PlanLedger):
    def confirm_step(self, plan, step) -> bool:  # pragma: no cover - simple test double
        return True


_PLAN_TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _plan_now() -> datetime:
    return _PLAN_TIMESTAMP


def _setup_environment(tmp_path: Path) -> tuple[PlanStorage, PlanController, PlanExecutor, Path]:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)
    storage = PlanStorage(integration_root / "plans", now=_plan_now)
    ledger = _AcceptLedger()
    executor = PlanExecutor(ledger, storage, rollback_dir=integration_root / "rollbacks", now=_plan_now)
    controller = PlanController(storage)
    return storage, controller, executor, integration_root


def test_plan_execution_logs_outcomes(tmp_path: Path) -> None:
    storage, controller, executor, integration_root = _setup_environment(tmp_path)

    plan = CodexPlan.create(
        goal="Heal embodiment drift",
        steps=[
            {
                "title": "Restart camera services",
                "kind": "action",
                "action": "restart camera",
                "metadata": {"severity": "critical", "confidence": 0.9},
            },
            {
                "title": "Apply noise quarantine",
                "kind": "action",
                "action": "noise quarantine",
                "metadata": {"severity": "warning", "confidence": 0.6},
            },
        ],
        now=_plan_now,
    )
    storage.save_plan(plan)
    controller.approve_plan(plan.plan_id, "operator")
    controller.approve_step(plan.plan_id, 0, "operator")
    controller.approve_step(plan.plan_id, 1, "operator")

    def runner(step):
        return {"ran": step.action}

    executor.execute_next(plan.plan_id, runner)

    outcome_path = integration_root / "outcomes" / f"{plan.plan_id}.jsonl"
    assert outcome_path.exists()
    payload = [json.loads(line) for line in outcome_path.read_text().splitlines()]
    assert payload[0]["status"] == "success"
    assert payload[0]["impact"] == "high"
    assert payload[0]["operator_action"] == "approve"

    with pytest.raises(RuntimeError):
        def failing(step):
            raise RuntimeError("runner_failed")

        executor.execute_next(plan.plan_id, failing)

    payload = [json.loads(line) for line in outcome_path.read_text().splitlines()]
    assert len(payload) == 2
    assert payload[-1]["status"] == "failure"
    assert payload[-1]["impact"] == "medium"
    assert payload[-1]["metadata"]["rolled_back"] is True

    events = integration_memory.load_events(limit=None)
    assert any(event.event_type == "plan.outcome" for event in events)


def test_strategy_adjustments_and_dashboard(tmp_path: Path) -> None:
    storage, controller, executor, integration_root = _setup_environment(tmp_path)

    plan = CodexPlan.create(
        goal="Stabilize sensors",
        steps=[
            {
                "title": "Restart camera services",
                "kind": "action",
                "action": "restart camera",
                "metadata": {"severity": "critical", "confidence": 0.9},
            },
            {
                "title": "Apply noise quarantine",
                "kind": "action",
                "action": "noise quarantine",
                "metadata": {"severity": "warning", "confidence": 0.6},
            },
        ],
        now=_plan_now,
    )
    storage.save_plan(plan)
    controller.approve_plan(plan.plan_id, "operator")
    controller.approve_step(plan.plan_id, 0, "operator")
    controller.approve_step(plan.plan_id, 1, "operator")

    def first_runner(step):
        if step.action == "restart camera":
            return {"ran": step.action}
        raise RuntimeError("failure")

    with pytest.raises(RuntimeError):
        executor.execute_next(plan.plan_id, first_runner)
        executor.execute_next(plan.plan_id, first_runner)

    weights_after_failure = strategy_engine.weights_dict()
    assert weights_after_failure["severity"] < 0.4
    assert weights_after_failure["confidence"] > 0.15

    def override_plan(iteration: int) -> None:
        override = CodexPlan.create(
            goal=f"Override attempt {iteration}",
            steps=[
                {
                    "title": "Restart camera services",
                    "kind": "action",
                    "action": "restart camera",
                    "metadata": {"severity": "critical", "confidence": 0.9},
                },
                {
                    "title": "Apply noise quarantine",
                    "kind": "action",
                    "action": "noise quarantine",
                    "metadata": {"severity": "warning", "confidence": 0.6},
                },
            ],
            now=_plan_now,
        )
        storage.save_plan(override)
        controller.approve_plan(override.plan_id, "operator")
        controller.approve_step(override.plan_id, 1, "operator")
        controller.approve_step(override.plan_id, 0, "operator")

        def runner(step):
            return {"ran": step.action}

        executor.execute_next(override.plan_id, runner)
        executor.execute_next(override.plan_id, runner)

    for index in range(3):
        override_plan(index)

    summary = strategy_engine.sequence_summary()
    assert summary is not None
    assert "restart camera" in summary
    assert "noise quarantine" in summary
    assert "3" in summary

    assert strategy_engine.strategy_version > 1

    strategy_engine.set_lock(True, operator="warden")
    assert strategy_engine.locked is True

    dashboard = PlanDashboard(storage, rollback_dir=integration_root / "rollbacks")
    rows = list(dashboard.rows())
    assert rows
    assert rows[0]["strategy_locked"] is True
    assert isinstance(rows[0]["strategy_version"], int)
    assert rows[0]["strategy_summary"] == summary
