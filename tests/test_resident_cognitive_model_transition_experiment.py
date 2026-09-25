from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from sentientos.resident_cognitive_model_serving import (
    ResidentCognitiveModelServingError, ResidentCognitiveServingSlot,
)
from sentientos.resident_cognitive_model_transition_experiment import *
from sentientos.resident_cognitive_model_transition_rehearsal import run

pytestmark = pytest.mark.no_legacy_skip
NOW = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)


class Session:
    def __init__(self, sid="session-a", identity=None, activation=None, operation="operation-a"):
        identity = identity or {"identity_digest": "a"}
        activation = activation or activation_value("a", 1)
        self.session_id = sid
        self.binding = {"observed_loaded_model_identity": identity, "serving_operation_id": operation,
                        "activation_state_semantic_digest": activation["state_semantic_digest"],
                        "activation_generation": activation["generation"],
                        "activation_receipt_id": activation["receipt_id"],
                        "activation_receipt_semantic_digest": activation["receipt_semantic_digest"]}
    def to_dict(self):
        return {"session_id": self.session_id, "binding": self.binding, "status": "production_current"}


class Serving:
    def __init__(self, session): self.session = session
    def current_session(self): return self.session


class Slot:
    def __init__(self): self.current_controller = Serving(Session())


def activation_value(letter: str, generation: int):
    return {"state_semantic_digest": letter * 64, "generation": generation,
            "receipt_id": f"receipt-{letter}", "receipt_semantic_digest": letter * 64}


class Operations:
    def __init__(self, slot, *, fail=None, mismatch=False):
        self.slot, self.fail, self.mismatch = slot, fail, mismatch
    def activate_successor(self):
        if self.fail == "b_activation": raise RuntimeError("denied")
        return {"activation": activation_value("b", 2)}
    def serve_successor(self, activation):
        if self.fail == "b_serving": raise RuntimeError("serving")
        identity = {"identity_digest": "wrong" if self.mismatch else "b"}
        self.slot.current_controller = Serving(Session("session-b", identity, activation, "b-op"))
        return {"session": self.slot.current_controller.session.to_dict()}
    def activate_restored_predecessor(self):
        if self.fail == "a_activation": raise RuntimeError("denied")
        return {"activation": activation_value("c", 3)}
    def serve_restored_predecessor(self, activation):
        if self.fail == "a_serving": raise RuntimeError("serving")
        self.slot.current_controller = Serving(Session("session-restored-a", {"identity_digest": "a"}, activation, "a-op"))
        return {"session": self.slot.current_controller.session.to_dict()}


def protocol():
    identity = {"identity_digest": "a"}
    return TransitionProtocol.create(installation_identity="installation", predecessor=identity,
        successor={"identity_digest": "b"}, initial_activation=activation_value("a", 1),
        initial_session=Session().to_dict(), initial_boundary=history_boundary([]),
        b_operation_id="b-op", restored_a_operation_id="a-op")


def boundary(slot):
    session = slot.current_controller.current_session()
    return {**dict(history_boundary([])), "current_activation": activation_value("a", 1),
            "current_resident_serving_session": session.to_dict() if session else None}


def controller(tmp_path, *, operations=None, gate=None, journal=None):
    slot = Slot()
    gate = gate or ResidentCognitionQuiescenceGate()
    journal = journal or TransitionJournal(tmp_path / "journal.jsonl")
    ops = operations or Operations(slot)
    ctl = ResidentCognitiveModelTransitionController(protocol=protocol(), journal=journal, gate=gate,
        slot=slot, history_snapshot=lambda: boundary(slot), operations=ops,
        allow_synthetic_approval_for_tests=True, clock=lambda: NOW)
    return ctl, gate, journal, slot, ops


def approval(ctl, slot, *, mutate=None):
    target = PHASES[PHASES.index(ctl.phase) + 1]
    current = boundary(slot)
    value = dict(make_stage_approval(protocol=ctl.protocol, requested_stage=target, prior_phase=ctl.phase,
        journal_head_digest=ctl.health()["journal_head"], correlation_id=f"stage:{target}",
        current_activation=current["current_activation"], current_session=current["current_resident_serving_session"],
        current_boundary=current, synthetic_test_approval=True,
        not_before="2026-09-24T00:00:00+00:00", expires_at="2026-09-25T00:00:00+00:00"))
    if mutate:
        value[mutate] = "tampered"
    return value


