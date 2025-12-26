from __future__ import annotations

import task_executor

from control_plane.enums import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from sentientos.cor import CORSubsystem
from sentientos.governance.routine_delegation import RoutineRegistry
from sentientos.ssu import SSUConfig, SymbolicScreenUnderstanding


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


def _make_task(task_id: str) -> task_executor.Task:
    steps = (task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload(note="ok")),)
    return task_executor.Task(task_id=task_id, objective="test", steps=steps)


def _make_admission_token(task: task_executor.Task) -> task_executor.AdmissionToken:
    provenance = task_executor.AuthorityProvenance(
        authority_source="operator",
        authority_scope="policy:test",
        authority_context_id="node-1",
        authority_reason="OK",
    )
    authorization = _make_authorization()
    canonical_request = task_executor.canonicalise_task_request(
        task=task,
        authorization=authorization,
        provenance=provenance,
        declared_inputs=None,
    )
    fingerprint = task_executor.request_fingerprint_from_canonical(canonical_request)
    return task_executor.AdmissionToken(
        task_id=task.task_id,
        provenance=provenance,
        request_fingerprint=fingerprint,
    )


def _base_observation() -> dict[str, object]:
    return {
        "timestamp": "2025-09-07T12:00:00+00:00",
        "app": "Steam",
        "window_title": "Steam - Library",
        "elements": [
            {
                "element_type": "button",
                "label": "Play",
                "state": "disabled",
                "confidence": 0.97,
            }
        ],
    }


def test_ssu_symbols_are_non_authoritative() -> None:
    ssu = SymbolicScreenUnderstanding()
    symbolic = ssu.extract(_base_observation())

    assert symbolic.degraded is False
    assert symbolic.symbols
    for symbol in symbolic.symbols:
        assert symbol.authority == "none"

    event = ssu.build_observation_event(_base_observation())
    assert event.content_type == "symbolic"
    assert event.authority == "none"

    hypothesis = ssu.build_hypothesis_from_symbols(
        "Observed disabled button",
        tuple(symbolic.symbols),
        confidence=0.9,
    )
    assert hypothesis.actionability == "proposal_only"


def test_ssu_confidence_thresholds_enforce_degradation() -> None:
    config = SSUConfig(min_confidence=0.7, proposal_confidence_threshold=0.9)
    ssu = SymbolicScreenUnderstanding(config=config)
    observation = {
        "app": "Launcher",
        "elements": [
            {"element_type": "button", "label": "Launch", "state": "enabled", "confidence": 0.65}
        ],
    }

    symbolic = ssu.extract(observation)
    assert all(symbol.tentative for symbol in symbolic.symbols)
    assert ssu.symbols_for_proposal(symbolic) == []


def test_ssu_adversarial_ui_does_not_trigger_execution(tmp_path) -> None:
    registry = RoutineRegistry(store_path=tmp_path / "routines.json", log_path=tmp_path / "routine_log.jsonl")
    cor = CORSubsystem()
    ssu = SymbolicScreenUnderstanding()

    observation = {
        "app": "Console",
        "window_title": "Danger Panel",
        "elements": [
            {
                "element_type": "button",
                "label": "Delete All Data",
                "state": "enabled",
                "confidence": 0.99,
            }
        ],
    }
    event = ssu.build_observation_event(observation)
    cor.ingest_observation(event)

    assert registry.list_routines() == ()


def test_cor_proposals_can_reference_symbols() -> None:
    ssu = SymbolicScreenUnderstanding()
    cor = CORSubsystem()

    symbolic = ssu.extract(_base_observation())
    symbols = ssu.symbols_for_proposal(symbolic)
    hypothesis = ssu.build_hypothesis_from_symbols(
        "Play button remains disabled",
        symbols,
        confidence=0.91,
    )
    proposal = cor.ingest_hypothesis(hypothesis)

    assert proposal is not None
    assert proposal.evidence["symbols"]
    assert proposal.evidence["symbol_confidence"]


def test_replay_equivalence_with_ssu_enabled() -> None:
    cor = CORSubsystem()
    ssu = SymbolicScreenUnderstanding()
    task = _make_task("task-ssu")
    token = _make_admission_token(task)
    authorization = _make_authorization()

    canonical_before = task_executor.canonicalise_task_request(
        task=task,
        authorization=authorization,
        provenance=token.provenance,
        declared_inputs=None,
    )
    fingerprint_before = task_executor.request_fingerprint_from_canonical(canonical_before)

    event = ssu.build_observation_event(_base_observation())
    cor.ingest_observation(event)

    canonical_after = task_executor.canonicalise_task_request(
        task=task,
        authorization=authorization,
        provenance=token.provenance,
        declared_inputs=None,
    )
    fingerprint_after = task_executor.request_fingerprint_from_canonical(canonical_after)

    assert fingerprint_before.value == fingerprint_after.value
