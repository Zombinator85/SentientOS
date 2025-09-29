import json
from pathlib import Path

from codex.orchestrator import StrategyOrchestrator
from codex.strategy import CodexStrategy, StrategyPlan, configure_strategy_root
from integration_memory import configure_integration_root


def _strategy(
    strategy_id: str,
    *,
    goal: str,
    channels: list[str],
    horizon: float,
    priority: float,
) -> CodexStrategy:
    return CodexStrategy(
        strategy_id=strategy_id,
        goal=goal,
        status="active",
        plan_chain=[
            StrategyPlan(
                plan_id=f"{strategy_id}-plan",
                title="stabilize",
                branches=[],
            )
        ],
        metadata={
            "channels": channels,
            "horizon": horizon,
            "priority": priority,
        },
    )


def test_orchestrator_detects_conflicts_and_resolution(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)

    orchestrator = StrategyOrchestrator(integration_root)
    first = _strategy(
        "vision-stability",
        goal="Stabilize embodiment vision channel",
        channels=["embodiment:vision"],
        horizon=4,
        priority=0.7,
    )
    second = _strategy(
        "vision-boost",
        goal="Boost embodiment vision clarity",
        channels=["embodiment:vision"],
        horizon=5,
        priority=0.68,
    )

    orchestrator.track_strategy(first)
    orchestrator.track_strategy(second)
    conflicts = orchestrator.scan()

    assert conflicts, "Expected a conflict to be detected"
    conflict = conflicts[0]
    assert "resource" in conflict.classes
    assert conflict.proposed_resolution == "merge"

    active_path = integration_root / "strategies" / "active.jsonl"
    assert active_path.exists()
    lines = [line for line in active_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2

    conflict_files = list((tmp_path / "pulse" / "conflicts").glob("*.json"))
    assert conflict_files, "Conflicts should be logged to /pulse/conflicts"


def test_orchestrator_sequences_and_escalates(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)

    orchestrator = StrategyOrchestrator(integration_root)
    long_horizon = _strategy(
        "cooling-long",
        goal="Sustain thermal drift mitigation",
        channels=["daemon:cooling"],
        horizon=9,
        priority=0.55,
    )
    short_horizon = _strategy(
        "cooling-short",
        goal="Immediate cooling pulse",
        channels=["daemon:cooling"],
        horizon=1,
        priority=0.52,
    )
    orchestrator.track_strategy(long_horizon)
    orchestrator.track_strategy(short_horizon)

    high_priority = _strategy(
        "narrative-emergency",
        goal="Narrative crisis escalation",
        channels=["daemon:narrative"],
        horizon=2,
        priority=0.95,
    )
    low_priority = _strategy(
        "narrative-sustain",
        goal="Narrative stability assurance",
        channels=["daemon:narrative"],
        horizon=2,
        priority=0.2,
    )
    orchestrator.track_strategy(high_priority)
    orchestrator.track_strategy(low_priority)

    conflicts = orchestrator.scan()
    assert len(conflicts) >= 2
    by_pair = {tuple(conflict.strategies): conflict for conflict in conflicts}

    cooling_key = tuple(sorted(["cooling-long", "cooling-short"]))
    narrative_key = tuple(sorted(["narrative-emergency", "narrative-sustain"]))

    cooling_conflict = by_pair[(cooling_key[0], cooling_key[1])]
    assert "temporal" in cooling_conflict.classes
    assert cooling_conflict.proposed_resolution == "sequence"

    narrative_conflict = by_pair[(narrative_key[0], narrative_key[1])]
    assert "priority" in narrative_conflict.classes
    assert narrative_conflict.proposed_resolution == "escalate"


def test_dashboard_and_operator_override(tmp_path: Path) -> None:
    integration_root = tmp_path / "integration"
    configure_integration_root(integration_root)
    configure_strategy_root(integration_root)

    orchestrator = StrategyOrchestrator(integration_root)
    alpha = _strategy(
        "relay-alpha",
        goal="Relay anomaly suppression",
        channels=["channel:relay"],
        horizon=3,
        priority=0.45,
    )
    beta = _strategy(
        "relay-beta",
        goal="Relay optimization",
        channels=["channel:relay"],
        horizon=4,
        priority=0.42,
    )

    orchestrator.track_strategy(alpha)
    orchestrator.track_strategy(beta)
    conflicts = orchestrator.scan()
    conflict = conflicts[0]

    snapshot = orchestrator.dashboard_snapshot()
    assert snapshot["active"], "Active strategies should appear on the dashboard"
    assert snapshot["conflicts"], "Conflicts should appear on the dashboard"

    orchestrator.apply_decision(
        conflict.conflict_id,
        decision="override",
        operator="warden",
        new_resolution="sequence",
        rationale="Queue after inspection",
    )

    updated = orchestrator.dashboard_snapshot()
    dashboard_conflict = updated["conflicts"][0]
    assert dashboard_conflict["resolution"] == "sequence"
    assert dashboard_conflict["status"] == "operator_override"

    log_path = integration_root / "orchestration_log.jsonl"
    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert any(entry["action"] == "operator_decision" for entry in entries)

    # Adaptive preference after operator override
    orchestrator.resolve_strategy("relay-alpha")
    orchestrator.resolve_strategy("relay-beta")

    gamma = _strategy(
        "relay-gamma",
        goal="Relay audit",
        channels=["channel:relay"],
        horizon=3,
        priority=0.4,
    )
    delta = _strategy(
        "relay-delta",
        goal="Relay stabilizer",
        channels=["channel:relay"],
        horizon=5,
        priority=0.43,
    )
    orchestrator.track_strategy(gamma)
    orchestrator.track_strategy(delta)
    learned_conflict = orchestrator.scan()[0]
    assert learned_conflict.proposed_resolution == "sequence"
    assert learned_conflict.metadata.get("origin") in {"heuristic", "learned"}

    orchestrator.apply_decision(
        learned_conflict.conflict_id,
        decision="quarantine",
        operator="warden",
        target_strategy="relay-delta",
        rationale="Hold delta until audit",
    )
    refreshed = orchestrator.dashboard_snapshot()
    active = {item["strategy_id"]: item for item in refreshed["active"]}
    assert active["relay-delta"]["metadata"]["quarantined"] is True

