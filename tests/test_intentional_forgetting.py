from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from log_utils import append_json, read_json
from sentientos import narrative_synthesis
from sentientos.authority_surface import build_authority_surface_snapshot, diff_authority_surfaces
from sentientos.cor import CORConfig, CORSubsystem, Hypothesis
from sentientos.governance.habit_inference import HabitConfig, HabitInferenceEngine, HabitObservation
from sentientos.governance.intentional_forgetting import IntentionalForgetRequest, IntentionalForgettingService
from sentientos.governance.routine_delegation import (
    RoutineAction,
    RoutineActionResult,
    RoutineCatalog,
    RoutineExecutor,
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
