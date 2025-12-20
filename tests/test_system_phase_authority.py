import pytest

pytestmark = pytest.mark.no_legacy_skip

from system_continuity import (
    CheckpointLedger,
    DriftSentinel,
    GuardViolation,
    HumanLens,
    PhaseGate,
    RollbackError,
    SelfUpdateOrchestrator,
    SystemPhase,
)


@pytest.fixture
def sample_checkpoint():
    ledger = CheckpointLedger()
    return ledger.snapshot(
        phase=SystemPhase.LOCAL_AUTONOMY,
        module_snapshots={"core": {"status": "ok"}},
        volatility={"mode": "stable"},
        assertions=[{"id": "a1", "confidence": 0.5}],
        inquiry_backlog=["why"],
        narrative_synopses=["story"],
        constraint_registry={"c1": True},
        schema_versions={"modules": "1.0"},
        note="baseline",
    )


def test_phase_guard_enforcement_blocks_violation():
    gate = PhaseGate()
    with pytest.raises(GuardViolation):
        gate.enforce("architecture_change")
    with pytest.raises(GuardViolation):
        gate.enforce("confidence_upgrade", target="HIGH")
    gate.transition(SystemPhase.ADVISORY_WINDOW)
    gate.enforce("architecture_change")
    with pytest.raises(GuardViolation):
        gate.transition(SystemPhase.LOCAL_AUTONOMY)


def test_checkpoint_write_restore_and_migration(sample_checkpoint):
    ledger = CheckpointLedger()
    ledger.snapshot(
        phase=sample_checkpoint.phase,
        module_snapshots=sample_checkpoint.module_snapshots,
        volatility=sample_checkpoint.volatility,
        assertions=sample_checkpoint.assertions,
        inquiry_backlog=sample_checkpoint.inquiry_backlog,
        narrative_synopses=sample_checkpoint.narrative_synopses,
        constraint_registry=sample_checkpoint.constraint_registry,
        schema_versions=sample_checkpoint.schema_versions,
        note="copy",
    )
    latest = ledger.latest()
    ledger.register_migration(latest.checkpoint_version, lambda state: state["schema_versions"].update({"modules": "2.0"}))
    restored = ledger.restore(latest.checkpoint_version)
    restored["module_snapshots"]["core"]["status"] = "mutated"
    again = ledger.restore(latest.checkpoint_version)
    assert again["module_snapshots"]["core"]["status"] == "ok"
    assert again["schema_versions"]["modules"] == "2.0"


def test_failed_update_triggers_rollback(sample_checkpoint):
    gate = PhaseGate(phase=SystemPhase.ADVISORY_WINDOW)
    orchestrator = SelfUpdateOrchestrator(gate, CheckpointLedger())
    modules = {"alpha": lambda: None}

    def bad_validator(state):
        raise ValueError("invariant broken")

    with pytest.raises(RollbackError):
        orchestrator.perform_update(
            modules=modules,
            module_snapshots=sample_checkpoint.module_snapshots,
            volatility=sample_checkpoint.volatility,
            assertions=sample_checkpoint.assertions,
            inquiry_backlog=sample_checkpoint.inquiry_backlog,
            narrative_synopses=sample_checkpoint.narrative_synopses,
            constraint_registry=sample_checkpoint.constraint_registry,
            schema_versions=sample_checkpoint.schema_versions,
            swapper=lambda: None,
            rehydrator=lambda state: state,
            validator=bad_validator,
            author="operator",
        )
    assert orchestrator.status["last_failure"] is not None
    assert orchestrator.status["brownout"] is True


def test_drift_sentinel_emits_events():
    sentinel = DriftSentinel()
    previous = {
        "beliefs": [{"id": "b1", "confidence": 0.2, "evidence": "log"}],
        "authorities": ["internal:core"],
        "constraint_registry": {"c1": True},
        "assertions": [{"id": "a1", "confidence": 0.1}],
        "narrative_synopses": ["long narrative"],
    }
    current = {
        "beliefs": [{"id": "b1", "confidence": 0.5, "evidence": "log"}],
        "authorities": ["internal:core", "external:peer"],
        "constraint_registry": {"c1": False},
        "assertions": [{"id": "a1", "confidence": 0.3}],
        "narrative_synopses": ["short"],
    }
    events = sentinel.scan(previous, current)
    kinds = {event["kind"] for event in events}
    assert "belief_hardening" in kinds
    assert "authority_expansion" in kinds
    assert "constraint_change" in kinds
    assert "assertion_confidence" in kinds
    assert "narrative_compression" in kinds


def test_brownout_recovery_integrity(sample_checkpoint):
    gate = PhaseGate(phase=SystemPhase.ADVISORY_WINDOW)
    ledger = CheckpointLedger()
    orchestrator = SelfUpdateOrchestrator(gate, ledger)
    modules = {"alpha": lambda: None, "beta": lambda: None}

    def validator(state):
        assert state["constraint_registry"]["c1"] is True

    executed = orchestrator.perform_update(
        modules=modules,
        module_snapshots=sample_checkpoint.module_snapshots,
        volatility=sample_checkpoint.volatility,
        assertions=sample_checkpoint.assertions,
        inquiry_backlog=sample_checkpoint.inquiry_backlog,
        narrative_synopses=sample_checkpoint.narrative_synopses,
        constraint_registry=sample_checkpoint.constraint_registry,
        schema_versions=sample_checkpoint.schema_versions,
        swapper=lambda: None,
        rehydrator=lambda state: state,
        validator=validator,
        author="operator",
        note="integrity check",
    )
    assert executed == sorted(modules)
    assert orchestrator.status["brownout"] is False
    assert gate.phase is SystemPhase.ADVISORY_WINDOW

    lens = HumanLens(
        checkpoint=ledger.latest(),
        posture="steady",
        open_questions=["none"],
        recent_revisions=["checkpointed"],
    )
    rendered = lens.render()
    assert "current_phase" in rendered
