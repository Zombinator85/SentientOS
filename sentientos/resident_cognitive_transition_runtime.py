"""Production composition for explicitly configured resident cognitive transitions."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from .local_model_production_activation import activate_production, verify_current_activation
from .resident_cognitive_model_serving import (
    ResidentCognitiveModelServingController, ResidentCognitiveServingSlot,
)
from .resident_cognitive_model_transition_experiment import (
    ResidentCognitionQuiescenceGate, TransitionError, TransitionJournal,
    TransitionProtocol, TransitionStageExecutionContext, stage_serving_binding,
)


def _activation(result: Mapping[str, Any]) -> dict[str, Any]:
    state, receipt = result["active_state"], result["activation_receipt"]
    return {**dict(state), "receipt_id": receipt["receipt_id"],
            "receipt_semantic_digest": receipt["receipt_semantic_digest"]}


class ResidentCognitiveTransitionStageOperations:
    """Adapter over canonical activation, resident serving, and stable-slot owners."""

    def __init__(self, *, installation_handle: Any, control_plane_kernel: Any,
                 protocol: TransitionProtocol, journal: TransitionJournal,
                 gate: ResidentCognitionQuiescenceGate, slot: ResidentCognitiveServingSlot,
                 serving_controller_factory: Callable[..., ResidentCognitiveModelServingController]
                 = ResidentCognitiveModelServingController,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 allow_synthetic_evidence_for_tests: bool = False) -> None:
        self.installation_handle = installation_handle
        self.control_plane_kernel = control_plane_kernel
        self.protocol, self.journal = protocol, journal
        self.gate, self.slot = gate, slot
        self.serving_controller_factory = serving_controller_factory
        self.clock = clock
        self.allow_synthetic_evidence_for_tests = allow_synthetic_evidence_for_tests

    def _activate(self, context: TransitionStageExecutionContext | None, *, suffix: str) -> Mapping[str, Any]:
        if context is None:
            raise TransitionError("activation_stage_execution_context_required")
        approval = context.exact_activation_approval()
        current = verify_current_activation(
            self.installation_handle,
            allow_synthetic_evidence_for_tests=self.allow_synthetic_evidence_for_tests)
        correlation_id = str(approval.get("correlation_id", ""))
        commissioning_receipt_id = str(approval.get("commissioning_receipt_id", ""))
        if not correlation_id or not commissioning_receipt_id:
            raise TransitionError("external_activation_approval_binding_incomplete")
        result = activate_production(
            installation_handle=self.installation_handle,
            commissioning_receipt_id=commissioning_receipt_id,
            approval_evidence=approval,
            control_plane_kernel=self.control_plane_kernel,
            correlation_id=correlation_id,
            expected_prior_state=current["active_state"]["state_semantic_digest"],
            observation_time=self.clock(), clock=self.clock,
            allow_synthetic_evidence_for_tests=self.allow_synthetic_evidence_for_tests)
        return {"activation": _activation(cast(Mapping[str, Any], result)),
                "activation_admission": result["activation_receipt"]["model_activation_admission_ref"],
                "external_activation_approval_evidence_id": approval["approval_evidence_id"],
                "external_activation_approval_semantic_digest": approval["approval_semantic_digest"],
                "activation_transition_stage": suffix}

    def _quiescence(self) -> Mapping[str, Any]:
        for entry in reversed(self.journal.entries()):
            if entry["status"] == "completed" and entry["phase"] in {"a_quiesced", "b_quiesced"}:
                token = entry["evidence"]
                if self.gate.verifies(token):
                    return cast(Mapping[str, Any], token)
        raise TransitionError("live_quiescence_custody_mismatch")

    def _serve(self, *, activation: Mapping[str, Any], identity: Mapping[str, Any],
               operation_id: str, stage: str) -> Mapping[str, Any]:
        controller = self.serving_controller_factory(
            self.installation_handle, self.control_plane_kernel)
        session = controller.establish(
            operation_id=operation_id,
            expected_activation_state_digest=str(activation["state_semantic_digest"]))
        binding = stage_serving_binding(protocol=self.protocol, stage=stage,
            activation=activation, expected_identity=identity, operation_id=operation_id)
        bound = self.slot.bind_transition_verified(controller, gate=self.gate,
            quiescence=self._quiescence(), stage_binding=binding,
            protocol=self.protocol, stage=stage)
        return {"stage_binding": dict(binding), "session": bound.to_dict(),
                "serving_admission": bound.binding["model_serving_admission_ref"]}

    def activate_successor(self, context: TransitionStageExecutionContext | None = None) -> Mapping[str, Any]:
        return self._activate(context, suffix="A->B")

    def serve_successor(self, activation: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._serve(activation=activation, identity=self.protocol.value["successor_b"],
            operation_id=str(self.protocol.value["b_serving_operation_id"]), stage="b_serving_bound")

    def activate_restored_predecessor(self, context: TransitionStageExecutionContext | None = None) -> Mapping[str, Any]:
        return self._activate(context, suffix="B->A")

    def serve_restored_predecessor(self, activation: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._serve(activation=activation, identity=self.protocol.value["restored_a"],
            operation_id=str(self.protocol.value["restored_a_serving_operation_id"]),
            stage="restored_a_serving_bound")
