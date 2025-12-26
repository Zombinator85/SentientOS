from __future__ import annotations

import json
from typing import Mapping

import pytest

from control_plane.enums import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from sentientos.cor import CORSubsystem
from sentientos.governance.routine_delegation import (
    RoutineAction,
    RoutineActionResult,
    RoutineApproval,
    RoutineCatalog,
    RoutineExecutor,
    RoutinePolicyViolation,
    RoutineRegistry,
    RoutineSpec,
    RoutineTrigger,
    make_routine_approval,
)
import task_executor


def _make_catalog(counter: dict[str, int], *, trigger_result: bool = True) -> RoutineCatalog:
    catalog = RoutineCatalog()

    def _trigger(_: Mapping[str, object]) -> bool:
        return trigger_result

    def _action(_: Mapping[str, object]) -> RoutineActionResult:
        counter["calls"] += 1
        return RoutineActionResult(outcome="ok", details={"ran": True}, affected_scopes=("lighting",))

    catalog.register_trigger(RoutineTrigger(trigger_id="trigger-always", description="always", predicate=_trigger))
    catalog.register_action(RoutineAction(action_id="action-lights", description="set lights", handler=_action))
    return catalog


def _make_conflict_catalog(counters: dict[str, int]) -> RoutineCatalog:
    catalog = RoutineCatalog()

    def _trigger(_: Mapping[str, object]) -> bool:
        return True

    def _action_a(_: Mapping[str, object]) -> RoutineActionResult:
        counters["a"] += 1
        return RoutineActionResult(outcome="ok", details={"ran": "a"}, affected_scopes=("lighting",))

    def _action_b(_: Mapping[str, object]) -> RoutineActionResult:
        counters["b"] += 1
        return RoutineActionResult(outcome="ok", details={"ran": "b"}, affected_scopes=("lighting",))

    catalog.register_trigger(RoutineTrigger(trigger_id="trigger-always", description="always", predicate=_trigger))
    catalog.register_action(
        RoutineAction(
            action_id="action-a",
            description="set lights warm",
            handler=_action_a,
            conflict_domains=("lighting",),
        )
    )
    catalog.register_action(
        RoutineAction(
            action_id="action-b",
            description="set lights cool",
            handler=_action_b,
            conflict_domains=("lighting",),
        )
    )
    return catalog


def _make_spec(*, routine_id: str = "routine-1", authority_impact: str = "none") -> RoutineSpec:
    return RoutineSpec(
        routine_id=routine_id,
        trigger_id="trigger-always",
        trigger_description="time == 18:00",
        action_id="action-lights",
        action_description="set_lights(color=yellow)",
        scope=("lighting",),
        reversibility="guaranteed",
        authority_impact=authority_impact,
    )


def _make_approval(spec: RoutineSpec) -> RoutineApproval:
    return make_routine_approval(
        approved_by="operator",
        summary=spec.action_description,
        trigger_summary=spec.trigger_description,
        scope_summary=spec.scope,
    )


def _make_task(task_id: str) -> task_executor.Task:
    steps = (task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="ok")),)
    return task_executor.Task(task_id=task_id, objective="test", steps=steps)


def _make_authorization() -> AuthorizationRecord:
    return AuthorizationRecord.create(
        request_type=RequestType.TASK_EXECUTION,
        requester_id="operator",
        intent_hash="intent",
        context_hash="context",
        policy_version="v1-static",
        decision=Decision.ALLOW,
        reason=ReasonCode.OK,
        metadata={},
    )


def _make_admission_token(task: task_executor.Task) -> task_executor.AdmissionToken:
    provenance = task_executor.AuthorityProvenance(
        authority_source="operator",
        authority_scope="policy:test",
        authority_context_id="node-1",
        authority_reason="OK",
    )
    authorization = _make_authorization()
    canonical_request = task_executor.canonicalise_task_request(
        task=task, authorization=authorization, provenance=provenance, declared_inputs=None
    )
    fingerprint = task_executor.request_fingerprint_from_canonical(canonical_request)
    return task_executor.AdmissionToken(
        task_id=task.task_id,
        provenance=provenance,
        request_fingerprint=fingerprint,
    )