def advance(ctl, slot, evidence=None):
    return ctl.advance(approval=approval(ctl, slot), evidence=evidence)


def test_real_owner_temporal_rehearsal_retrieves_exact_b_record(tmp_path):
    result = run(tmp_path / "rehearsal")
    assert result["status"] == "verified_complete"
    assert result["initial_restored_identity_equal"] and result["b_identity_differs_from_a"]
    assert result["serving_sessions_distinct"]
    assert result["b_developmental_record_id"] in result["restored_a_retrieved_record_ids"]
    index = result["restored_a_retrieved_record_ids"].index(result["b_developmental_record_id"])
    assert result["restored_a_retrieved_record_digests"][index] == result["b_developmental_record_digest"]


def test_completed_stage_reconstructs(tmp_path):
    ctl, gate, journal, slot, ops = controller(tmp_path)
    advance(ctl, slot)
    rebuilt = ResidentCognitiveModelTransitionController(protocol=ctl.protocol, journal=journal, gate=gate,
        slot=slot, history_snapshot=lambda: boundary(slot), operations=ops,
        allow_synthetic_approval_for_tests=True, clock=lambda: NOW)
    assert rebuilt.phase == "a_to_b_transition_requested" and not rebuilt.health()["replay_forbidden"]


def test_failed_effectful_stage_is_not_replayable_after_reconstruction(tmp_path):
    ctl, gate, journal, slot, _ = controller(tmp_path)
    ctl.operations = Operations(slot, fail="b_activation")
    advance(ctl, slot); advance(ctl, slot, {"timeout_seconds": 1})
    with pytest.raises(RuntimeError): advance(ctl, slot)
    rebuilt = ResidentCognitiveModelTransitionController(protocol=ctl.protocol, journal=journal, gate=gate,
        slot=slot, history_snapshot=lambda: boundary(slot), operations=Operations(slot),
        allow_synthetic_approval_for_tests=True, clock=lambda: NOW)
    assert rebuilt.health()["status"] == "interrupted"
    with pytest.raises(TransitionError, match="failed_or_unresolved_stage_replay_forbidden"):
        advance(rebuilt, slot)


def test_unresolved_attempt_is_not_replayable(tmp_path):
    ctl, gate, journal, slot, ops = controller(tmp_path)
    advance(ctl, slot); advance(ctl, slot, {"timeout_seconds": 1})
    journal.append(ctl.phase, {"attempted_stage": "b_activation_committed"}, status="attempted")
    rebuilt = ResidentCognitiveModelTransitionController(protocol=ctl.protocol, journal=journal, gate=gate,
        slot=slot, history_snapshot=lambda: boundary(slot), operations=ops,
        allow_synthetic_approval_for_tests=True, clock=lambda: NOW)
    assert rebuilt.health()["reason"] == "unresolved_attempt"
    with pytest.raises(TransitionError, match="replay_forbidden"): advance(rebuilt, slot)


def test_quiesced_reconstruction_requires_same_live_gate_token(tmp_path):
    ctl, gate, journal, slot, ops = controller(tmp_path)
    advance(ctl, slot); advance(ctl, slot, {"timeout_seconds": 1})
    rebuilt = ResidentCognitiveModelTransitionController(protocol=ctl.protocol, journal=journal,
        gate=ResidentCognitionQuiescenceGate(), slot=slot, history_snapshot=lambda: boundary(slot), operations=ops,
        allow_synthetic_approval_for_tests=True, clock=lambda: NOW)
    assert rebuilt.health()["reason"] == "live_quiescence_custody_mismatch"


