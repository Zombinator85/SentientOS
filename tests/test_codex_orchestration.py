import json
import inspect
from pathlib import Path

from codex.orchestrator import StrategyOrchestrator
from codex.strategy import CodexStrategy, StrategyPlan, configure_strategy_root
from integration_memory import configure_integration_root
from sentientos import scoped_lifecycle_diagnostic
from sentientos.orchestration_intent_fabric import resolve_current_re_evaluation_basis_brief


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


def _resolve_basis(
    tmp_path: Path,
    *,
    watchpoint_class: str,
    satisfaction_status: str,
    recommendation: str,
    expected_actor: str = "orchestration_body",
    resolution_path: str = "none",
    operator_influence_state: str = "no_operator_influence_yet",
    readiness_verdict: str = "ready_to_proceed",
    wait_kind: str = "awaiting_internal_result_closure",
    pressure_classification: str = "stable_or_low_pressure",
    wake_classification: str = "wake_ready",
    wake_posture: str = "informational_only",
    resume_ready: bool = True,
) -> dict[str, object]:
    return resolve_current_re_evaluation_basis_brief(
        tmp_path,
        current_orchestration_state={
            "current_orchestration_state_id": "state-1",
            "current_resolution_path": resolution_path,
        },
        current_orchestration_watchpoint={
            "orchestration_watchpoint_id": "watch-1",
            "watchpoint_class": watchpoint_class,
        },
        watchpoint_satisfaction={
            "watchpoint_satisfaction_id": "sat-1",
            "satisfaction_status": satisfaction_status,
        },
        re_evaluation_trigger_recommendation={
            "re_evaluation_trigger_id": "ret-1",
            "recommendation": recommendation,
            "expected_actor": expected_actor,
        },
        current_orchestration_resumption_candidate={
            "orchestration_resumption_candidate_id": "cand-1",
            "resumption_candidate_class": "resumption_candidate" if resume_ready else "no_resume_candidate",
            "resume_ready": resume_ready,
        },
        current_resumed_operation_readiness={
            "resumed_operation_readiness_verdict": readiness_verdict,
        },
        current_orchestration_watchpoint_brief={
            "wait_kind": wait_kind,
        },
        current_orchestration_pressure_signal={
            "pressure_classification": pressure_classification,
        },
        current_orchestration_wake_readiness_detector={
            "wake_readiness_classification": wake_classification,
            "result_posture": wake_posture,
        },
        operator_resolution_influence={
            "operator_influence_state": operator_influence_state,
        },
        unified_result={
            "resolution_path": resolution_path,
        },
    )


def test_current_re_evaluation_basis_brief_classifications(tmp_path: Path) -> None:
    satisfaction = _resolve_basis(
        tmp_path,
        watchpoint_class="await_new_proposal",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
    )
    assert satisfaction["basis_classification"] == "satisfaction_driven_re_evaluation"

    operator = _resolve_basis(
        tmp_path,
        watchpoint_class="await_operator_resolution",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_packet_synthesis",
        operator_influence_state="operator_resolution_applied",
    )
    assert operator["basis_classification"] == "operator_resolution_driven_re_evaluation"

    internal = _resolve_basis(
        tmp_path,
        watchpoint_class="await_internal_execution_result",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
        resolution_path="internal_execution",
    )
    assert internal["basis_classification"] == "internal_result_driven_re_evaluation"

    external = _resolve_basis(
        tmp_path,
        watchpoint_class="await_external_fulfillment_receipt",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
        resolution_path="external_fulfillment",
    )
    assert external["basis_classification"] == "external_fulfillment_driven_re_evaluation"

    continuity = _resolve_basis(
        tmp_path,
        watchpoint_class="await_new_proposal",
        satisfaction_status="watchpoint_stale",
        recommendation="hold_for_manual_review",
        wait_kind="continuity_uncertain",
        pressure_classification="fragmentation_pressure",
        wake_classification="wake_blocked_by_fragmentation",
        wake_posture="strongly_blocked",
        readiness_verdict="hold_for_operator_review",
        resume_ready=False,
    )
    assert continuity["basis_classification"] == "continuity_uncertainty_driven_re_evaluation"
    assert continuity["posture"] == "conservative_wake_or_re_entry_posture"

    no_basis = _resolve_basis(
        tmp_path,
        watchpoint_class="no_watchpoint_needed",
        satisfaction_status="no_active_watchpoint",
        recommendation="no_re_evaluation_needed",
        resume_ready=False,
        readiness_verdict="not_ready",
    )
    assert no_basis["basis_classification"] == "no_current_re_evaluation_basis"


def test_current_re_evaluation_basis_brief_is_non_authoritative(tmp_path: Path) -> None:
    brief = _resolve_basis(
        tmp_path,
        watchpoint_class="await_new_proposal",
        satisfaction_status="watchpoint_satisfied",
        recommendation="rerun_delegated_judgment",
    )
    boundaries = brief.get("boundaries", {})
    assert boundaries.get("non_authoritative") is True
    assert boundaries.get("non_executing") is True
    assert boundaries.get("does_not_execute_or_route_work") is True
    assert brief.get("decision_power") == "none"
    assert brief.get("basis", {}).get("historical_honesty", {}).get("derived_from_existing_surfaces_only") is True


def test_current_re_evaluation_basis_brief_surface_is_in_scoped_lifecycle_diagnostic() -> None:
    source = inspect.getsource(scoped_lifecycle_diagnostic.build_scoped_lifecycle_diagnostic)
    assert "current_re_evaluation_basis_brief" in source
