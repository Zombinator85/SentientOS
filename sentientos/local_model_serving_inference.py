"""Separately admitted inference against an opaque, current serving lifetime."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .governed_local_model_invocation import (
    GovernedLocalModelInvoker,
    LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
)
from .local_model_authority import LocalModelAuthorityMap, build_local_model_authority_map
from .local_model_production_serving import (
    ProductionServingController,
    ProductionServingError,
    ServingSession,
)


class ProductionServingInferenceError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ProductionServingInferenceController:
    """Narrow bridge; callers provide an operation, never a model or its custody."""

    __slots__ = ("_serving",)

    def __init__(self, serving_controller: ProductionServingController) -> None:
        if not isinstance(serving_controller, ProductionServingController):
            raise ProductionServingInferenceError("production_serving_controller_required")
        self._serving = serving_controller

    def current_conversation_model_identity(self) -> Mapping[str, Any]:
        """Return stable activation/model provenance, never a worker-lifetime identity."""
        session = self._serving.current_session()
        if session is None:
            raise ProductionServingInferenceError("current_serving_session_required")
        binding = session.binding
        return {
            key: binding[key]
            for key in (
                "activation_state_semantic_digest", "activation_generation",
                "activation_receipt_id", "activation_receipt_semantic_digest", "model_id",
                "observed_loaded_model_identity", "artifact_id", "artifact_sha256",
                "runtime_id", "authority_map_digest",
            )
        }

    @staticmethod
    def _authority(session: ServingSession) -> LocalModelAuthorityMap:
        binding = session.binding
        load = binding["load_configuration"]
        config = ModelConfig(
            [ModelCandidate(Path(str(binding["artifact_path"])), "llama_cpp", str(binding["model_id"]),
                            {"gpu_layers": int(load["n_gpu_layers"])})],
            default_engine="llama_cpp",
            max_context_tokens=int(load["n_ctx"]),
            generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1),
        )
        authority = build_local_model_authority_map(
            config, allowed_roots=[Path(str(binding["artifact_path"])).parent],
            observed_at="1970-01-01T00:00:00+00:00")
        if authority.map_digest != binding["authority_map_digest"]:
            raise ProductionServingInferenceError("serving_authority_map_digest_mismatch")
        return authority

    def generate(self, *, prompt: str, caller: str, correlation_id: str,
                 budget: LocalModelInvocationBudget | None = None,
                 caller_linkage: Mapping[str, Any] | None = None) -> LocalModelInvocationReceipt:
        session = self._serving.current_session()
        if session is None:
            raise ProductionServingInferenceError("current_serving_session_required")
        try:
            model = self._serving._current_inference_model(session)
        except ProductionServingError as exc:
            raise ProductionServingInferenceError(exc.code) from exc
        authority = self._authority(session)
        binding = session.binding
        identity = dict(binding["observed_loaded_model_identity"])
        record = authority.record_for_active_identity(model.active_identity, "local_user_chat")
        if record is None or model.active_identity.to_dict() != identity:
            raise ProductionServingInferenceError("exact_loaded_model_authority_record_required")
        linkage: Mapping[str, Any] = {
            "serving_session_id": session.session_id,
            "serving_operation_id": binding["serving_operation_id"],
            "activation_state_semantic_digest": binding["activation_state_semantic_digest"],
            "activation_generation": binding["activation_generation"],
            "activation_receipt_id": binding["activation_receipt_id"],
            "activation_receipt_semantic_digest": binding["activation_receipt_semantic_digest"],
            "model_serving_admission_ref": binding["model_serving_admission_ref"],
            "authority_map_digest": binding["authority_map_digest"],
            "observed_loaded_model_identity": identity,
            "artifact_id": binding["artifact_id"],
            "artifact_sha256": binding["artifact_sha256"],
            "runtime_id": binding["runtime_id"],
            "caller_context": dict(caller_linkage or {}),
        }
        invoker = GovernedLocalModelInvoker(
            model=model, authority_map=authority, kernel=self._serving._kernel,
            runtime_root=self._serving._handle.root / "local-model" / "inference")
        request = invoker.build_request(
            purpose="local_user_chat", prompt=prompt, caller=caller,
            correlation_id=correlation_id, budget=budget,
            upstream_evidence={"current_serving_lifetime": linkage}, linkage=linkage)

        def current() -> None:
            try:
                self._serving._current_inference_model(session)
            except ProductionServingError as exc:
                raise ProductionServingInferenceError("serving_lifetime_not_current") from exc

        def current_after() -> None:
            try:
                current()
            except ProductionServingInferenceError:
                self._serving._invalidate_inference_session(session, "currentness_changed_during_inference")
                raise

        receipt = invoker.invoke(request, pre_effect_guard=current, post_effect_guard=current_after)
        if receipt.admission_decision_ref == binding["model_serving_admission_ref"]:
            raise ProductionServingInferenceError("inference_admission_not_independent")
        return receipt
