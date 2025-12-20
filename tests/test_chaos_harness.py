from __future__ import annotations

import pytest

from sentientos.chaos_harness import (
    ChaosExerciseRunner,
    ChaosScenario,
    ChaosScenarioRegistry,
    ExpectedPosture,
)
from system_continuity import CheckpointLedger, PhaseGate, SystemPhase

pytestmark = pytest.mark.no_legacy_skip


def _base_state():
    return {
        "module_snapshots": {"core": {"status": "ok"}},
        "volatility": {"mode": "steady"},
        "assertions": [{"id": "a1", "confidence": 0.2}],
        "inquiry_backlog": ["why"],
        "narrative_synopses": ["story"],
        "constraint_registry": {"c1": True},
        "schema_versions": {"modules": "1.0"},
        "routing": {"core": "primary"},
    }


def _scenario(name: str, category: str = "load") -> ChaosScenario:
    return ChaosScenario(
        version=1,
        name=name,
        category=category,
        injected_signals=("pressure", "throttle"),
        expected_posture=ExpectedPosture(
            phase=SystemPhase.LOCAL_AUTONOMY,
            volatility={"mode": "steady"},
            routing={"core": "primary"},
        ),
        duration=1.0,
        success_criteria=("recovered", "logged"),
    )


def test_scenario_execution_is_deterministic_and_recorded():
    gate = PhaseGate()
    ledger = CheckpointLedger()
    runner = ChaosExerciseRunner(
        gate,
        ledger,
        base_state=_base_state(),
        authorities=["internal:core"],
        beliefs=[{"id": "b1", "confidence": 0.1, "evidence": "log"}],
    )
    registry = ChaosScenarioRegistry()
    registry.register(_scenario("load-surge"))

    first = runner.run(registry.latest("load-surge"))
    second = runner.run(registry.latest("load-surge"))

    assert first.applied_signals == second.applied_signals == ("pressure", "throttle")
    assert first.routing == second.routing
    assert first.entered_brownout is True
    assert any("BROWNOUT" in phase for _, phase, _ in first.transitions)


def test_brownout_recovery_restores_phase_and_checkpoint():
    gate = PhaseGate()
    ledger = CheckpointLedger()
    runner = ChaosExerciseRunner(gate, ledger, base_state=_base_state())
    scenario = _scenario("outage-drill", category="outage")

    record = runner.run(scenario)

    assert gate.phase is SystemPhase.LOCAL_AUTONOMY
    restored = ledger.restore(record.checkpoint_version)
    assert restored["constraint_registry"] == {"c1": True}
    assert restored["schema_versions"] == {"modules": "1.0"}


def test_burn_in_cycles_capture_summaries_without_drift():
    gate = PhaseGate()
    ledger = CheckpointLedger()
    runner = ChaosExerciseRunner(
        gate,
        ledger,
        base_state=_base_state(),
        authorities=["internal:core"],
        beliefs=[{"id": "b1", "confidence": 0.05, "evidence": "log"}],
    )
    registry = ChaosScenarioRegistry()
    registry.register(_scenario("scarcity-loop", category="scarcity"))

    lens = runner.run_burn_in(registry, cycles=2, unattended=True)

    assert lens.data["system_posture"] == "burn-in"
    assert len(runner.records) == 2
    assert gate.phase is SystemPhase.LOCAL_AUTONOMY


def test_idempotent_replay_does_not_expand_authority():
    gate = PhaseGate()
    ledger = CheckpointLedger()
    runner = ChaosExerciseRunner(
        gate,
        ledger,
        base_state=_base_state(),
        authorities=["internal:core"],
    )
    scenario = _scenario("latency-drill", category="latency")

    first = runner.run(scenario)
    second = runner.run(scenario)

    assert first.applied_signals == second.applied_signals
    assert ledger.restore(second.checkpoint_version)["constraint_registry"] == {"c1": True}
    assert gate.phase is SystemPhase.LOCAL_AUTONOMY
