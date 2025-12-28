from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from log_utils import append_json, read_json
from sentientos import narrative_synthesis
from sentientos.authority_surface import build_authority_surface_snapshot, diff_authority_surfaces
from sentientos.cor import CORConfig, CORSubsystem, Hypothesis
from sentientos.governance.habit_inference import HabitConfig, HabitInferenceEngine, HabitObservation
from sentientos.governance.intentional_forgetting import (
    ForgetDiff,
    ForgetBoundaryDecision,
    ForgetBoundaryPreview,
    ForgetCommitPhase,
    BoundaryRefusal,
    IntentionalForgetRequest,
    IntentionalForgettingService,
    InvariantViolation,
    read_forget_log,
    read_forget_pressure,
)
from sentientos.governance.routine_delegation import (
    RoutineAction,
    RoutineActionResult,
    RoutineCatalog,
    RoutineExecutor,
    RoutineDefinition,
    RoutineRegistry,
    RoutineSpec,
    RoutineTrigger,
    make_routine_approval,
)
from sentientos.governance.semantic_habit_class import SemanticHabitClassManager

pytestmark = pytest.mark.no_legacy_skip


def _habit_observation(timestamp: str) -> HabitObservation:
    return HabitObservation(
        action_id="action-1",
        action_description="Toggle lights",
        trigger_id="trigger-1",
        trigger_description="Sunset",
        scope=("lighting",),
        reversibility="bounded",
        authority_impact="none",
        timestamp=timestamp,
        context={"room": "office"},
        outcome={"status": "ok"},
    )


def _routine_spec(routine_id: str) -> RoutineSpec:
    return RoutineSpec(
        routine_id=routine_id,
        trigger_id="trigger-1",
        trigger_description="Sunset",
        action_id="action-1",
        action_description="Toggle lights",
        scope=("lighting",),
        reversibility="bounded",
        authority_impact="none",
        expiration=None,
        priority=None,
        precedence_group=None,
        group_priority=None,
        precedence_conditions=(),
        trigger_specificity=0,
        time_window=None,
    )


def _committed_forget_entries(path: Path) -> list[dict[str, object]]:
    return [entry for entry in read_forget_log(path) if entry.get("event") == "intentional_forget"]


def _phase_entries(path: Path) -> list[dict[str, object]]:
    return [entry for entry in read_forget_log(path) if entry.get("event") == "intentional_forget_phase"]


def _proof_entries(path: Path) -> list[dict[str, object]]:
    return [
        entry
        for entry in read_forget_log(path)
        if entry.get("event") == "intentional_forget_rollback_proof"
    ]


def _refusal_entries(path: Path) -> list[dict[str, object]]:
    return [
        entry for entry in read_forget_log(path) if entry.get("event") == "intentional_forget_refusal"
    ]


def _pressure_entries(path: Path) -> list[dict[str, object]]:
    return [
        entry for entry in read_forget_log(path) if entry.get("event") == "intentional_forget_pressure"
    ]


def test_forget_habit_prevents_reproposal(tmp_path: Path) -> None:
    config = HabitConfig(
        min_occurrences=2,
        max_interval_stddev_seconds=99999.0,
        max_mean_interval_seconds=99999.0,
        proposal_confidence_threshold=0.1,
    )
    engine = HabitInferenceEngine(config=config)
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    service = IntentionalForgettingService(
        routine_registry=registry,
        habit_engine=engine,
        log_path=tmp_path / "forget_log.jsonl",
    )
    now = datetime.now(timezone.utc)
    proposal = engine.record_observation(_habit_observation(now.isoformat()))
    assert proposal is None
    proposal = engine.record_observation(_habit_observation((now + timedelta(seconds=10)).isoformat()))
    assert proposal is not None

    service.forget(
        IntentionalForgetRequest(
            target_type="habit",
            target_id=proposal.habit_id,
            forget_scope="exact",
            proof_level="structural",
        )
    )
    assert proposal.habit_id in engine.list_forgotten()

    proposal = engine.record_observation(_habit_observation((now + timedelta(seconds=20)).isoformat()))
    assert proposal is None


