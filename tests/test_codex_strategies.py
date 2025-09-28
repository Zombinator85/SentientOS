"""Tests for multi-cycle Codex strategy arcs with conditional branches."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex.strategy import (
    CodexStrategy,
    StrategyBranch,
    StrategyLedger,
    StrategyPlan,
    configure_strategy_root,
    strategy_engine,
)
from integration_memory import configure_integration_root


class _LedgerSpy(StrategyLedger):
    def __init__(self) -> None:
        self.checkpoints: list[tuple[str, StrategyPlan]] = []
        self.branches: list[tuple[str, StrategyPlan, StrategyBranch]] = []

    def confirm_checkpoint(self, strategy: CodexStrategy, plan: StrategyPlan) -> bool:
        self.checkpoints.append((strategy.strategy_id, plan))
        return True

    def confirm_branch(self, strategy: CodexStrategy, plan: StrategyPlan, branch: StrategyBranch) -> bool:
        self.branches.append((strategy.strategy_id, plan, branch))
        return True


@pytest.fixture(autouse=True)
def _reset_strategy_engine(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)
    strategy_engine.set_strategy_ledger(StrategyLedger())


def test_strategy_branching_and_horizon_persistence(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)

    ledger = _LedgerSpy()
    strategy_engine.set_strategy_ledger(ledger)

    strategy = CodexStrategy(
        strategy_id="overnight-feed",
        goal="Maintain stable embodiment feeds overnight",
        plan_chain=[
            StrategyPlan(
                plan_id="stabilize",
                title="Stabilize feed",
                branches=[
                    StrategyBranch("anomaly_persists", "escalate", "Escalate if unresolved"),
                    StrategyBranch("resolved", "verify", "Verify when resolved"),
                ],
            ),
            StrategyPlan(
                plan_id="escalate",
                title="Escalate response",
                branches=[
                    StrategyBranch("anomaly_persists", "verify", "Escalation follow up"),
                    StrategyBranch("default", "verify", "Default verification"),
                ],
            ),
            StrategyPlan(
                plan_id="verify",
                title="Verify recovery",
                checkpoint=False,
                branches=[],
            ),
        ],
        conditions={
            "anomaly_persists": "If anomaly persists",
            "resolved": "If anomaly resolved early",
        },
        metadata={"horizon": 6, "confidence": 0.7, "rollback_path": "rollbacks/feed"},
    )

    strategy_engine.register_strategy(strategy, operator="warden")
    strategy_engine.activate_strategy(strategy.strategy_id, operator="warden")

    strategy_engine.checkpoint_strategy(strategy.strategy_id, operator="warden")
    assert ledger.checkpoints[0][1].plan_id == "stabilize"

    strategy_engine.advance_strategy(
        strategy.strategy_id,
        "anomaly_persists",
        operator="warden",
        condition_payload={"cycle": 1, "anomaly": "camera drift"},
    )

    after_first_branch = strategy_engine.load_strategy(strategy.strategy_id)
    assert after_first_branch.current_plan.plan_id == "escalate"
    assert after_first_branch.metadata["last_condition"] == "anomaly_persists"
    assert after_first_branch.plan_chain[0].ledger_confirmed is True

    strategy_engine.checkpoint_strategy(strategy.strategy_id, operator="warden")
    assert ledger.checkpoints[-1][1].plan_id == "escalate"

    strategy_engine.advance_strategy(
        strategy.strategy_id,
        "anomaly_persists",
        operator="warden",
        condition_payload={"cycle": 2, "anomaly": "sensor noise"},
    )

    after_second_branch = strategy_engine.load_strategy(strategy.strategy_id)
    assert after_second_branch.current_plan.plan_id == "verify"
    assert after_second_branch.metadata["horizon"] == 5
    assert after_second_branch.plan_chain[1].ledger_confirmed is True

    strategy_engine.terminate_strategy(strategy.strategy_id, operator="warden", rolled_back=False)
    final_strategy = strategy_engine.load_strategy(strategy.strategy_id)
    assert final_strategy.status == "completed"

    strategy_log = integration_root / "strategy_log.jsonl"
    assert strategy_log.exists()
    entries = [json.loads(line) for line in strategy_log.read_text(encoding="utf-8").splitlines() if line]
    actions = [entry["action"] for entry in entries]
    assert "strategy_advanced" in actions
    assert "strategy_horizon_adjusted" in actions

    stored_strategy = json.loads((integration_root / "strategies" / "overnight-feed.json").read_text())
    assert stored_strategy["metadata"]["horizon"] == 5


def test_operator_controls_and_branch_override(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)

    class _BlockingLedger(StrategyLedger):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def confirm_checkpoint(self, strategy: CodexStrategy, plan: StrategyPlan) -> bool:
            self.calls.append(f"checkpoint:{plan.plan_id}")
            return True

        def confirm_branch(self, strategy: CodexStrategy, plan: StrategyPlan, branch: StrategyBranch) -> bool:
            self.calls.append(f"branch:{branch.condition}")
            return branch.condition != "blocked"

    ledger = _BlockingLedger()
    strategy_engine.set_strategy_ledger(ledger)

    strategy = CodexStrategy(
        strategy_id="conditional-arc",
        goal="Route anomaly mitigation",
        plan_chain=[
            StrategyPlan(
                plan_id="mitigate",
                title="Mitigate anomaly",
                branches=[
                    StrategyBranch("blocked", "escalate", "Escalate when blocked"),
                    StrategyBranch("clear", "verify", "Verify when clear"),
                ],
            ),
            StrategyPlan(
                plan_id="escalate",
                title="Escalate",
                branches=[StrategyBranch("default", None, "End escalation")],
            ),
            StrategyPlan(
                plan_id="verify",
                title="Verify closure",
                checkpoint=False,
                branches=[],
            ),
        ],
        metadata={"horizon": 4, "confidence": 0.8, "rollback_path": "rollback://mitigate"},
    )

    strategy_engine.register_strategy(strategy, operator="guide")
    strategy_engine.activate_strategy(strategy.strategy_id, operator="guide")

    checkpointed = strategy_engine.checkpoint_strategy(strategy.strategy_id, operator="guide")
    assert checkpointed.status == "checkpoint"
    assert ledger.calls[0] == "checkpoint:mitigate"

    paused = strategy_engine.pause_strategy(strategy.strategy_id, operator="guide")
    assert paused.metadata["paused"] is True

    resumed = strategy_engine.resume_strategy(strategy.strategy_id, operator="guide")
    assert "paused" not in resumed.metadata

    with pytest.raises(PermissionError):
        strategy_engine.advance_strategy(strategy.strategy_id, "blocked", operator="guide")

    progressed = strategy_engine.advance_strategy(strategy.strategy_id, "clear", operator="guide")
    assert progressed.current_plan.plan_id == "verify"

    terminated = strategy_engine.terminate_strategy(strategy.strategy_id, operator="guide", rolled_back=True)
    assert terminated.status == "rolled_back"
    assert any(call.startswith("branch:") for call in ledger.calls)
