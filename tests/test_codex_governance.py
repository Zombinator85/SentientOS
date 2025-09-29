from __future__ import annotations

import json
from pathlib import Path

from codex.meta_strategies import CodexMetaStrategy
from codex.strategy import CodexStrategy, StrategyPlan, StrategyAdjustmentEngine
from integration_memory import configure_integration_root


def _setup_engine(tmp_path: Path) -> tuple[StrategyAdjustmentEngine, Path]:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    engine = StrategyAdjustmentEngine(root=integration_root)
    return engine, integration_root


def _meta_strategy() -> CodexMetaStrategy:
    return CodexMetaStrategy(
        pattern="stabilize sensors | diagnose anomaly → stabilize signal | operator",
        abstraction={
            "goal": "stabilize sensors",
            "step_order": ["diagnose anomaly", "stabilize signal"],
            "parameters": {"escalation_path": ["notify ops", "page steward"]},
        },
        instances=[],
        metadata={"status": "approved", "confidence": 0.82},
    )


def _strategy(
    *,
    strategy_id: str,
    steps: list[str],
    meta_pattern: str,
    escalation_path: list[str] | None = None,
) -> CodexStrategy:
    plans = [
        StrategyPlan(plan_id=f"plan-{index}", title=title)
        for index, title in enumerate(steps)
    ]
    metadata = {"meta_strategy": meta_pattern}
    if escalation_path is not None:
        metadata["escalation_path"] = escalation_path
    return CodexStrategy(
        strategy_id=strategy_id,
        goal="Stabilize sensors",
        plan_chain=plans,
        metadata=metadata,
    )


def test_governor_detects_compliance_and_divergence(tmp_path: Path) -> None:
    engine, integration_root = _setup_engine(tmp_path)
    governor = engine.meta_governor()
    meta = _meta_strategy()
    governor.register_meta_strategy(meta)

    aligned = _strategy(
        strategy_id="strategy-1",
        steps=["Diagnose Anomaly", "Stabilize Signal"],
        meta_pattern=meta.pattern,
        escalation_path=["Notify Ops", "Page Steward"],
    )
    engine.register_strategy(aligned)
    state = governor.state_for(aligned.strategy_id)
    assert state is not None
    assert state.status == "aligned"
    assert state.suspended is False

    divergent = _strategy(
        strategy_id="strategy-1",
        steps=["Collect Telemetry", "Stabilize Signal"],
        meta_pattern=meta.pattern,
        escalation_path=["Notify Ops"],
    )
    engine.register_strategy(divergent)
    state = governor.state_for(divergent.strategy_id)
    assert state is not None
    assert state.status == "suspended"
    assert state.suspended is True
    assert state.divergence_score > 0
    assert governor.anomalies(), "Divergence should be logged as an anomaly"

    # A second observation should escalate the divergence
    governor.observe(divergent, reason="monitor")
    escalated_state = governor.state_for(divergent.strategy_id)
    assert escalated_state is not None
    assert escalated_state.status == "escalated"

    previous_tolerance = governor.tolerance_for(meta.pattern)
    override_state = governor.operator_override(
        meta.pattern,
        divergent.strategy_id,
        operator="ops",
        approve=False,
        rationale="manual review cleared the drift",
    )
    assert override_state.status == "override"
    assert override_state.suspended is False
    assert governor.tolerance_for(meta.pattern) > previous_tolerance

    recent_events = governor.recent_events()
    assert any(event["event"] == "governance_override" for event in recent_events)

    log_path = integration_root / "governance_log.jsonl"
    assert log_path.exists()
    with log_path.open("r", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    assert any(entry["event"] == "governance_override" for entry in records)


def test_governor_resequence_and_dashboard_controls(tmp_path: Path) -> None:
    engine, integration_root = _setup_engine(tmp_path)
    governor = engine.meta_governor()
    meta = _meta_strategy()
    governor.register_meta_strategy(meta)

    resequence_candidate = _strategy(
        strategy_id="strategy-2",
        steps=["Stabilize Signal", "Diagnose Anomaly"],
        meta_pattern=meta.pattern,
        escalation_path=["Notify Ops", "Page Steward"],
    )
    engine.register_strategy(resequence_candidate)
    state = governor.state_for(resequence_candidate.strategy_id)
    assert state is not None
    assert state.status == "resequence"
    assert state.suspended is False
    assert state.resequenced is True

    dashboard = governor.dashboard_snapshot()
    assert dashboard["enabled"] is True
    assert "override_escalation" in dashboard["operator_controls"]["actions"]
    assert dashboard["meta_strategies"], "Dashboard should list supervised meta-strategies"
    pattern_row = next(row for row in dashboard["meta_strategies"] if row["pattern"] == meta.pattern)
    supervised_ids = [entry["strategy_id"] for entry in pattern_row["supervising"]]
    assert resequence_candidate.strategy_id in supervised_ids

    log_path = integration_root / "governance_log.jsonl"
    assert log_path.exists()
    with log_path.open("r", encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle if line.strip()]
    assert any(entry["event"] == "governance_resequence" for entry in lines)