def test_routines_only_run_after_approval(tmp_path) -> None:
    counter = {"calls": 0}
    catalog = _make_catalog(counter)
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    executor = RoutineExecutor(log_path=tmp_path / "routine_log.jsonl")
    spec = _make_spec()

    executor.run(registry.list_routines(), catalog, {"time": "18:00"})
    assert counter["calls"] == 0

    registry.approve_routine(spec, _make_approval(spec))
    executor.run(registry.list_routines(), catalog, {"time": "18:00"})
    assert counter["calls"] == 1


def test_revocation_halts_execution_immediately(tmp_path) -> None:
    counter = {"calls": 0}
    catalog = _make_catalog(counter)
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    executor = RoutineExecutor(log_path=tmp_path / "routine_log.jsonl")
    spec = _make_spec()
    registry.approve_routine(spec, _make_approval(spec))

    executor.run(registry.list_routines(), catalog, {"time": "18:00"})
    assert counter["calls"] == 1

    registry.revoke_routine(spec.routine_id, revoked_by="operator", reason="pause")
    executor.run(registry.list_routines(), catalog, {"time": "18:00"})
    assert counter["calls"] == 1


def test_routines_cannot_escalate_authority(tmp_path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    spec = _make_spec(authority_impact="global")
    with pytest.raises(RoutinePolicyViolation):
        registry.approve_routine(spec, _make_approval(spec))


def test_cor_proposals_do_not_auto_create_routines(tmp_path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    cor = CORSubsystem()
    spec = _make_spec()

    proposal = cor.propose_routine("Evening lights", spec)
    assert proposal.summary == "Evening lights"
    assert registry.list_routines() == ()


def test_routine_execution_does_not_affect_task_replay_equivalence(tmp_path) -> None:
    counter = {"calls": 0}
    catalog = _make_catalog(counter)
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    executor = RoutineExecutor(log_path=tmp_path / "routine_log.jsonl")
    spec = _make_spec(routine_id="routine-2")
    registry.approve_routine(spec, _make_approval(spec))

    task = _make_task("task-1")
    token = _make_admission_token(task)
    authorization = _make_authorization()
    canonical_before = task_executor.canonicalise_task_request(
        task=task,
        authorization=authorization,
        provenance=token.provenance,
        declared_inputs=None,
    )
    fingerprint_before = task_executor.request_fingerprint_from_canonical(canonical_before)

    executor.run(registry.list_routines(), catalog, {"time": "18:00"})

    canonical_after = task_executor.canonicalise_task_request(
        task=task,
        authorization=authorization,
        provenance=token.provenance,
        declared_inputs=None,
    )
    fingerprint_after = task_executor.request_fingerprint_from_canonical(canonical_after)
    assert fingerprint_before.value == fingerprint_after.value


def test_conflict_resolution_uses_operator_precedence(tmp_path) -> None:
    counters = {"a": 0, "b": 0}
    catalog = _make_conflict_catalog(counters)
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    executor = RoutineExecutor(log_path=tmp_path / "routine_log.jsonl")

    routine_a = RoutineSpec(
        routine_id="routine-a",
        trigger_id="trigger-always",
        trigger_description="always",
        action_id="action-a",
        action_description="set_lights(warm)",
        scope=("lighting",),
        reversibility="guaranteed",
        authority_impact="none",
        priority=10,
    )
    routine_b = RoutineSpec(
        routine_id="routine-b",
        trigger_id="trigger-always",
        trigger_description="always",
        action_id="action-b",
        action_description="set_lights(cool)",
        scope=("lighting",),
        reversibility="guaranteed",
        authority_impact="none",
        priority=5,
    )

    registry.approve_routine(routine_a, _make_approval(routine_a))
    registry.approve_routine(routine_b, _make_approval(routine_b))
    executor.run(registry.list_routines(), catalog, {"time": "18:00", "operator_priority": True})

    assert counters["a"] == 1
    assert counters["b"] == 0


def test_conflict_resolution_prefers_specific_routine(tmp_path) -> None:
    counters = {"a": 0, "b": 0}
    catalog = _make_conflict_catalog(counters)
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    executor = RoutineExecutor(log_path=tmp_path / "routine_log.jsonl")

    routine_a = RoutineSpec(
        routine_id="routine-specific",
        trigger_id="trigger-always",
        trigger_description="movie_mode == true",
        action_id="action-a",
        action_description="set_lights(dim)",
        scope=("lighting",),
        reversibility="guaranteed",
        authority_impact="none",
        trigger_specificity=10,
    )
    routine_b = RoutineSpec(
        routine_id="routine-general",
        trigger_id="trigger-always",
        trigger_description="evening",
        action_id="action-b",
        action_description="set_lights(bright)",
        scope=("lighting",),
        reversibility="guaranteed",
        authority_impact="none",
        trigger_specificity=1,
    )

    registry.approve_routine(routine_a, _make_approval(routine_a))
    registry.approve_routine(routine_b, _make_approval(routine_b))
    executor.run(registry.list_routines(), catalog, {"time": "18:00"})

    assert counters["a"] == 1
    assert counters["b"] == 0


def test_conflict_resolution_prefers_time_bound_routine(tmp_path) -> None:
    counters = {"a": 0, "b": 0}
    catalog = _make_conflict_catalog(counters)
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    executor = RoutineExecutor(log_path=tmp_path / "routine_log.jsonl")

    routine_a = RoutineSpec(
        routine_id="routine-timebound",
        trigger_id="trigger-always",
        trigger_description="between 18:00-19:00",
        action_id="action-a",
        action_description="set_lights(dim)",
        scope=("lighting",),
        reversibility="guaranteed",
        authority_impact="none",
        time_window=("18:00", "19:00"),
    )
    routine_b = RoutineSpec(
        routine_id="routine-continuous",
        trigger_id="trigger-always",
        trigger_description="evening",
        action_id="action-b",
        action_description="set_lights(bright)",
        scope=("lighting",),
        reversibility="guaranteed",
        authority_impact="none",
    )

    registry.approve_routine(routine_a, _make_approval(routine_a))
    registry.approve_routine(routine_b, _make_approval(routine_b))
    executor.run(registry.list_routines(), catalog, {"time": "18:30"})

    assert counters["a"] == 1
    assert counters["b"] == 0


def test_conflict_pause_prompts_once_and_replays_deterministically(tmp_path) -> None:
    counters = {"a": 0, "b": 0}
    log_path = tmp_path / "routine_log.jsonl"
    catalog = _make_conflict_catalog(counters)
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=log_path)
    executor = RoutineExecutor(log_path=log_path)

    routine_a = RoutineSpec(
        routine_id="routine-1",
        trigger_id="trigger-always",
        trigger_description="always",
        action_id="action-a",
        action_description="set_lights(warm)",
        scope=("lighting",),
        reversibility="guaranteed",
        authority_impact="none",
    )
    routine_b = RoutineSpec(
        routine_id="routine-2",
        trigger_id="trigger-always",
        trigger_description="always",
        action_id="action-b",
        action_description="set_lights(cool)",
        scope=("lighting",),
        reversibility="guaranteed",
        authority_impact="none",
    )

    registry.approve_routine(routine_a, _make_approval(routine_a))
    registry.approve_routine(routine_b, _make_approval(routine_b))

    executor.run(registry.list_routines(), catalog, {"time": "18:00"})
    executor.run(registry.list_routines(), catalog, {"time": "18:00"})

    assert counters["a"] == 0
    assert counters["b"] == 0

    logs = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    prompts = [entry for entry in logs if entry.get("event") == "routine_conflict_prompt"]
    detections = [entry for entry in logs if entry.get("event") == "routine_conflict_detected"]
    assert len(prompts) == 1
    assert len(detections) == 2
    assert detections[0]["conflict_id"] == detections[1]["conflict_id"]
