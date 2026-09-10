"""Effectful, inference-free serving of the current hardened activation."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .control_plane_kernel import (AdmissionOutcome, AuthorityClass, ControlActionRequest,
                                   ControlPlaneKernel, LifecyclePhase)
from .installation_state import InstallationStateError, InstallationStateHandle
from .local_model_production_activation import ProductionActivationError, verify_current_activation
from .local_model_runtime_worker import ExactRuntimeLocalModel
from .local_runtime_provisioning import semantic_digest

PRINCIPAL = "deterministic_activated_model_serving_controller"
CAPABILITY = "local_model_production_serving"
TARGET_SUBSYSTEM = "local_model_chat"
ACTION = "establish_exact_activated_model_serving_session"
RECEIPT_SCHEMA = "sentientos.local_model_serving_session_receipt:v1"
WITNESS_SCHEMA = "sentientos.privilege_witness:model_serving:v1"
INVALIDATION_SCHEMA = "sentientos.local_model_serving_session_invalidation:v1"
MAX_OPERATION_ID_LENGTH = 128
PLACEHOLDER_OPERATION_IDS = frozenset({"*", "any", "current", "default", "latest", "placeholder", "sample", "test", "wildcard"})


class ProductionServingError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n").encode()


def _create(handle: InstallationStateHandle, relative: str, value: Mapping[str, Any]) -> None:
    obj = handle.fixed_object(relative)
    handle.ensure_directory(handle.fixed_object(relative.rsplit("/", 1)[0]))
    try:
        handle.durable_create(obj, _canonical(value))
    except InstallationStateError as exc:
        if exc.args != ("state_object_already_exists",) or handle.read_regular(obj) != _canonical(value):
            raise ProductionServingError("serving_evidence_publication_failed") from exc


def _identity(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise ProductionServingError("loaded_model_identity_missing")
    return dict(value)


def _operation_id(value: str) -> str:
    if not isinstance(value, str):
        raise ProductionServingError("serving_operation_id_invalid")
    normalized = value.strip()
    if (not normalized or normalized != value or len(normalized) > MAX_OPERATION_ID_LENGTH
            or normalized.lower() in PLACEHOLDER_OPERATION_IDS
            or any(character in normalized for character in "*?[]{}")):
        raise ProductionServingError("serving_operation_id_invalid")
    return normalized


def _verified(handle: InstallationStateHandle, allow_synthetic: bool) -> dict[str, Any]:
    try:
        verified = verify_current_activation(handle, allow_synthetic_evidence_for_tests=allow_synthetic)
    except ProductionActivationError as exc:
        raise ProductionServingError("current_hardened_activation_invalid:" + exc.code) from exc
    state, activation = verified["active_state"], verified["activation_receipt"]
    if state.get("installation_identity") != handle.identity.value:
        raise ProductionServingError("activation_installation_identity_mismatch")
    if activation.get("resulting_state_digest") != state.get("state_semantic_digest"):
        raise ProductionServingError("activation_receipt_state_mismatch")
    # The canonical verifier has re-read catalog, commissioning, and artifact bytes.  Bind
    # every state field here so a later comparison cannot accidentally narrow currentness.
    return {"active_state": dict(state), "activation_receipt": dict(activation),
            "catalog_proof": dict(verified["catalog_proof"])}


@dataclass(frozen=True, slots=True)
class ServingSession:
    """Opaque inspection record.  Deliberately contains no model or generation method."""

    session_id: str
    binding: Mapping[str, Any]
    status: str = "production_current"

    def to_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "binding": dict(self.binding), "status": self.status}


class ProductionServingController:
    """Owns at most one exact-runtime model and never exposes that model publicly."""

    def __init__(self, installation_handle: InstallationStateHandle, control_plane_kernel: ControlPlaneKernel,
                 *, model_factory: Callable[[Mapping[str, Any], Mapping[str, Any]], Any] = ExactRuntimeLocalModel,
                 allow_synthetic_evidence_for_tests: bool = False) -> None:
        if not isinstance(installation_handle, InstallationStateHandle):
            raise ProductionServingError("authenticated_installation_handle_required")
        self._handle = installation_handle
        self._kernel = control_plane_kernel
        self._factory = model_factory
        self._allow_synthetic = allow_synthetic_evidence_for_tests
        self._session: ServingSession | None = None
        self._model: Any | None = None

    def _same_activation(self, verified: Mapping[str, Any], session: ServingSession) -> bool:
        state = verified["active_state"]
        if session.binding.get("activation_state_semantic_digest") != state.get("state_semantic_digest"):
            return False
        if session.binding.get("activation_generation") != state.get("generation"):
            return False
        if session.binding.get("activation_state") != state:
            return False
        return True

    def _alive(self) -> bool:
        if self._model is None:
            return False
        process = getattr(self._model, "_process", None)
        if process is None:
            return True
        result: object = process.poll()
        return result is None

    def current_session(self) -> ServingSession | None:
        if self._session is None:
            return None
        try:
            verified = _verified(self._handle, self._allow_synthetic)
        except ProductionServingError:
            self._invalidate("current_activation_unverifiable")
            return None
        if not self._same_activation(verified, self._session):
            self._invalidate("activation_changed")
            return None
        if not self._alive():
            self._invalidate("exact_runtime_worker_dead")
            return None
        return self._session

    def establish(self, *, operation_id: str) -> ServingSession:
        operation_id = _operation_id(operation_id)
        before = _verified(self._handle, self._allow_synthetic)
        existing = self.current_session()
        if existing is not None:
            return existing
        state, activation, proof = before["active_state"], before["activation_receipt"], before["catalog_proof"]
        intent = {"installation_identity": self._handle.identity.value,
                  "activation_state_semantic_digest": state["state_semantic_digest"],
                  "activation_generation": state["generation"], "activation_receipt_id": activation["receipt_id"],
                  "activation_receipt_semantic_digest": activation["receipt_semantic_digest"],
                  "model_id": state["model_id"], "artifact_id": state["artifact_id"],
                  "runtime_id": state["runtime_id"], "authority_map_digest": state["authority_map_digest"]}
        operation_intent = {**intent, "serving_operation_id": operation_id}
        correlation = "model-serving:" + semantic_digest(operation_intent)
        decision = self._kernel.admit(ControlActionRequest(
            action_kind=ACTION, authority_class=AuthorityClass.MODEL_SERVING, actor=PRINCIPAL,
            target_subsystem=TARGET_SUBSYSTEM, requested_phase=LifecyclePhase.RUNTIME,
            metadata={**operation_intent, "correlation_id": correlation}))
        if (decision.outcome != AdmissionOutcome.ALLOW or decision.authority_class != AuthorityClass.MODEL_SERVING
                or decision.actor != PRINCIPAL or decision.action_kind != ACTION
                or decision.target_subsystem != TARGET_SUBSYSTEM or decision.correlation_id != correlation):
            raise ProductionServingError("model_serving_control_plane_not_allowed")
        chain = {key: state[key] for key in ("model_id", "artifact_path", "artifact_sha256",
                                              "artifact_size_bytes", "interpreter_path")}
        try:
            model = self._factory(chain, state["load_configuration"])
        except Exception as exc:
            raise ProductionServingError("exact_activated_model_load_failed") from exc
        try:
            observed = _identity(model.active_identity)
            expected_identity = self._commissioning_identity(state)
            required = {"posture": "production", "fallback": False, "engine": expected_identity.get("engine", "llama_cpp"),
                        "resolved_artifact_path": state["artifact_path"],
                        "model_content_sha256": state["artifact_sha256"],
                        "artifact_size_bytes": state["artifact_size_bytes"]}
            if any(observed.get(k) != v for k, v in required.items()):
                raise ProductionServingError("loaded_model_observed_identity_mismatch")
            if expected_identity.get("configuration_digest") is not None and observed.get("configuration_digest") != expected_identity["configuration_digest"]:
                raise ProductionServingError("loaded_model_configuration_identity_mismatch")
            after = _verified(self._handle, self._allow_synthetic)
            if (after["active_state"] != state or after["activation_receipt"] != activation
                    or after["catalog_proof"] != proof):
                raise ProductionServingError("activation_changed_during_load")
            binding = {**operation_intent, "control_plane_correlation_id": correlation,
                       "activation_state": state, "catalog_proof": proof,
                       "catalog_proof_semantic_digest": proof["proof_semantic_digest"],
                       "commissioning_receipt_id": state["commissioning_receipt_id"],
                       "commissioning_receipt_semantic_digest": state["commissioning_receipt_semantic_digest"],
                       **{k: state[k] for k in ("artifact_path", "artifact_sha256", "artifact_size_bytes", "route_id",
                                                "runtime_id", "interpreter_path", "load_configuration", "authority_map_digest")},
                       "observed_loaded_model_identity": observed,
                       "model_serving_admission_ref": decision.admission_decision_ref}
            session_id = "serving-session-" + semantic_digest(binding)[:24]
            session = ServingSession(session_id, MappingProxyType(binding))
            receipt = {"schema_version": RECEIPT_SCHEMA, "status": "serving_session_bound", **session.to_dict(),
                       "control_plane_authority_class": AuthorityClass.MODEL_SERVING.value,
                       "admission_outcome": "allow", "model_loaded": True, "serving_session_bound": True,
                       "inference_performed": False, "local_model_inference_authority_granted": False,
                       "adjacent_authority_granted": False}
            receipt["receipt_id"] = "serving-receipt-" + semantic_digest(receipt)[:24]
            receipt["receipt_semantic_digest"] = semantic_digest(receipt)
            witness = {"schema_version": WITNESS_SCHEMA, "session_id": session_id,
                       "receipt_id": receipt["receipt_id"], "receipt_semantic_digest": receipt["receipt_semantic_digest"],
                       "admission_decision_ref": decision.admission_decision_ref,
                       "authority_class": AuthorityClass.MODEL_SERVING.value, "inference_performed": False}
            witness["witness_semantic_digest"] = semantic_digest(witness)
            _create(self._handle, f"local-model/serving/receipts/{receipt['receipt_id']}.json", receipt)
            _create(self._handle, f"logs/privileges/{receipt['receipt_id']}.json", witness)
            self._model, self._session = model, session
            return session
        except Exception:
            model.close()
            raise

    def _commissioning_identity(self, state: Mapping[str, Any]) -> dict[str, Any]:
        obj = self._handle.fixed_object(
            f"local-model/commissioning/receipts/{state['commissioning_receipt_id']}.json")
        try:
            receipt = json.loads(self._handle.read_regular(obj))
        except (OSError, ValueError, InstallationStateError) as exc:
            raise ProductionServingError("commissioning_receipt_unavailable") from exc
        if receipt.get("receipt_semantic_digest") != state["commissioning_receipt_semantic_digest"]:
            raise ProductionServingError("commissioning_receipt_identity_mismatch")
        return _identity(receipt.get("observed_active_model_identity"))

    def _invalidate(self, reason: str) -> None:
        session, model = self._session, self._model
        self._session = self._model = None
        if model is not None:
            model.close()
        if session is None:
            return
        invalidation = {"schema_version": INVALIDATION_SCHEMA, "session_id": session.session_id,
                        "serving_operation_id": session.binding["serving_operation_id"],
                        "prior_status": session.status, "status": "non_current_unloaded", "reason": reason}
        invalidation["invalidation_id"] = "serving-invalidation-" + semantic_digest(invalidation)[:24]
        invalidation["invalidation_semantic_digest"] = semantic_digest(invalidation)
        _create(self._handle, f"local-model/serving/invalidations/{invalidation['invalidation_id']}.json", invalidation)
        self._session = replace(session, status="non_current_unloaded")
        self._session = None

    def close(self) -> None:
        self._invalidate("controller_closed")