def test_journal_protocol_and_stage_approval_tamper(tmp_path):
    ctl, _, journal, slot, _ = controller(tmp_path)
    with pytest.raises(TransitionError, match="stage_approval_tamper"):
        ctl.advance(approval=approval(ctl, slot, mutate="requested_stage"))
    advance(ctl, slot)
    journal.path.write_text(journal.path.read_text().replace("a_to_b_transition_requested", "skip"))
    with pytest.raises(TransitionError, match="journal_tamper"): ctl.health()
    proto = protocol(); bad = dict(proto.value); bad["successor_b"] = {"x": 1}; object.__setattr__(proto, "value", bad)
    with pytest.raises(TransitionError, match="protocol_tamper"): proto.verify()


def test_quiescence_timeout_and_inference_denied_while_quiesced():
    gate = ResidentCognitionQuiescenceGate(); entered = threading.Event(); release = threading.Event()
    def work():
        with gate.cycle(): entered.set(); release.wait()
    thread = threading.Thread(target=work); thread.start(); entered.wait()
    with pytest.raises(TransitionError, match="quiescence_timeout"):
        gate.quiesce(timeout_seconds=.01, observation={})
    release.set(); thread.join(); token = gate.quiesce(timeout_seconds=1, observation={})
    with pytest.raises(TransitionError, match="resident_cognition_quiesced"):
        with gate.cycle(): pass
    gate.resume(token)


@pytest.mark.parametrize("failure", ["b_activation", "b_serving", "a_activation", "a_serving"])
def test_subordinate_denial_or_failure_interrupts_without_retry_or_rollback(tmp_path, failure):
    ctl, _, _, slot, _ = controller(tmp_path)
    ctl.operations = Operations(slot, fail=failure)
    while True:
        target = PHASES[PHASES.index(ctl.phase) + 1]
        if ((failure == "b_activation" and target == "b_activation_committed")
                or (failure == "b_serving" and target == "b_serving_bound")
                or (failure == "a_activation" and target == "a_restoration_activation_committed")
                or (failure == "a_serving" and target == "restored_a_serving_bound")):
            with pytest.raises(RuntimeError): advance(ctl, slot)
            break
        advance(ctl, slot, {"timeout_seconds": 1} if target in {"a_quiesced", "b_quiesced"} else {})
    assert ctl.health()["status"] == "interrupted" and ctl.health()["replay_forbidden"]


def test_stage_skip_is_rejected(tmp_path):
    ctl, _, _, slot, _ = controller(tmp_path)
    bad = dict(approval(ctl, slot)); bad["requested_stage"] = "a_quiesced"
    body = {k: v for k, v in bad.items() if k != "approval_digest"}; bad["approval_digest"] = digest(body)
    with pytest.raises(TransitionError, match="stage_approval_binding_mismatch"): ctl.advance(approval=bad)


def test_transition_slot_rejects_bind_without_quiescence():
    gate = ResidentCognitionQuiescenceGate(); proto = protocol(); activation = activation_value("b", 2)
    session = Session("session-b", {"identity_digest": "b"}, activation, "b-op")
    slot = ResidentCognitiveServingSlot(cast(Any, Serving(Session())))
    binding = stage_serving_binding(protocol=proto, stage="b_serving_bound", activation=activation,
                                    expected_identity={"identity_digest": "b"}, operation_id="b-op")
    with pytest.raises(ResidentCognitiveModelServingError, match="transition_bind_without_live_quiescence"):
        slot.bind_transition_verified(cast(Any, Serving(session)), gate=gate, quiescence={},
                                      stage_binding=binding, protocol=proto, stage="b_serving_bound")


def test_synthetic_approval_rejected_in_production(tmp_path):
    ctl, gate, journal, slot, ops = controller(tmp_path)
    production = ResidentCognitiveModelTransitionController(protocol=ctl.protocol, journal=journal, gate=gate,
        slot=slot, history_snapshot=lambda: boundary(slot), operations=ops, clock=lambda: NOW)
    with pytest.raises(TransitionError, match="synthetic_stage_approval_forbidden"):
        production.advance(approval=approval(production, slot))


def test_stage_binding_grants_no_authority():
    binding = stage_serving_binding(protocol=protocol(), stage="b_serving_bound",
        activation=activation_value("b", 2), expected_identity={"identity_digest": "b"}, operation_id="b-op")
    assert not binding["grants_activation"] and not binding["grants_model_serving"] and not binding["grants_inference"]
