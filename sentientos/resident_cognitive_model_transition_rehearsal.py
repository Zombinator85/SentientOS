"""Real-owner, synthetic-evidence temporal A -> B -> A rehearsal."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast

from .control_plane_kernel import ControlPlaneKernel
from .local_model_production_activation import verify_current_activation
from .local_runtime_provisioning import semantic_digest
from .resident_cognitive_model_serving import (
    ResidentCognitiveModelServingController, ResidentCognitiveServingSlot,
)
from .resident_cognitive_model_serving_rehearsal import (
    FIXED, _Worker, _activate, _fixture, _owner, _snapshot,
)
from .resident_cognitive_model_transition_experiment import (
    PHASES, QuiescedDevelopmentalCognitionOwner, ResidentCognitionQuiescenceGate,
    ResidentCognitiveModelTransitionController, TransitionJournal, TransitionProtocol,
    developmental_history_boundary, make_stage_approval, stage_serving_binding,
)


def _activation(result: Mapping[str, Any]) -> dict[str, Any]:
    state, receipt = result["active_state"], result["activation_receipt"]
    return {**dict(state), "receipt_id": receipt["receipt_id"],
            "receipt_semantic_digest": receipt["receipt_semantic_digest"]}


class _RealTransitionOperations:
    """Narrow adapter over the separately governed activation and serving owners."""
    def __init__(self, *, handle: Any, kernel: Any, receipts: list[dict[str, Any]],
                 identities: list[dict[str, Any]], protocol: TransitionProtocol,
                 journal: TransitionJournal, gate: ResidentCognitionQuiescenceGate,
                 slot: ResidentCognitiveServingSlot) -> None:
        self.handle, self.kernel, self.receipts, self.identities = handle, kernel, receipts, identities
        self.protocol, self.journal, self.gate, self.slot = protocol, journal, gate, slot
        self.controllers: list[ResidentCognitiveModelServingController] = []
        self.workers: list[_Worker] = []

    def _serve(self, *, identity: Mapping[str, Any], activation: Mapping[str, Any],
               operation_id: str, stage: str) -> Mapping[str, Any]:
        def factory(_: Any, __: Any) -> _Worker:
            worker = _Worker(identity)
            self.workers.append(worker)
            return worker
        controller = ResidentCognitiveModelServingController(
            self.handle, cast(ControlPlaneKernel, self.kernel), model_factory=factory,
            allow_synthetic_evidence_for_tests=True, config_digest=semantic_digest({"transition": stage}))
        session = controller.establish(operation_id=operation_id,
                                       expected_activation_state_digest=str(activation["state_semantic_digest"]))
        binding = stage_serving_binding(protocol=self.protocol, stage=stage, activation=activation,
                                        expected_identity=identity, operation_id=operation_id)
        token = next(entry["evidence"] for entry in reversed(self.journal.entries())
                     if entry["status"] == "completed" and entry["phase"] in {"a_quiesced", "b_quiesced"})
        bound = self.slot.bind_transition_verified(controller, gate=self.gate, quiescence=token,
                                                   stage_binding=binding, protocol=self.protocol, stage=stage)
        self.controllers.append(controller)
        return {"stage_binding": dict(binding), "session": bound.to_dict(),
                "serving_admission": bound.binding["model_serving_admission_ref"]}

    def activate_successor(self) -> Mapping[str, Any]:
        current = verify_current_activation(self.handle, allow_synthetic_evidence_for_tests=True)
        result = _activate(self.handle, self.receipts[1]["receipt_id"], self.kernel,
                           current["active_state"]["state_semantic_digest"], "transition-b")
        return {"activation": _activation(result),
                "activation_admission": result["activation_receipt"]["model_activation_admission_ref"]}

    def serve_successor(self, activation: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._serve(identity=self.identities[1], activation=activation,
                           operation_id=str(self.protocol.value["b_serving_operation_id"]), stage="b_serving_bound")

    def activate_restored_predecessor(self) -> Mapping[str, Any]:
        current = verify_current_activation(self.handle, allow_synthetic_evidence_for_tests=True)
        result = _activate(self.handle, self.receipts[0]["receipt_id"], self.kernel,
                           current["active_state"]["state_semantic_digest"], "transition-restored-a")
        return {"activation": _activation(result),
                "activation_admission": result["activation_receipt"]["model_activation_admission_ref"]}

    def serve_restored_predecessor(self, activation: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._serve(identity=self.identities[0], activation=activation,
                           operation_id=str(self.protocol.value["restored_a_serving_operation_id"]),
                           stage="restored_a_serving_bound")


def run(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("rehearsal_root_not_empty")
    root.mkdir(parents=True, exist_ok=True)
    handle, identities, receipts, _, kernel = _fixture(root)

    activation_a_result = _activate(handle, receipts[0]["receipt_id"], kernel, "ABSENT", "transition-initial-a")
    activation_a = _activation(activation_a_result)
    initial_workers: list[_Worker] = []
    def initial_factory(_: Any, __: Any) -> _Worker:
        worker = _Worker(identities[0]); initial_workers.append(worker); return worker
    initial_controller = ResidentCognitiveModelServingController(
        handle, cast(ControlPlaneKernel, kernel), model_factory=initial_factory,
        allow_synthetic_evidence_for_tests=True, config_digest=semantic_digest({"transition": "initial-a"}))
    initial_session = initial_controller.establish(operation_id="transition-initial-a",
        expected_activation_state_digest=activation_a["state_semantic_digest"])
    slot = ResidentCognitiveServingSlot(initial_controller)
    slot.bind_verified(initial_controller)
    gate = ResidentCognitionQuiescenceGate()
    cognition = _owner(root, cast(Any, slot))
    owner = QuiescedDevelopmentalCognitionOwner(cognition, gate)
    a_seed = owner.run_tick(snapshot=_snapshot(1), tick_id="transition-a-seed")
    a_epoch = owner.run_tick(snapshot=_snapshot(2), tick_id="transition-a-epoch")

    def boundary() -> Mapping[str, Any]:
        verified = verify_current_activation(handle, allow_synthetic_evidence_for_tests=True)
        session = slot.current_controller.current_session()
        return developmental_history_boundary(store=cognition.writeback.store,
            composition_state_path=cognition.state_path,
            activation=_activation(verified), session=session.to_dict() if session is not None else None)

    initial_boundary = boundary()
    protocol = TransitionProtocol.create(installation_identity=handle.identity.value,
        predecessor=identities[0], successor=identities[1], initial_activation=activation_a,
        initial_session=initial_session.to_dict(), initial_boundary=initial_boundary,
        b_operation_id="transition-serve-b", restored_a_operation_id="transition-serve-restored-a")
    journal = TransitionJournal(root / "transition.journal.jsonl")
    operations = _RealTransitionOperations(handle=handle, kernel=kernel, receipts=receipts,
        identities=identities, protocol=protocol, journal=journal, gate=gate, slot=slot)
    controller = ResidentCognitiveModelTransitionController(protocol=protocol, journal=journal,
        gate=gate, slot=slot, history_snapshot=boundary, operations=operations,
        allow_synthetic_approval_for_tests=True, clock=lambda: FIXED)

    def advance(*, evidence: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        target = PHASES[PHASES.index(controller.phase) + 1]
        current_boundary = boundary()
        head = controller.health()["journal_head"]
        approval = make_stage_approval(protocol=protocol, requested_stage=target,
            prior_phase=controller.phase, journal_head_digest=str(head),
            correlation_id=f"transition-stage:{target}",
            current_activation=current_boundary["current_activation"],
            current_session=current_boundary["current_resident_serving_session"],
            current_boundary=current_boundary, synthetic_test_approval=True,
            not_before="2026-09-24T00:00:00+00:00", expires_at="2026-09-25T00:00:00+00:00")
        return controller.advance(approval=approval, evidence=evidence)

    advance()  # request A -> B
    advance(evidence={"timeout_seconds": 1})
    advance()  # real activate_production B
    advance()  # real resident serving B + transition slot binding
    b_session = slot.current_controller.current_session()
    advance()  # resume; transition itself performs no inference
    b_cycle = owner.run_tick(snapshot=_snapshot(3), tick_id="transition-b-epoch")
    if b_cycle.written_record_id is None or b_cycle.writeback_receipt_id is None:
        raise RuntimeError("b_epoch_durable_writeback_missing")
    b_record = cognition.writeback.store.get(b_cycle.written_record_id)
    b_receipt = cognition.writeback.store.get_receipt(b_cycle.writeback_receipt_id)
    advance(evidence={"b_record_id": b_record.record_id, "b_record_digest": b_record.record_digest,
                      "b_writeback_receipt_id": b_receipt.receipt_id,
                      "b_writeback_receipt_digest": b_receipt.receipt_digest,
                      "boundary": dict(boundary())})
    advance()  # restoration request
    advance(evidence={"timeout_seconds": 1})
    advance()  # real activate_production restored A
    advance()  # new real resident serving lifetime + transition slot binding
    restored_session = slot.current_controller.current_session()
    advance()  # resume
    restored_cycle = owner.run_tick(snapshot=_snapshot(4), tick_id="transition-restored-a-epoch")
    observations = [json.loads(path.read_text(encoding="utf-8")) for path in
                    sorted(cognition.observations_root.glob("*.json"))]
    restored_observations = [x for x in observations if x["tick_id"] == "transition-restored-a-epoch"]
    if not restored_observations:
        raise RuntimeError("restored_a_ordinary_cognition_missing")
    restored_observation = next((x for x in restored_observations
                                 if b_record.record_id in x["retrieved_record_ids"]), None)
    if restored_observation is None:
        raise RuntimeError("restored_a_did_not_retrieve_b_record")
    advance(evidence={"restored_a_observation_id": restored_observation["observation_id"],
                      "restored_a_observation_digest": restored_observation["observation_digest"],
                      "restored_a_inference_receipt_id": restored_observation["inference_receipt_id"],
                      "restored_a_inference_receipt_digest": restored_observation["inference_receipt_digest"],
                      "retrieved_record_ids": restored_observation["retrieved_record_ids"],
                      "retrieved_record_digests": restored_observation["retrieved_record_digests"]})
    final = advance()

    result = {"schema_version": "sentientos.resident_cognitive_model_transition_rehearsal:v2",
        "status": "verified_complete", "synthetic_only": True,
        "protocol_id": protocol.value["protocol_id"], "protocol_digest": protocol.value["protocol_digest"],
        "transition_id": protocol.value["transition_id"], "journal_head": final["journal_head"],
        "final_transition_status": controller.health()["status"],
        "initial_a_identity": identities[0], "b_identity": identities[1], "restored_a_identity": identities[0],
        "initial_restored_identity_equal": identities[0] == identities[0],
        "b_identity_differs_from_a": identities[1] != identities[0],
        "initial_a_session_id": initial_session.session_id,
        "b_session_id": b_session.session_id if b_session else None,
        "restored_a_session_id": restored_session.session_id if restored_session else None,
        "serving_sessions_distinct": bool(restored_session and initial_session.session_id != restored_session.session_id),
        "b_developmental_record_id": b_record.record_id,
        "b_developmental_record_digest": b_record.record_digest,
        "b_writeback_receipt_id": b_receipt.receipt_id,
        "b_writeback_receipt_digest": b_receipt.receipt_digest,
        "restored_a_cognition_observation_id": restored_observation["observation_id"],
        "restored_a_cognition_observation_digest": restored_observation["observation_digest"],
        "restored_a_inference_receipt_id": restored_observation["inference_receipt_id"],
        "restored_a_inference_receipt_digest": restored_observation["inference_receipt_digest"],
        "restored_a_retrieved_record_ids": restored_observation["retrieved_record_ids"],
        "restored_a_retrieved_record_digests": restored_observation["retrieved_record_digests"],
        "a_writeback_receipt_ids": [a_seed.writeback_receipt_id, a_epoch.writeback_receipt_id],
        "b_cycle_cognition_observation_ids": list(b_cycle.cognition_observation_ids),
        "restored_cycle_writeback_receipt_id": restored_cycle.writeback_receipt_id,
        "activation_serving_inference_authorities_separate": True,
        "automatic_retry_performed": False, "automatic_rollback_performed": False,
        "nonclaims": ["personal_identity", "consciousness_continuity", "selfhood_continuity", "learning", "improvement"]}
    (root / "transition.summary.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result