def test_forget_cor_blocks_resurrection(tmp_path: Path) -> None:
    config = CORConfig(
        proposal_confidence_threshold=0.0,
        hypothesis_decay_window_seconds=0,
        hypothesis_expiry_seconds=99999,
        proposal_suppression_seconds=0,
    )
    cor = CORSubsystem(config=config)
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    service = IntentionalForgettingService(
        routine_registry=registry,
        cor_subsystem=cor,
        log_path=tmp_path / "forget_log.jsonl",
    )
    hypothesis = Hypothesis(hypothesis="Focus email window", confidence=0.9)
    assert cor.ingest_hypothesis(hypothesis) is not None

    service.forget(
        IntentionalForgetRequest(
            target_type="cor",
            target_id=hypothesis.hypothesis,
            forget_scope="exact",
            proof_level="structural",
        )
    )

    assert cor.ingest_hypothesis(hypothesis) is None
    assert hypothesis.hypothesis not in cor.list_hypotheses()


def test_cascaded_class_forget_removes_routines(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec_one = _routine_spec("routine-1")
    spec_two = _routine_spec("routine-2")
    approval_one = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec_one.trigger_description,
        scope_summary=spec_one.scope,
    )
    approval_two = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec_two.trigger_description,
        scope_summary=spec_two.scope,
    )
    registry.approve_routine(spec_one, approval_one)
    registry.approve_routine(spec_two, approval_two)

    manager = SemanticHabitClassManager(registry=registry, log_path=str(tmp_path / "classes.jsonl"))
    manager.create_class(
        "Focus",
        routine_ids=(spec_one.routine_id, spec_two.routine_id),
        created_by="operator",
        description="Focus routines",
    )

    service = IntentionalForgettingService(
        routine_registry=registry,
        class_manager=manager,
        log_path=tmp_path / "forget_log.jsonl",
    )
    service.forget(
        IntentionalForgetRequest(
            target_type="class",
            target_id="Focus",
            forget_scope="cascade",
            proof_level="structural",
        )
    )

    assert registry.list_routines() == ()
    assert manager.list_classes() == ()
    assert "Focus" in manager.list_forgotten()


def test_authority_diff_reports_removal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sentientos.governance.routine_delegation as routine_delegation

    monkeypatch.setattr(routine_delegation, "DEFAULT_STORE_PATH", tmp_path / "routines.json")
    monkeypatch.setattr(routine_delegation, "DEFAULT_LOG_PATH", tmp_path / "routine_log.jsonl")
    registry = RoutineRegistry()
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    before = build_authority_surface_snapshot()

    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    service.forget(
        IntentionalForgetRequest(
            target_type="routine",
            target_id=spec.routine_id,
            forget_scope="exact",
            proof_level="structural",
        )
    )
    after = build_authority_surface_snapshot()
    diff = diff_authority_surfaces(before, after)
    removed = [
        change
        for change in diff.get("changes", [])
        if change.get("change_type") == "remove" and "removed from delegation registry" in change.get("description", "")
    ]
    assert removed


