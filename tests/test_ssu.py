from __future__ import annotations

import pytest
import task_executor

from control_plane.enums import Decision, ReasonCode, RequestType
from control_plane.records import AuthorizationRecord
from sentientos.cor import CORConfig, CORSubsystem, Hypothesis
from sentientos.governance.routine_delegation import RoutineRegistry
from sentientos.ssu import SSUConfig, SymbolicScreenUnderstanding


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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


def test_confidence_decays_deterministically() -> None:
    clock = FakeClock()
    config = CORConfig(
        proposal_confidence_threshold=0.95,
        hypothesis_decay_window_seconds=100,
        hypothesis_expiry_seconds=1000,
        hypothesis_stale_confidence_threshold=0.5,
    )
    cor = CORSubsystem(config=config, now_fn=clock)
    hypothesis = Hypothesis(hypothesis="steady pattern", confidence=0.9)
    cor.ingest_hypothesis(hypothesis)

    clock.advance(50)
    snapshot = cor.diagnostics_snapshot()
    belief = snapshot["beliefs"][0]
    assert belief["decayed_confidence"] == pytest.approx(0.45)
    assert belief["stale"] is True


def test_stale_symbols_are_excluded_from_proposals() -> None:
    clock = FakeClock()
    config = SSUConfig(
        min_confidence=0.4,
        proposal_confidence_threshold=0.8,
        decay_window_seconds=10,
        expiry_seconds=100,
    )
    ssu = SymbolicScreenUnderstanding(config=config, now_fn=clock)
    observation = _base_observation()

    symbolic = ssu.extract(observation)
    assert ssu.symbols_for_proposal(symbolic)

    clock.advance(10)
    assert ssu.symbols_for_proposal(symbolic) == []


def test_rejected_proposals_do_not_reappear_without_change() -> None:
    clock = FakeClock()
    config = CORConfig(
        proposal_confidence_threshold=0.8,
        proposal_suppression_seconds=100,
    )
    cor = CORSubsystem(config=config, now_fn=clock)
    evidence = {"symbols": ["a"]}
    cor.record_proposal_rejection(
        hypothesis="repeat idea",
        evidence=evidence,
        confidence=0.9,
        reason="operator_reject",
    )

    proposal = cor.ingest_hypothesis(Hypothesis(hypothesis="repeat idea", confidence=0.9, evidence=evidence))
    assert proposal is None

    proposal = cor.ingest_hypothesis(Hypothesis(hypothesis="repeat idea", confidence=0.95, evidence=evidence))
    assert proposal is not None


def test_context_resets_clear_reflection_state() -> None:
    clock = FakeClock()
    cor = CORSubsystem(now_fn=clock)
    cor.ingest_hypothesis(Hypothesis(hypothesis="transient", confidence=0.7))
    cor.reset_context(reason="system_restart")

    snapshot = cor.diagnostics_snapshot()
    assert snapshot["beliefs"] == []


def test_obsolete_ui_pattern_decays_and_disappears() -> None:
    clock = FakeClock()
    config = SSUConfig(
        min_confidence=0.4,
        proposal_confidence_threshold=0.8,
        decay_window_seconds=5,
        expiry_seconds=6,
    )
    ssu = SymbolicScreenUnderstanding(config=config, now_fn=clock)
    observation = {
        "app": "Console",
        "elements": [
            {"element_type": "button", "label": "Erase", "state": "enabled", "confidence": 0.99}
        ],
    }

    symbolic = ssu.extract(observation)
    assert ssu.symbols_for_proposal(symbolic)

    clock.advance(6)
    assert ssu.symbols_for_proposal(symbolic) == []


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
