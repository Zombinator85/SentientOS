from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from sentientos.resident_cognitive_model_serving import (
    ResidentCognitiveModelServingError, ResidentCognitiveServingSlot,
)
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.resident_cognitive_model_transition_experiment import *
from sentientos.resident_cognitive_model_transition_rehearsal import run
from sentientos.resident_cognitive_transition_runtime import ResidentCognitiveTransitionStageOperations

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
                        "activation_receipt_semantic_digest": activation["receipt_semantic_digest"],
                        "activation_history_digest": activation.get("activation_history_digest"),
                        "activation_predecessor_state_digest": activation.get("activation_predecessor_state_digest"),
                        "activation_predecessor_posture": activation.get("activation_predecessor_posture")}
    def to_dict(self):
        return {"session_id": self.session_id, "binding": self.binding, "status": "production_current"}


class Serving:
    def __init__(self, session): self.session = session
    def current_session(self): return self.session


class Slot:
    def __init__(self): self.current_controller = Serving(Session())


def activation_value(letter: str, generation: int):
    predecessor = ("a" * 64) if generation > 1 else None
    return {"state_semantic_digest": letter * 64, "generation": generation,
            "receipt_id": f"receipt-{letter}", "receipt_semantic_digest": letter * 64,
            "model_loaded": False, "serving_started": False, "inference_performed": False,
            "commissioning_active_model_identity": {"identity_digest": "a" if generation != 2 else "b"},
            "activation_history_digest": "h" * 64,
            "activation_predecessor_state_digest": predecessor,
            "activation_predecessor_posture": ("verified_predecessor_state" if predecessor
                else "verified_initial_activation_without_predecessor")}


class Operations:
    def __init__(self, slot, *, fail=None, mismatch=False):
        self.slot, self.fail, self.mismatch = slot, fail, mismatch
        self.protocol = protocol()
    def activate_successor(self, context=None):
        if self.fail == "b_activation": raise RuntimeError("denied")
        return {"activation": activation_value("b", 2), "activation_transition_stage": "A->B"}
    def serve_successor(self, activation):
        if self.fail == "b_serving": raise RuntimeError("serving")
        return self._serve(activation, "b_serving_bound", {"identity_digest": "wrong" if self.mismatch else "b"}, "b-op")
    def activate_restored_predecessor(self, context=None):
        if self.fail == "a_activation": raise RuntimeError("denied")
        return {"activation": activation_value("c", 3), "activation_transition_stage": "B->A"}
    def verify_historical_activation(self, activation):
        return activation["commissioning_active_model_identity"]
    def verify_historical_serving_session(self, session):
        return {"receipt_id": "serving-receipt", "receipt_semantic_digest": "c" * 64}
    def verify_transition_observation(self, stage, evidence):
        return None
    def serve_restored_predecessor(self, activation):
        if self.fail == "a_serving": raise RuntimeError("serving")
        return self._serve(activation, "restored_a_serving_bound", {"identity_digest": "a"}, "a-op")

    def _serve(self, activation, stage, identity, operation):
        from sentientos.resident_cognitive_model_transition_experiment import stage_serving_binding
        serving_admission = "serving-admission-" + stage
        stage_binding = dict(stage_serving_binding(protocol=self.protocol, stage=stage,
            activation=activation, expected_identity=identity, operation_id=operation))
        activation_state = {key: value for key, value in activation.items()
            if key not in {"receipt_id", "receipt_semantic_digest", "activation_history_digest",
                           "activation_predecessor_state_digest", "activation_predecessor_posture",
                           "commissioning_active_model_identity", "activation_transition_stage"}}
        session = Session("pending", identity, activation, operation)
        session.binding.update({"activation_state": activation_state,
                                "model_serving_admission_ref": serving_admission,
                                "installation_identity": self.protocol.value["installation_identity"]})
        session.session_id = "resident-serving-session-" + semantic_digest(dict(session.binding))[:24]
        self.slot.current_controller = Serving(session)
        return {"stage_binding": stage_binding, "session": session.to_dict(),
                "serving_admission": serving_admission, "serving_receipt_id": "serving-receipt",
                "serving_receipt_semantic_digest": "c" * 64}


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
    assert result["b_observation_serving_session_receipt_id"]
    assert result["b_observation_serving_session_receipt_digest"]
    assert (result["b_observation_model_serving_admission_ref"]
            != result["b_observation_inference_admission_decision_ref"])
    index = result["restored_a_retrieved_record_ids"].index(result["b_developmental_record_id"])
    assert result["restored_a_retrieved_record_digests"][index] == result["b_developmental_record_digest"]