def test_forgetting_prevents_execution_after_forget(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    executor = RoutineExecutor(log_path=tmp_path / "routine_log.jsonl")
    catalog = RoutineCatalog()

    def action_handler(_: dict[str, object]) -> RoutineActionResult:
        return RoutineActionResult(outcome="ok", affected_scopes=("lighting",))

    catalog.register_trigger(RoutineTrigger(trigger_id="trigger-1", description="Sunset", predicate=lambda _: True))
    catalog.register_action(RoutineAction(action_id="action-1", description="Toggle lights", handler=action_handler))
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    executor.run(registry.list_routines(), catalog, {"time": "18:00"})

    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    service.forget(
        IntentionalForgetRequest(
            target_type="routine",
            target_id=spec.routine_id,
            forget_scope="exact",
            proof_level="structural",
        )
    )
    executor.run(registry.list_routines(), catalog, {"time": "18:00"})
    entries = read_json(tmp_path / "routine_log.jsonl")
    executions = [entry for entry in entries if entry.get("event") == "delegated_execution"]
    assert len(executions) == 1


def test_narrative_mentions_forgetting_without_details(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    forget_log = tmp_path / "forget_log.jsonl"
    append_json(
        forget_log,
        {
            "event": "intentional_forget",
            "target_type": "routine",
            "target": "routine-1",
            "cascade": False,
            "authority": "operator",
            "proof_level": "structural",
            "post_state_hash": "hash",
            "redacted_target": False,
        },
    )
    monkeypatch.setattr(narrative_synthesis, "FORGET_LOG_PATH", str(forget_log))

    summary = narrative_synthesis.build_narrative_summary()
    lines = [line for section in summary["sections"] for line in section.get("lines", [])]
    assert any("intentionally forgotten" in line for line in lines)
    assert "routine-1" not in " ".join(lines)


def test_simulation_does_not_mutate_state(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    manager = SemanticHabitClassManager(registry=registry, log_path=str(tmp_path / "classes.jsonl"))
    manager.create_class(
        "Focus",
        routine_ids=(spec.routine_id,),
        created_by="operator",
        description="Focus routines",
    )
    service = IntentionalForgettingService(
        routine_registry=registry,
        class_manager=manager,
        log_path=tmp_path / "forget_log.jsonl",
    )

    diff = service.simulate_forget(
        IntentionalForgetRequest(
            target_type="routine",
            target_id=spec.routine_id,
            forget_scope="cascade",
            proof_level="structural",
        )
    )
    assert isinstance(diff, ForgetDiff)
    assert registry.get_routine(spec.routine_id) is not None
    assert manager.get_class("Focus") is not None
    assert read_forget_log(service.log_path) == []
    assert _proof_entries(service.log_path) == []


def test_simulation_matches_execution_effect(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec_one = _routine_spec("routine-1")
    spec_two = _routine_spec("routine-2")
    approval_one = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec_one.trigger_description,
        scope_summary=spec_one.scope,
    )
    approval_two = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec_two.trigger_description,
        scope_summary=spec_two.scope,
    )
    registry.approve_routine(spec_one, approval_one)
    registry.approve_routine(spec_two, approval_two)
    manager = SemanticHabitClassManager(registry=registry, log_path=str(tmp_path / "classes.jsonl"))
    manager.create_class(
        "Focus",
        routine_ids=(spec_one.routine_id, spec_two.routine_id),
        created_by="operator",
        description="Focus routines",
    )
    service = IntentionalForgettingService(
        routine_registry=registry,
        class_manager=manager,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="class",
        target_id="Focus",
        forget_scope="cascade",
        proof_level="structural",
    )
    diff = service.simulate_forget(request)
    result = service.forget(request)

    assert diff.state_hashes["after"] == result.post_state_hash
    assert tuple(sorted(diff.removals)) == tuple(sorted(result.impacted))


def test_simulation_reports_cascade_removals(tmp_path: Path) -> None:
    config = HabitConfig(
        min_occurrences=2,
        max_interval_stddev_seconds=99999.0,
        max_mean_interval_seconds=99999.0,
        proposal_confidence_threshold=0.1,
    )
    engine = HabitInferenceEngine(config=config)
    now = datetime.now(timezone.utc)
    engine.record_observation(_habit_observation(now.isoformat()))
    proposal = engine.record_observation(_habit_observation((now + timedelta(seconds=10)).isoformat()))
    assert proposal is not None

    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    routine_id = f"routine-{proposal.habit_id}"
    spec = _routine_spec(routine_id)
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        habit_engine=engine,
        log_path=tmp_path / "forget_log.jsonl",
    )
    diff = service.simulate_forget(
        IntentionalForgetRequest(
            target_type="habit",
            target_id=proposal.habit_id,
            forget_scope="cascade",
            proof_level="structural",
        )
    )
    assert f"routine:{routine_id}" in diff.cascaded_removals


def test_simulation_reports_blocked_targets(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    diff = service.simulate_forget(
        IntentionalForgetRequest(
            target_type="habit",
            target_id="habit-123",
            forget_scope="exact",
            proof_level="structural",
        )
    )
    assert diff.blocked
    assert diff.state_hashes["before"] == diff.state_hashes["after"]


def test_simulation_diff_is_deterministic(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    first = service.simulate_forget(request)
    second = service.simulate_forget(request)
    assert first.to_dict() == second.to_dict()


def test_rollback_proof_is_deterministic(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()

    def run(root: Path) -> dict[str, object]:
        registry = RoutineRegistry(store_path=root / "routines.json", log_path=root / "routine_log.jsonl")
        spec = _routine_spec("routine-1")
        approval = make_routine_approval(
            approved_by="operator",
            summary="Toggle lights at sunset",
            trigger_summary=spec.trigger_description,
            scope_summary=spec.scope,
        )
        registry.approve_routine(spec, approval)
        service = IntentionalForgettingService(
            routine_registry=registry,
            log_path=root / "forget_log.jsonl",
        )
        service.forget(
            IntentionalForgetRequest(
                target_type="routine",
                target_id=spec.routine_id,
                forget_scope="exact",
                proof_level="structural",
            )
        )
        proofs = _proof_entries(service.log_path)
        assert proofs
        return proofs[0]

    first = run(first_root)
    second = run(second_root)
    assert first.get("proof_hash") == second.get("proof_hash")
    assert first.get("authority_surface_hash") == second.get("authority_surface_hash")
    assert first.get("narrative_summary_hash") == second.get("narrative_summary_hash")
    assert first.get("semantic_domains") == second.get("semantic_domains")


def test_forget_tx_id_is_deterministic(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    first = service.simulate_forget(request)
    second = service.simulate_forget(request)
    assert first.forget_tx_id == second.forget_tx_id


def test_duplicate_execution_is_noop(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    first = service.forget(request)
    second = service.forget(request)

    assert second.replayed is True
    assert second.forget_tx_id == first.forget_tx_id
    committed_entries = _committed_forget_entries(service.log_path)
    assert committed_entries[0].get("forget_tx_id") == first.forget_tx_id
    assert len(committed_entries) == 1


def test_invariant_verification_blocks_reintroduction(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    service.forget(request)
    routine = RoutineDefinition(
        routine_id=spec.routine_id,
        trigger_id=spec.trigger_id,
        trigger_description=spec.trigger_description,
        action_id=spec.action_id,
        action_description=spec.action_description,
        scope=spec.scope,
        reversibility=spec.reversibility,
        authority_impact=spec.authority_impact,
        expiration=spec.expiration,
        priority=spec.priority,
        precedence_group=spec.precedence_group,
        group_priority=spec.group_priority,
        precedence_conditions=spec.precedence_conditions,
        trigger_specificity=spec.trigger_specificity,
        time_window=spec.time_window,
        approval=approval,
        created_at=approval.approved_at,
        created_by=approval.approved_by,
        policy=spec.policy_snapshot(),
    )
    registry._state["routines"][spec.routine_id] = routine.to_dict()
    with pytest.raises(InvariantViolation, match="reintroduced_routine"):
        service.verify_post_commit_invariants()


def test_invariant_verification_is_stable_after_restart(tmp_path: Path) -> None:
    store_path = tmp_path / "routines.json"
    log_path = tmp_path / "routine_log.jsonl"
    registry = RoutineRegistry(store_path=store_path, log_path=log_path)
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    service.forget(
        IntentionalForgetRequest(
            target_type="routine",
            target_id=spec.routine_id,
            forget_scope="exact",
            proof_level="structural",
        )
    )
    reloaded = RoutineRegistry(store_path=store_path, log_path=log_path)
    replay_service = IntentionalForgettingService(
        routine_registry=reloaded,
        log_path=tmp_path / "forget_log.jsonl",
    )
    replay_service.verify_post_commit_invariants()
    replay_service.verify_post_commit_invariants()


def test_phase_progression_records_transitions(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )

    service.forget(request)

    phases = [entry.get("phase") for entry in _phase_entries(service.log_path)]
    assert phases == [
        ForgetCommitPhase.PREPARED.value,
        ForgetCommitPhase.APPLYING.value,
        ForgetCommitPhase.COMMITTED.value,
    ]


def test_recovery_reapplies_applying_phase(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    forget_tx_id = service.simulate_forget(request).forget_tx_id
    append_json(
        service.log_path,
        {
            "event": "intentional_forget_phase",
            "phase": ForgetCommitPhase.PREPARED.value,
            "forget_tx_id": forget_tx_id,
            "target_type": request.target_type,
            "target": request.target_id,
            "forget_scope": request.forget_scope,
            "proof_level": request.proof_level,
            "authority": "operator",
            "redacted_target": False,
        },
    )
    append_json(
        service.log_path,
        {
            "event": "intentional_forget_phase",
            "phase": ForgetCommitPhase.APPLYING.value,
            "forget_tx_id": forget_tx_id,
            "target_type": request.target_type,
            "target": request.target_id,
            "forget_scope": request.forget_scope,
            "proof_level": request.proof_level,
            "authority": "operator",
            "redacted_target": False,
        },
    )

    result = service.forget(request)

    assert result.replayed is True
    assert registry.list_routines() == ()
    assert _committed_forget_entries(service.log_path)


def test_replay_after_abort_retries(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    forget_tx_id = service.simulate_forget(request).forget_tx_id
    append_json(
        service.log_path,
        {
            "event": "intentional_forget_phase",
            "phase": ForgetCommitPhase.ABORTED.value,
            "forget_tx_id": forget_tx_id,
            "target_type": request.target_type,
            "target": request.target_id,
            "forget_scope": request.forget_scope,
            "proof_level": request.proof_level,
            "authority": "operator",
            "redacted_target": False,
        },
    )

    result = service.forget(request)

    assert result.replayed is False
    assert registry.list_routines() == ()
    assert _committed_forget_entries(service.log_path)


def test_simulation_reports_phase_state(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    forget_tx_id = service.simulate_forget(request).forget_tx_id
    append_json(
        service.log_path,
        {
            "event": "intentional_forget_phase",
            "phase": ForgetCommitPhase.PREPARED.value,
            "forget_tx_id": forget_tx_id,
            "target_type": request.target_type,
            "target": request.target_id,
            "forget_scope": request.forget_scope,
            "proof_level": request.proof_level,
            "authority": "operator",
            "redacted_target": False,
        },
    )

    diff = service.simulate_forget(request)

    assert diff.phase == ForgetCommitPhase.PREPARED.value
    assert diff.execution_status == "pending"
def test_simulation_reports_prior_execution(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    service.forget(request)
    diff = service.simulate_forget(request)
    assert diff.replay_status == "already_applied"


def test_failed_execution_does_not_register_tx(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="habit",
        target_id="habit-1",
        forget_scope="exact",
        proof_level="structural",
    )
    with pytest.raises(ValueError, match="Habit inference engine is required"):
        service.forget(request)
    assert _committed_forget_entries(service.log_path) == []
    phase_entries = _phase_entries(service.log_path)
    assert phase_entries
    assert phase_entries[-1].get("phase") == ForgetCommitPhase.ABORTED.value


def test_forget_tx_id_stable_across_serialization(tmp_path: Path) -> None:
    store_path = tmp_path / "routines.json"
    log_path = tmp_path / "routine_log.jsonl"
    registry = RoutineRegistry(store_path=store_path, log_path=log_path)
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)

    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    first = service.simulate_forget(request)

    reloaded = RoutineRegistry(store_path=store_path, log_path=log_path)
    replay_service = IntentionalForgettingService(
        routine_registry=reloaded,
        log_path=tmp_path / "forget_log.jsonl",
    )
    second = replay_service.simulate_forget(request)
    assert first.forget_tx_id == second.forget_tx_id


class _BoundaryRefuser:
    name = "memory"

    def preview_forget(self, request: IntentionalForgetRequest) -> ForgetBoundaryPreview:
        return ForgetBoundaryPreview(
            subsystem=self.name,
            decision=ForgetBoundaryDecision.REFUSE,
            reason="memory_anchor",
        )

    def verify_post_commit(self, state: dict[str, object]) -> None:
        return None


class _BoundaryDeferrer:
    name = "cognition"

    def preview_forget(self, request: IntentionalForgetRequest) -> ForgetBoundaryPreview:
        return ForgetBoundaryPreview(
            subsystem=self.name,
            decision=ForgetBoundaryDecision.DEFER,
            reason="cognitive_lock",
        )

    def verify_post_commit(self, state: dict[str, object]) -> None:
        return None


def test_boundary_refusal_blocks_execution(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryRefuser(),),
    )

    with pytest.raises(BoundaryRefusal):
        service.forget(
            IntentionalForgetRequest(
                target_type="routine",
                target_id=spec.routine_id,
                forget_scope="exact",
                proof_level="structural",
            )
        )

    assert registry.get_routine(spec.routine_id) is not None
    assert _committed_forget_entries(service.log_path) == []
    assert _proof_entries(service.log_path) == []
    refusals = _refusal_entries(service.log_path)
    assert refusals


def test_boundary_defer_requires_acknowledgment(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryDeferrer(),),
    )

    with pytest.raises(BoundaryRefusal):
        service.forget(
            IntentionalForgetRequest(
                target_type="routine",
                target_id=spec.routine_id,
                forget_scope="exact",
                proof_level="structural",
            )
        )
    assert _committed_forget_entries(service.log_path) == []
    assert _proof_entries(service.log_path) == []

    result = service.forget(
        IntentionalForgetRequest(
            target_type="routine",
            target_id=spec.routine_id,
            forget_scope="exact",
            proof_level="structural",
            defer_acknowledged=True,
        )
    )
    assert result.forget_tx_id
    assert _committed_forget_entries(service.log_path)


def test_pressure_created_on_defer(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryDeferrer(),),
    )

    with pytest.raises(BoundaryRefusal):
        service.forget(
            IntentionalForgetRequest(
                target_type="routine",
                target_id=spec.routine_id,
                forget_scope="exact",
                proof_level="structural",
            )
        )

    pressure_entries = _pressure_entries(service.log_path)
    assert pressure_entries
    assert pressure_entries[-1].get("status") == "active"
    assert pressure_entries[-1].get("phase") == "deferred"


def test_pressure_deduplicates_on_reproposal(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryDeferrer(),),
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )

    with pytest.raises(BoundaryRefusal):
        service.forget(request)
    with pytest.raises(BoundaryRefusal):
        service.forget(request)

    assert len(_pressure_entries(service.log_path)) == 1


def test_pressure_persists_across_restart(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryDeferrer(),),
    )
    with pytest.raises(BoundaryRefusal):
        service.forget(
            IntentionalForgetRequest(
                target_type="routine",
                target_id=spec.routine_id,
                forget_scope="exact",
                proof_level="structural",
            )
        )

    reloaded = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryDeferrer(),),
    )
    pressure = read_forget_pressure(reloaded.log_path)
    assert pressure


def test_reconciliation_clears_pressure(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryDeferrer(),),
    )
    with pytest.raises(BoundaryRefusal):
        service.forget(
            IntentionalForgetRequest(
                target_type="routine",
                target_id=spec.routine_id,
                forget_scope="exact",
                proof_level="structural",
            )
        )

    reconciling = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(),
    )
    results = reconciling.reconcile_forgetting_pressure()
    assert results[0].get("status") == "cleared"
    assert read_forget_pressure(reconciling.log_path) == []


def test_reconciliation_maintains_pressure(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryDeferrer(),),
    )
    with pytest.raises(BoundaryRefusal):
        service.forget(
            IntentionalForgetRequest(
                target_type="routine",
                target_id=spec.routine_id,
                forget_scope="exact",
                proof_level="structural",
            )
        )

    results = service.reconcile_forgetting_pressure()
    assert results[0].get("status") == "blocked"
    assert read_forget_pressure(service.log_path)


def test_simulation_reports_pressure_state(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryDeferrer(),),
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    with pytest.raises(BoundaryRefusal):
        service.forget(request)

    diff = service.simulate_forget(request)
    assert diff.pressure


def test_simulation_matches_boundary_refusal(tmp_path: Path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _routine_spec("routine-1")
    approval = make_routine_approval(
        approved_by="operator",
        summary="Toggle lights at sunset",
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )
    registry.approve_routine(spec, approval)
    service = IntentionalForgettingService(
        routine_registry=registry,
        log_path=tmp_path / "forget_log.jsonl",
        boundary_contracts=(_BoundaryRefuser(),),
    )
    request = IntentionalForgetRequest(
        target_type="routine",
        target_id=spec.routine_id,
        forget_scope="exact",
        proof_level="structural",
    )
    diff = service.simulate_forget(request)
    assert diff.boundary_previews
    assert diff.blocked
    with pytest.raises(BoundaryRefusal):
        service.forget(request)
