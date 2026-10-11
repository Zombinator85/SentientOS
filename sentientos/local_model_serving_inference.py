"""Separately admitted inference against an opaque, current serving lifetime."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Mapping

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .governed_local_model_invocation import (
    GovernedLocalModelInvoker,
    GovernedLocalModelResourceInvocationContext,
    LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
    MAX_INVOCATION_RECEIPT_BYTES,
    MAX_INVOCATION_RECEIPTS,
    validate_receipt,
)
from .local_model_authority import LocalModelAuthorityMap, build_local_model_authority_map, digest_payload
from .chat_process_generation import (
    ChatProcessGenerationError,
    verify_current_chat_process_handoff,
    verify_stored_chat_process_handoff,
)
from .local_model_production_serving import (
    ProductionServingController,
    ProductionServingError,
    ServingSession,
    read_serving_operation_history,
)


class ProductionServingInferenceError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def unavailable_chat_process_software_generation() -> dict[str, Any]:
    """Describe the unimplemented chat-process generation issuer without inferring one."""
    return {
        "status": "unavailable",
        "reason_code": "authenticated_chat_process_generation_issuer_not_composed",
        "generation_identity": None,
        "process_instance_id": None,
    }


class ProductionServingInferenceController:
    """Narrow bridge; callers provide an operation, never a model or its custody."""

    __slots__ = ("_serving", "_runtime_handoff_id", "_receipt_capacity_lock")

    def __init__(self, serving_controller: ProductionServingController, *,
                 runtime_handoff_id: str | None = None) -> None:
        if not isinstance(serving_controller, ProductionServingController):
            raise ProductionServingInferenceError("production_serving_controller_required")
        self._serving = serving_controller
        self._runtime_handoff_id = runtime_handoff_id
        self._receipt_capacity_lock = threading.Lock()

    def _software_generation_attribution(self) -> dict[str, Any]:
        if self._runtime_handoff_id is None:
            return unavailable_chat_process_software_generation()
        try:
            return verify_current_chat_process_handoff(
                handle=self._serving._handle, handoff_id=self._runtime_handoff_id)
        except ChatProcessGenerationError as exc:
            raise ProductionServingInferenceError("chat_process_generation_handoff_invalid") from exc

    def current_conversation_model_identity(self) -> Mapping[str, Any]:
        """Return stable activation/model provenance, never a worker-lifetime identity."""
        session = self._serving.current_session()
        if session is None:
            raise ProductionServingInferenceError("current_serving_session_required")
        binding = session.binding
        return {
            key: binding[key]
            for key in (
                "installation_identity", "activation_state_semantic_digest", "activation_generation",
                "activation_predecessor_state_digest",
                "activation_receipt_id", "activation_receipt_semantic_digest", "model_id",
                "observed_loaded_model_identity", "artifact_id", "artifact_sha256",
                "runtime_id", "authority_map_digest", "serving_receipt_id",
                "serving_receipt_semantic_digest", "serving_operation_attempt_id",
                "serving_operation_attempt_semantic_digest",
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
                 caller_linkage: Mapping[str, Any] | None = None,
                 resource_context: GovernedLocalModelResourceInvocationContext | None = None,
                 ) -> LocalModelInvocationReceipt:
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
        software_generation_attribution = self._software_generation_attribution()
        configured_operation = software_generation_attribution.get("configured_serving_operation_id")
        if (configured_operation is not None
                and configured_operation != binding.get("serving_operation_id")):
            raise ProductionServingInferenceError("serving_operation_chat_handoff_mismatch")
        linkage: Mapping[str, Any] = {
            "serving_session_id": session.session_id,
            "serving_receipt_id": binding.get("serving_receipt_id"),
            "serving_receipt_semantic_digest": binding.get("serving_receipt_semantic_digest"),
            "serving_operation_attempt_id": binding.get("serving_operation_attempt_id"),
            "serving_operation_attempt_semantic_digest": binding.get(
                "serving_operation_attempt_semantic_digest"),
            "serving_operation_id": binding["serving_operation_id"],
            "installation_identity": binding["installation_identity"],
            "activation_state_semantic_digest": binding["activation_state_semantic_digest"],
            "activation_generation": binding["activation_generation"],
            "activation_predecessor_state_digest": binding["activation_predecessor_state_digest"],
            "activation_receipt_id": binding["activation_receipt_id"],
            "activation_receipt_semantic_digest": binding["activation_receipt_semantic_digest"],
            "model_serving_admission_ref": binding["model_serving_admission_ref"],
            "authority_map_digest": binding["authority_map_digest"],
            "observed_loaded_model_identity": identity,
            "artifact_id": binding["artifact_id"],
            "artifact_sha256": binding["artifact_sha256"],
            "runtime_id": binding["runtime_id"],
            "caller_context": dict(caller_linkage or {}),
            "software_generation_attribution": software_generation_attribution,
        }
        invoker = GovernedLocalModelInvoker(
            model=model, authority_map=authority, kernel=self._serving._kernel,
            runtime_root=self._serving._handle.root / "local-model" / "inference")
        handle = self._serving._handle
        receipt_directory = handle.fixed_object("local-model/inference/receipts")
        handle.ensure_directory(receipt_directory)

        def publish_receipt(value: Mapping[str, Any]) -> None:
            receipt_id = value.get("receipt_id")
            if (not isinstance(receipt_id, str) or len(receipt_id) != 30
                    or not receipt_id.startswith("lmrec-")
                    or any(character not in "0123456789abcdef" for character in receipt_id[6:])):
                raise ProductionServingInferenceError("invocation_receipt_identity_invalid")
            valid, findings = validate_receipt(value)
            if not valid:
                raise ProductionServingInferenceError("invocation_receipt_validation_failed:" + findings[0])
            target = receipt_directory.child(receipt_id + ".json")
            payload = (json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            if len(payload) > MAX_INVOCATION_RECEIPT_BYTES:
                raise ProductionServingInferenceError("invocation_receipt_size_bound_exceeded")
            handle.durable_replace(target, payload)

        invoker.register_evidence_sink(publish_receipt)
        request = invoker.build_request(
            purpose="local_user_chat", prompt=prompt, caller=caller,
            correlation_id=correlation_id, budget=budget,
            upstream_evidence={"current_serving_lifetime": linkage}, linkage=linkage)
        request_receipt_bytes = json.dumps(request.to_receipt_request_dict(),
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False).encode("utf-8")
        # Leave bounded room for the receipt envelope and resource linkage,
        # which are added after backend entry.
        if len(request_receipt_bytes) + 8192 > MAX_INVOCATION_RECEIPT_BYTES:
            raise ProductionServingInferenceError(
                "invocation_request_receipt_size_bound_exceeded")

        def current() -> None:
            # Both guards use the chat child’s own launcher handoff, never the
            # maintenance daemon’s independently running software identity.
            # The post-effect guard ensures a completed receipt cannot span a
            # detected source-generation change during inference.
            try:
                self._serving._current_inference_model(session)
            except ProductionServingError as exc:
                raise ProductionServingInferenceError("serving_lifetime_not_current") from exc
            current_generation = self._software_generation_attribution()
            if current_generation != software_generation_attribution:
                raise ProductionServingInferenceError("chat_process_generation_changed_during_inference")

        def current_after() -> None:
            try:
                current()
            except ProductionServingInferenceError:
                self._serving._invalidate_inference_session(session, "currentness_changed_during_inference")
                raise

        # The read-only observer refuses more than this many receipts. Hold
        # one process-local slot across backend execution and durable receipt
        # publication so concurrent requests cannot exceed that source bound.
        with self._receipt_capacity_lock:
            try:
                receipt_names = handle.list_regular_names(
                    receipt_directory, max_entries=MAX_INVOCATION_RECEIPTS)
            except Exception as exc:
                raise ProductionServingInferenceError(
                    "invocation_receipt_capacity_observation_unavailable") from exc
            if len(receipt_names) >= MAX_INVOCATION_RECEIPTS:
                raise ProductionServingInferenceError(
                    "invocation_receipt_capacity_exhausted")
            receipt = invoker.invoke(
                request,
                pre_effect_guard=current,
                post_effect_guard=current_after,
                resource_context=resource_context,
            )
        if receipt.admission_decision_ref == binding["model_serving_admission_ref"]:
            raise ProductionServingInferenceError("inference_admission_not_independent")
        return receipt

    def verify_stored_chat_invocation(self, *, receipt_id: str, receipt_digest: str,
                                     session_id: str, user_turn_id: str,
                                     assistant_text: str | None = None,
                                     client_request_id_digest: str | None = None) -> Mapping[str, Any]:
        """Reconstruct one prior chat model identity from installation custody."""
        if (not isinstance(receipt_id, str) or len(receipt_id) != 30 or not receipt_id.startswith("lmrec-")
                or any(character not in "0123456789abcdef" for character in receipt_id[6:])):
            raise ProductionServingInferenceError("stored_invocation_identity_invalid")
        try:
            raw = self._serving._handle.read_regular_bounded(
                self._serving._handle.fixed_object(f"local-model/inference/receipts/{receipt_id}.json"),
                max_bytes=1_048_576)
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise ProductionServingInferenceError("stored_invocation_unavailable_or_invalid") from exc
        if (not isinstance(value, Mapping)
                or json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n" != raw
                or value.get("receipt_id") != receipt_id or value.get("receipt_digest") != receipt_digest):
            raise ProductionServingInferenceError("stored_invocation_identity_mismatch")
        valid, findings = validate_receipt(value)
        request = value.get("request")
        if not isinstance(request, Mapping):
            raise ProductionServingInferenceError("stored_invocation_request_invalid")
        request_semantic = {key: item for key, item in request.items()
            if key not in {"request_id", "request_digest", "raw_prompt_stored", "ephemeral_prompt_handling"}}
        request_digest = digest_payload(request_semantic)
        if (not valid or value.get("status") != "admitted_completed"
                or not isinstance(value.get("effects"), Mapping)
                or value["effects"].get("local_model_inference") is not True
                or not isinstance(value.get("output_digest"), str)
                or request.get("request_digest") != request_digest
                or request.get("request_id") != "lmreq-" + request_digest[:24]
                or request.get("caller") != "chat_service" or request.get("purpose") != "local_user_chat"):
            raise ProductionServingInferenceError("stored_invocation_not_completed_chat")
        upstream = request.get("upstream_evidence")
        linkage = request.get("linkage")
        lifetime = upstream.get("current_serving_lifetime") if isinstance(upstream, Mapping) else None
        if (not isinstance(lifetime, Mapping) or not isinstance(linkage, Mapping)
                or linkage != dict(lifetime)
                or dict(request.get("active_model_identity", {})) != dict(lifetime.get("observed_loaded_model_identity", {}))):
            raise ProductionServingInferenceError("stored_invocation_serving_binding_invalid")
        caller_context = lifetime.get("caller_context")
        if (not isinstance(caller_context, Mapping) or caller_context.get("session_id") != session_id
                or caller_context.get("user_turn_id") != user_turn_id):
            raise ProductionServingInferenceError("stored_invocation_conversation_binding_invalid")
        if client_request_id_digest is not None:
            if (not isinstance(client_request_id_digest, str) or len(client_request_id_digest) != 64
                    or any(character not in "0123456789abcdef" for character in client_request_id_digest)
                    or caller_context.get("client_request_id_digest") != client_request_id_digest):
                raise ProductionServingInferenceError("stored_invocation_client_request_binding_invalid")
        serving_reference_keys = ("serving_receipt_id", "serving_receipt_semantic_digest",
            "serving_operation_attempt_id", "serving_operation_attempt_semantic_digest")
        serving_reference_values = [lifetime.get(key) for key in serving_reference_keys]
        serving_receipt_lineage: dict[str, Any] = {"status": "historically_unbound"}
        if any(item is not None for item in serving_reference_values):
            if any(not isinstance(item, str) or not item for item in serving_reference_values):
                raise ProductionServingInferenceError("stored_invocation_serving_receipt_identity_incomplete")
            serving_receipt_id, serving_receipt_digest, serving_attempt_id, serving_attempt_digest = (
                serving_reference_values)
            try:
                serving_history = read_serving_operation_history(self._serving._handle)
            except ProductionServingError as exc:
                raise ProductionServingInferenceError("stored_invocation_serving_history_invalid") from exc
            matching_history = [item for item in serving_history
                if item.get("receipt_semantic_digest") == serving_receipt_digest
                and isinstance(item.get("receipt"), Mapping)
                and item["receipt"].get("receipt_id") == serving_receipt_id]
            if len(matching_history) != 1:
                raise ProductionServingInferenceError("stored_invocation_serving_receipt_unavailable")
            serving_history_item = matching_history[0]
            serving_receipt = serving_history_item["receipt"]
            serving_binding = serving_receipt.get("binding")
            serving_binding_fields = (
                "installation_identity", "serving_operation_id", "activation_state_semantic_digest",
                "activation_generation", "activation_predecessor_state_digest",
                "activation_receipt_id", "activation_receipt_semantic_digest",
                "model_serving_admission_ref", "authority_map_digest", "model_id",
                "artifact_id", "artifact_sha256", "runtime_id", "observed_loaded_model_identity",
            )
            if (serving_history_item.get("status") != "serving_receipt_verified"
                    or serving_receipt.get("session_id") != lifetime.get("serving_session_id")
                    or serving_history_item.get("attempt_semantic_digest") != serving_attempt_digest
                    or not isinstance(serving_history_item.get("attempt"), Mapping)
                    or serving_history_item["attempt"].get("attempt_id") != serving_attempt_id
                    or not isinstance(serving_binding, Mapping)
                    or any(lifetime.get(key) != serving_binding.get(key)
                        for key in serving_binding_fields)):
                raise ProductionServingInferenceError("stored_invocation_serving_receipt_lineage_mismatch")
            serving_receipt_lineage = {
                "status": "reservation_and_serving_receipt_verified",
                "serving_receipt_id": serving_receipt_id,
                "serving_receipt_semantic_digest": serving_receipt_digest,
                "serving_operation_attempt_id": serving_attempt_id,
                "serving_operation_attempt_semantic_digest": serving_attempt_digest,
            }
        software_generation = linkage.get("software_generation_attribution")
        if software_generation == unavailable_chat_process_software_generation():
            pass
        elif (isinstance(software_generation, Mapping)
                and software_generation.get("status") == "runtime_launcher_process_and_source_bound"):
            handoff_id = software_generation.get("handoff_id")
            handoff_digest = software_generation.get("handoff_digest")
            if not isinstance(handoff_id, str) or not isinstance(handoff_digest, str):
                raise ProductionServingInferenceError("stored_invocation_software_generation_posture_invalid")
            try:
                historical = verify_stored_chat_process_handoff(
                    handle=self._serving._handle, handoff_id=handoff_id,
                    expected_digest=handoff_digest)
            except ChatProcessGenerationError as exc:
                raise ProductionServingInferenceError("stored_invocation_software_generation_handoff_invalid") from exc
            if dict(historical) != dict(software_generation):
                raise ProductionServingInferenceError("stored_invocation_software_generation_handoff_mismatch")
            handoff_operation = historical.get("configured_serving_operation_id")
            serving_operation = lifetime.get("serving_operation_id")
            if (handoff_operation is not None and handoff_operation != serving_operation):
                raise ProductionServingInferenceError("stored_invocation_serving_operation_handoff_mismatch")
        else:
            raise ProductionServingInferenceError("stored_invocation_software_generation_posture_invalid")
        assistant_output_lineage = None
        if assistant_text is not None:
            if not isinstance(assistant_text, str) or not assistant_text:
                raise ProductionServingInferenceError("stored_invocation_transcript_text_invalid")
            transcript_text_digest = digest_payload({"text": assistant_text})
            if not value.get("output_truncated"):
                if digest_payload({"output": assistant_text}) != value.get("output_digest"):
                    raise ProductionServingInferenceError("stored_invocation_transcript_output_mismatch")
                output_posture = "exact_invocation_output_match"
            else:
                output_posture = "truncated_transcript_original_output_relation_unknown"
            assistant_output_lineage = {
                "status": output_posture,
                "invocation_output_digest": value.get("output_digest"),
                "transcript_text_digest": transcript_text_digest,
                "output_truncated": value.get("output_truncated"),
            }
        identity_keys = ("installation_identity", "activation_state_semantic_digest", "activation_generation",
            "activation_predecessor_state_digest", "activation_receipt_id", "activation_receipt_semantic_digest",
            "model_id", "observed_loaded_model_identity", "artifact_id", "artifact_sha256", "runtime_id",
            "authority_map_digest")
        identity_keys = identity_keys + tuple(key for key in serving_reference_keys if key in lifetime)
        if any(key not in lifetime for key in identity_keys):
            raise ProductionServingInferenceError("stored_invocation_serving_identity_incomplete")
        return {"serving_identity": {key: lifetime[key] for key in identity_keys},
                "loaded_model_identity": dict(request["active_model_identity"]),
                "request_id": request["request_id"], "receipt_id": receipt_id,
                "receipt_digest": receipt_digest, "status": value["status"],
                "software_generation_attribution": dict(software_generation),
                "caller_linkage": dict(caller_context),
                "serving_receipt_lineage": serving_receipt_lineage,
                "assistant_output_lineage": assistant_output_lineage}