def test_completed_stage_reconstructs(tmp_path):
    ctl, gate, journal, slot, ops = controller(tmp_path)
    advance(ctl, slot)
    rebuilt = ResidentCognitiveModelTransitionController(protocol=ctl.protocol, journal=journal, gate=gate,
        slot=slot, history_snapshot=lambda: boundary(slot), operations=ops,
        allow_synthetic_approval_for_tests=True, clock=lambda: NOW)
    assert rebuilt.phase == "a_to_b_transition_requested" and not rebuilt.health()["replay_forbidden"]


def test_transition_journal_round_trips_canonical_appends_and_rejects_truncated_tail(tmp_path):
    journal = TransitionJournal(tmp_path / "journal.jsonl")
    appended = journal.append("a_to_b_transition_requested", {"request": "bounded"})

    recovered = journal.entries()
    assert recovered == [dict(appended)]

    journal.path.write_bytes(journal.path.read_bytes().rstrip(b"\n"))
    with pytest.raises(TransitionError, match="journal_noncanonical"):
        journal.entries()


def test_operator_request_provenance_does_not_replace_the_quiescence_capability(tmp_path):
    ctl, _, _, slot, _ = controller(tmp_path)
    advance(ctl, slot)
    ctl.advance(approval=approval(ctl, slot), evidence={"timeout_seconds": 1},
        operation_context={"request_id": "request-1", "request_digest": "d" * 64})

    # The following stage reconstructs the persisted gate token from a journal
    # entry that also carries operator request linkage.
    advance(ctl, slot)
    assert ctl.phase == "b_activation_committed"
    assert ctl.health()["status"] == "in_progress"


def test_malformed_operator_linkage_cannot_be_ignored_as_quiescence_metadata(tmp_path):
    gate = ResidentCognitionQuiescenceGate()
    journal = TransitionJournal(tmp_path / "journal.jsonl")
    journal.append(PHASES[0], {"attempted_stage": PHASES[1]}, status="attempted")
    journal.append(PHASES[1], {})
    token = gate.quiesce(timeout_seconds=1, observation={})
    journal.append("a_quiesced", {**dict(token), "operator_request": []})

    rebuilt = ResidentCognitiveModelTransitionController(protocol=protocol(), journal=journal,
        gate=gate, slot=Slot(), history_snapshot=lambda: history_boundary([]),
        allow_synthetic_approval_for_tests=True, clock=lambda: NOW)
    assert rebuilt.health()["status"] == "interrupted"
    assert rebuilt.health()["reason"] == "quiescence_token_evidence_invalid"


def test_serving_stage_rejects_malformed_quiescence_request_linkage():
    gate = ResidentCognitionQuiescenceGate()
    token = gate.quiesce(timeout_seconds=1, observation={})
    operations = object.__new__(ResidentCognitiveTransitionStageOperations)
    operations.gate = gate
    operations.journal = type("Journal", (), {"entries": lambda self: [{
        "status": "completed", "phase": "a_quiesced",
        "evidence": {**dict(token), "operator_request": []},
    }]})()

    with pytest.raises(TransitionError, match="live_quiescence_evidence_invalid"):
        operations._quiescence()


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


def test_stage_binding_grants_no_authority_and_binds_activation_predecessor():
    activation = activation_value("b", 2)
    binding = stage_serving_binding(protocol=protocol(), stage="b_serving_bound",
        activation=activation, expected_identity={"identity_digest": "b"}, operation_id="b-op")
    assert binding["schema_version"] == BINDING_SCHEMA
    assert binding["activation_predecessor_state_digest"] == activation["activation_predecessor_state_digest"]
    assert binding["activation_predecessor_posture"] == "verified_predecessor_state"
    session = Session("session-b", {"identity_digest": "b"}, activation, "b-op")
    verify_stage_serving_binding(binding, protocol=protocol(), stage="b_serving_bound", session=session)
    session.binding["activation_predecessor_state_digest"] = "c" * 64
    with pytest.raises(TransitionError, match="transition_stage_serving_binding_mismatch"):
        verify_stage_serving_binding(binding, protocol=protocol(), stage="b_serving_bound", session=session)
    legacy_activation = dict(activation)
    legacy_activation.pop("activation_predecessor_state_digest")
    legacy_activation.pop("activation_predecessor_posture")
    legacy = stage_serving_binding(protocol=protocol(), stage="b_serving_bound",
        activation=legacy_activation, expected_identity={"identity_digest": "b"}, operation_id="b-op")
    assert legacy["schema_version"] == LEGACY_BINDING_SCHEMA
    assert not binding["grants_activation"] and not binding["grants_model_serving"] and not binding["grants_inference"]
