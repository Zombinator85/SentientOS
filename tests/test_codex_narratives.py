from __future__ import annotations

import json
from pathlib import Path

from codex.anomalies import Anomaly
from codex.governance import GovernanceDecision
from codex.narratives import CodexNarrator
from codex.strategy import CodexStrategy, StrategyPlan
from integration_dashboard import integration_panel_state
from integration_memory import configure_integration_root


def test_narratives_include_contextual_fields(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    narrator = CodexNarrator(integration_root)

    decision = GovernanceDecision(
        pattern="vision:stability",
        strategy_id="vision-guard",
        status="alert",
        divergence_score=0.42,
        actions=["Throttle conflicting plan"],
        details={"next_step": "Run integrity sweep", "outcome": "under_review"},
    )

    entry = narrator.create_governance_narrative(
        decision,
        event_id="gov-vision-guard",
        pulse_path="/pulse/governance/gov-vision-guard.json",
        integration_path=str(integration_root / "governance_log.jsonl"),
    )

    assert entry.summary.count("Trigger:") == 1
    for key in ["trigger", "response", "reasoning", "outcome", "next_step"]:
        assert getattr(entry, key), f"Expected {key} to be populated"

    stored = json.loads((integration_root / "narratives" / "gov-vision-guard.json").read_text(encoding="utf-8"))
    assert stored["sources"]["pulse"].endswith("gov-vision-guard.json")
    history = stored["history"]
    assert len(history) == 1
    latest = history[-1]
    for label in ["trigger", "response", "reasoning", "outcome", "next_step"]:
        assert latest[label]


def test_narratives_versioning_and_feedback(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    narrator = CodexNarrator(integration_root)

    strategy = CodexStrategy(
        strategy_id="relay-stabilize",
        goal="Stabilize relay output",
        plan_chain=[StrategyPlan(plan_id="relay-plan-1", title="Initial sweep")],
        metadata={"channels": ["relay"], "priority": 0.7, "horizon": 3},
    )

    narrator.create_strategy_narrative(
        strategy,
        event_id="strategy-relay-stabilize",
        pulse_path="/pulse/strategies/relay.json",
        integration_path=str(integration_root / "strategies" / "active.jsonl"),
    )

    narrator.rewrite_narrative(
        "strategy-relay-stabilize",
        updates={"outcome": "Strategy status remains checkpoint", "next_step": "Escalate to governance review"},
        operator="warden",
    )

    path = integration_root / "narratives" / "strategy-relay-stabilize.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["current_version"] == 2
    assert len(stored["history"]) == 2
    assert stored["history"][-1]["outcome"] == "Strategy status remains checkpoint"

    narrator.log_feedback("strategy-relay-stabilize", operator="warden", action="approve", notes="Clear summary")
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["feedback"]["approve"] == 1


def test_dashboard_switches_between_logs_and_narratives(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    memory = configure_integration_root(integration_root)
    memory.record_event(
        "heartbeat",
        source="CodexDaemon",
        impact="baseline",
        payload={"detail": "Routine"},
    )

    narrator = CodexNarrator(integration_root)
    anomaly = Anomaly("camera_offline", "Camera offline for 3 minutes", "warning", metadata={"mitigation": "Restarted sensor"})
    narrator.create_anomaly_narrative(
        anomaly,
        event_id="anomaly-camera",
        pulse_path="/pulse/anomalies/camera.json",
        integration_path=str(integration_root / "anomalies" / "camera.jsonl"),
    )

    logs_state = integration_panel_state(memory=memory, view="logs", narrator=narrator)
    assert logs_state.active_view == "logs"
    assert logs_state.feed == logs_state.events

    narrative_state = integration_panel_state(memory=memory, view="narratives", narrator=narrator)
    assert narrative_state.active_view == "narratives"
    assert narrative_state.feed == narrative_state.narratives
    assert narrative_state.narratives, "Expected narratives to be available"
    first = narrative_state.narratives[0]
    for field in ["trigger", "response", "reasoning", "outcome", "next_step"]:
        assert field in first and first[field]
