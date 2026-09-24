"""Bounded, preregistered developmental-model-replacement serving lifetimes."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .commissioned_model_evidence import VerifiedCommissionedModel, verify_commissioned_model
from .config import GenerationConfig, ModelCandidate, ModelConfig
from .control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionRequest, ControlPlaneKernel, LifecyclePhase
from .developmental_model_replacement_experiment import (
    PURPOSE, CognitiveModelIdentity, DevelopmentalModelReplacementError,
    ModelReplacementArtifactStore, ModelReplacementProtocol,
)
from .governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget
from .installation_state import InstallationStateError, InstallationStateHandle
from .local_model_authority import LocalModelAuthorityMap, build_local_model_authority_map, digest_payload
from .local_model_runtime_worker import ExactRuntimeLocalModel
from .local_runtime_provisioning import semantic_digest

CAPABILITY = "developmental_model_replacement_experimental_serving"
PRINCIPAL = "deterministic_developmental_model_replacement_experimental_serving_controller"
ACTION = "load_preregistered_experimental_local_model"
TARGET_SUBSYSTEM = "local_model_chat"
INTENT_SCHEMA = "sentientos.developmental_model_replacement_experimental_serving_intent:v1"
APPROVAL_SCHEMA = "sentientos.developmental_model_replacement_experimental_serving_approval:v1"
RECEIPT_SCHEMA = "sentientos.developmental_model_replacement_experimental_serving_receipt:v1"
CLOSURE_SCHEMA = "sentientos.developmental_model_replacement_experimental_serving_closure:v1"
EFFECTS = (
    "exact_operator_approval_evidence_read", "exact_preregistered_model_replacement_protocol_read",
    "exact_hardened_model_commissioning_receipt_read", "exact_model_artifact_identity_revalidation",
    "bounded_exact_experimental_local_model_load", "exact_experimental_loaded_model_identity_observation",
    "bounded_exact_experimental_local_model_unload", "experimental_model_serving_receipt_write",
)
_PLACEHOLDERS = {"", "*", "anonymous", "default", "sample", "test", "placeholder", "current", "latest", "any"}


class ExperimentalModelServingError(RuntimeError):
    def __init__(self, code: str): self.code = code; super().__init__(code)


def effect_set_digest() -> str:
    return str(semantic_digest({"effects": sorted(EFFECTS)}))


def _time(value: object) -> datetime:
    try: result = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError as exc: raise ExperimentalModelServingError("approval_time_invalid") from exc
    if result is None or result.tzinfo is None or result.utcoffset() is None:
        raise ExperimentalModelServingError("approval_time_invalid")
    return result


def _envelope(value: Mapping[str, Any], digest_key: str, prefix: str) -> dict[str, Any]:
    body = dict(value); claimed = body.pop(digest_key, None)
    if claimed != semantic_digest(body): raise ExperimentalModelServingError(prefix + "_digest_invalid")
    body[digest_key] = claimed
    return body


def approval_bindings(intent: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("target_capability", "target_principal", "effects", "effect_set_digest", "installation_identity",
            "protocol_id", "protocol_digest", "model_role", "expected_model_identity_digest",
            "commissioning_receipt_id", "commissioning_receipt_digest", "artifact_sha256", "artifact_size_bytes",
            "runtime_id", "interpreter_path", "load_configuration", "correlation_id", "intent_id", "intent_digest")
    return {key: intent[key] for key in keys}


def verify_runtime_approval(evidence: Mapping[str, Any], intent: Mapping[str, Any], *, observation_time: datetime,
                            allow_synthetic_for_tests: bool = False) -> Mapping[str, Any]:
    value = _envelope(evidence, "approval_digest", "approval")
    if value.get("schema_version") != APPROVAL_SCHEMA or value.get("approval_status") != "approved":
        raise ExperimentalModelServingError("approval_not_approved")
    for key in ("approval_evidence_id", "operator_identity", "evidence_source", "evidence_provenance"):
        item = str(value.get(key, "")).strip()
        if item.casefold() in _PLACEHOLDERS or "*" in item: raise ExperimentalModelServingError("approval_provenance_invalid")
    if value.get("synthetic_test_evidence") is not False and not allow_synthetic_for_tests:
        raise ExperimentalModelServingError("synthetic_approval_forbidden")
    for key, expected in approval_bindings(intent).items():
        if value.get(key) != expected: raise ExperimentalModelServingError("approval_" + key + "_mismatch")
    not_before, approved, expires = (_time(value.get(k)) for k in ("not_before", "approval_timestamp", "expires_at"))
    if not_before > approved or approved > expires: raise ExperimentalModelServingError("approval_interval_invalid")
    if observation_time < not_before: raise ExperimentalModelServingError("approval_not_yet_valid")
    if observation_time > expires: raise ExperimentalModelServingError("approval_expired")
    return MappingProxyType(value)


def _create(handle: InstallationStateHandle, relative: str, value: Mapping[str, Any]) -> None:
    data = ( __import__("json").dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n").encode()
    try: handle.durable_create(handle.fixed_object(relative), data)
    except InstallationStateError as exc:
        if exc.args != ("state_object_already_exists",) or handle.read_regular(handle.fixed_object(relative)) != data: raise


def _loaded_identity(evidence: VerifiedCommissionedModel, observed: Mapping[str, Any]) -> CognitiveModelIdentity:
    prior = evidence.cognitive_identity
    payload = dict(observed)
    from .developmental_model_replacement_experiment import _digest
    return CognitiveModelIdentity.create(
        model_id=prior.model_id, semantic_artifact_identity=str(payload["semantic_artifact_identity"]),
        model_content_sha256=str(payload["model_content_sha256"]), artifact_size_bytes=payload.get("artifact_size_bytes"),
        sidecar_metadata_digest=payload.get("sidecar_metadata_digest"), configuration_digest=str(payload["configuration_digest"]),
        engine_runtime_family=str(payload["engine"]), candidate_index=payload.get("candidate_index"),
        active_production=payload.get("posture") == "production", fallback=bool(payload.get("fallback")),
        authority_record_id=prior.authority_record_id, authority_record_digest=prior.authority_record_digest,
        active_model_identity=payload, active_model_identity_digest=_digest(payload))


class ExperimentalModelServingController:
    """Own exact workers outside canonical activation and production-serving custody."""
    def __init__(self, installation_handle: InstallationStateHandle, control_plane_kernel: ControlPlaneKernel,
                 *, artifact_root: Path, model_factory: Callable[[Mapping[str, Any], Mapping[str, Any]], Any] = ExactRuntimeLocalModel,
                 allow_synthetic_evidence_for_tests: bool = False) -> None:
        if not isinstance(installation_handle, InstallationStateHandle):
            raise ExperimentalModelServingError("authenticated_installation_handle_required")
        self._handle, self._kernel, self._store = installation_handle, control_plane_kernel, ModelReplacementArtifactStore(artifact_root)
        self._factory, self._allow_synthetic = model_factory, allow_synthetic_evidence_for_tests
        for item in ("local-model", "local-model/developmental-model-replacement",
                     "local-model/developmental-model-replacement/experimental-serving",
                     "local-model/developmental-model-replacement/experimental-serving/receipts"):
            installation_handle.ensure_directory(installation_handle.fixed_object(item))

    def prepare_intent(self, *, protocol_id: str, protocol_digest: str, model_role: str,
                       commissioning_receipt_id: str, correlation_id: str) -> Mapping[str, Any]:
        if model_role not in {"model_a", "model_b"}: raise ExperimentalModelServingError("model_role_invalid")
        if not correlation_id or correlation_id.casefold() in _PLACEHOLDERS or "*" in correlation_id:
            raise ExperimentalModelServingError("correlation_id_invalid")
        protocol = self._store.load_verified_protocol(protocol_id, protocol_digest)
        evidence = verify_commissioned_model(self._handle, commissioning_receipt_id,
                                              allow_synthetic_for_tests=self._allow_synthetic)
        expected = protocol.model_a_identity if model_role == "model_a" else protocol.model_b_identity
        if evidence.cognitive_identity != expected: raise ExperimentalModelServingError("commissioned_identity_not_preregistered")
        receipt = evidence.receipt
        value: dict[str, Any] = {
            "schema_version": INTENT_SCHEMA, "target_capability": CAPABILITY, "target_principal": PRINCIPAL,
            "effects": sorted(EFFECTS), "effect_set_digest": effect_set_digest(),
            "installation_identity": self._handle.identity.value, "protocol_id": protocol_id,
            "protocol_digest": protocol_digest, "model_role": model_role,
            "expected_model_identity": asdict(expected), "expected_model_identity_digest": expected.identity_digest,
            "commissioning_receipt_id": commissioning_receipt_id,
            "commissioning_receipt_digest": receipt["receipt_semantic_digest"],
            "commissioning_lineage": {k: receipt[k] for k in ("commissioning_intent_id", "commissioning_intent_digest",
                "commissioning_plan_digest", "model_commissioning_admission_ref", "smoke_local_model_inference_admission_ref")},
            "artifact_path": evidence.artifact_path, "artifact_sha256": evidence.artifact_sha256,
            "artifact_size_bytes": evidence.artifact_size_bytes, "runtime_id": receipt["runtime_id"],
            "interpreter_path": receipt["interpreter_path"], "load_configuration": receipt["load_configuration"],
            "authority_map_digest": receipt["authority_map_digest"], "authority_record_id": expected.authority_record_id,
            "correlation_id": correlation_id,
            "custody_destination": "local-model/developmental-model-replacement/experimental-serving/receipts",
            "model_load_performed": False, "inference_performed": False,
        }
        seed = semantic_digest(value); value["intent_id"] = "experimental-serving-intent-" + seed[:24]
        value["intent_digest"] = semantic_digest(value)
        return MappingProxyType(value)

    def establish(self, *, intent: Mapping[str, Any], approval: Mapping[str, Any], observation_time: datetime) -> "ExperimentalCognitiveEndpoint":
        intent = MappingProxyType(_envelope(intent, "intent_digest", "intent"))
        verified_approval = verify_runtime_approval(approval, intent, observation_time=observation_time,
                                                    allow_synthetic_for_tests=self._allow_synthetic)
        # Re-read every input immediately before admission and construction.
        protocol = self._store.load_verified_protocol(str(intent["protocol_id"]), str(intent["protocol_digest"]))
        evidence = verify_commissioned_model(self._handle, str(intent["commissioning_receipt_id"]),
                                              allow_synthetic_for_tests=self._allow_synthetic)
        expected = protocol.model_a_identity if intent["model_role"] == "model_a" else protocol.model_b_identity
        if expected.identity_digest != intent["expected_model_identity_digest"] or evidence.cognitive_identity != expected:
            raise ExperimentalModelServingError("pre_effect_identity_changed")
        verify_runtime_approval(verified_approval, intent, observation_time=observation_time,
                                allow_synthetic_for_tests=self._allow_synthetic)
        decision = self._kernel.admit(ControlActionRequest(ACTION, AuthorityClass.MODEL_SERVING, PRINCIPAL,
            TARGET_SUBSYSTEM, LifecyclePhase.RUNTIME, {"correlation_id": intent["correlation_id"],
            "serving_intent_id": intent["intent_id"], "serving_intent_digest": intent["intent_digest"],
            "approval_evidence_id": verified_approval["approval_evidence_id"],
            "approval_digest": verified_approval["approval_digest"]}))
        if (decision.outcome != AdmissionOutcome.ALLOW or decision.authority_class != AuthorityClass.MODEL_SERVING
                or decision.actor != PRINCIPAL or decision.action_kind != ACTION or decision.target_subsystem != TARGET_SUBSYSTEM
                or decision.correlation_id != intent["correlation_id"]):
            raise ExperimentalModelServingError("model_serving_control_plane_not_allowed")
        chain = {key: intent[key] for key in ("model_id", "artifact_path", "artifact_sha256", "artifact_size_bytes", "interpreter_path")} if "model_id" in intent else {
            "model_id": expected.model_id, **{key: intent[key] for key in ("artifact_path", "artifact_sha256", "artifact_size_bytes", "interpreter_path")}}
        try: worker = self._factory(chain, intent["load_configuration"])
        except Exception as exc: raise ExperimentalModelServingError("experimental_model_load_failed") from exc
        try:
            observed = worker.active_identity.to_dict()
            loaded = _loaded_identity(evidence, observed)
            loaded.verify()
            if loaded != expected: raise ExperimentalModelServingError("loaded_cognitive_identity_mismatch")
            lifetime_seed = {"intent_id": intent["intent_id"], "admission": decision.admission_decision_ref}
            lifetime = "experimental-serving-lifetime-" + semantic_digest(lifetime_seed)[:24]
            receipt: dict[str, Any] = {"schema_version": RECEIPT_SCHEMA, "status": "experimental_serving_bound",
                "protocol_id": protocol.protocol_id, "protocol_digest": protocol.protocol_digest, "model_role": intent["model_role"],
                "expected_cognitive_identity": asdict(expected), "observed_cognitive_identity": asdict(loaded),
                "commissioning_receipt_id": intent["commissioning_receipt_id"],
                "commissioning_receipt_digest": intent["commissioning_receipt_digest"],
                "artifact_sha256": intent["artifact_sha256"], "artifact_size_bytes": intent["artifact_size_bytes"],
                "runtime_id": intent["runtime_id"], "load_configuration": intent["load_configuration"],
                "approval_evidence_id": verified_approval["approval_evidence_id"], "approval_digest": verified_approval["approval_digest"],
                "model_serving_admission_ref": decision.admission_decision_ref, "serving_lifetime_id": lifetime,
                "worker_identity": observed, "canonical_activation_mutated": False,
                "canonical_production_serving_mutated": False, "inference_authority_granted": False,
                "inference_performed_by_serving_transition": False,
                "evidence_posture": "synthetic_test" if (verified_approval.get("synthetic_test_evidence") or
                    evidence.receipt.get("synthetic_test_evidence")) else "production_eligible_not_experiment_result"}
            receipt["receipt_id"] = "experimental-serving-receipt-" + semantic_digest(receipt)[:24]
            receipt["receipt_digest"] = semantic_digest(receipt)
            _create(self._handle, f"local-model/developmental-model-replacement/experimental-serving/receipts/{receipt['receipt_id']}.json", receipt)
            return ExperimentalCognitiveEndpoint(self, worker, protocol, evidence, expected, intent, receipt)
        except Exception:
            worker.close()
            raise


class ExperimentalCognitiveEndpoint:
    __slots__ = ("_controller", "_worker", "_protocol", "_evidence", "_expected", "_intent", "_receipt", "_closure", "_closed")
    def __init__(self, controller: ExperimentalModelServingController, worker: Any, protocol: ModelReplacementProtocol,
                 evidence: VerifiedCommissionedModel, expected: CognitiveModelIdentity, intent: Mapping[str, Any], receipt: Mapping[str, Any]):
        self._controller, self._worker, self._protocol, self._evidence = controller, worker, protocol, evidence
        self._expected, self._intent, self._receipt, self._closed = expected, intent, receipt, False
        self._closure: Mapping[str, Any] | None = None

    @property
    def serving_receipt(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self._receipt))

    @property
    def closure_receipt(self) -> Mapping[str, Any] | None:
        return None if self._closure is None else MappingProxyType(dict(self._closure))

    def current_identity(self) -> CognitiveModelIdentity:
        self._current(); return self._expected

    def _current(self) -> None:
        if self._closed: raise ExperimentalModelServingError("experimental_endpoint_closed")
        process = getattr(self._worker, "_process", None)
        if process is not None and process.poll() is not None: self._invalidate("worker_dead"); raise ExperimentalModelServingError("worker_dead")
        try:
            protocol = self._controller._store.load_verified_protocol(self._protocol.protocol_id, self._protocol.protocol_digest)
            evidence = verify_commissioned_model(self._controller._handle, str(self._intent["commissioning_receipt_id"]),
                                                  allow_synthetic_for_tests=self._controller._allow_synthetic)
            loaded = _loaded_identity(evidence, self._worker.active_identity.to_dict())
            if protocol != self._protocol or evidence.cognitive_identity != self._expected or loaded != self._expected:
                raise ExperimentalModelServingError("experimental_serving_currentness_changed")
        except Exception:
            self._invalidate("currentness_changed")
            raise

    def infer(self, *, purpose: str, prompt: str, correlation_id: str, budget: Mapping[str, Any],
              generation_posture: Mapping[str, Any], upstream_evidence: Mapping[str, Any]) -> Mapping[str, Any]:
        if purpose != PURPOSE or generation_posture.get("temperature") != 0:
            raise ExperimentalModelServingError("experiment_inference_posture_invalid")
        self._current()
        receipt = self._evidence.receipt
        config = ModelConfig([ModelCandidate(Path(self._evidence.artifact_path), "llama_cpp", str(receipt["model_id"]),
                    {"gpu_layers": int(receipt["load_configuration"]["n_gpu_layers"])})], default_engine="llama_cpp",
                    max_context_tokens=int(receipt["load_configuration"]["n_ctx"]),
                    generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1))
        authority: LocalModelAuthorityMap = build_local_model_authority_map(config, allowed_roots=[Path(self._evidence.artifact_path).parent],
                                                                            observed_at="1970-01-01T00:00:00+00:00")
        if authority.map_digest != receipt["authority_map_digest"]:
            self._invalidate("authority_map_changed"); raise ExperimentalModelServingError("authority_map_digest_mismatch")
        invoker = GovernedLocalModelInvoker(model=self._worker, authority_map=authority, kernel=self._controller._kernel,
            runtime_root=self._controller._handle.root / "local-model" / "developmental-model-replacement" / "experimental-serving" / "inference")
        kwargs = {key: budget[key] for key in LocalModelInvocationBudget.__dataclass_fields__ if key in budget}
        request = invoker.build_request(purpose=PURPOSE, prompt=prompt, caller=PRINCIPAL, correlation_id=correlation_id,
            budget=LocalModelInvocationBudget(**kwargs), upstream_evidence=upstream_evidence,
            linkage={"experimental_serving_lifetime_id": self._receipt["serving_lifetime_id"],
                     "model_serving_admission_ref": self._receipt["model_serving_admission_ref"]})
        result = invoker.invoke(request, pre_effect_guard=self._current, post_effect_guard=self._current)
        if result.admission_decision_ref == self._receipt["model_serving_admission_ref"]:
            self._invalidate("inference_admission_not_independent"); raise ExperimentalModelServingError("inference_admission_not_independent")
        return {"status": result.status, "fallback_occurred": result.fallback_occurred,
                "request_id": request.request_id, "request_digest": request.request_digest,
                "inference_receipt_id": result.receipt_id, "inference_receipt_digest": result.receipt_digest,
                "output_digest": result.output_digest,
                "actual_generation_parameters": result.generation_config.get("actual_generation_parameters", {})}

    def _invalidate(self, reason: str) -> None:
        if not self._closed: self.close(reason=reason, status="invalidated")

    def close(self, *, reason: str = "operator_close", status: str = "closed") -> None:
        if self._closed: return
        self._closed = True
        try: self._worker.close()
        finally:
            value: dict[str, Any] = {"schema_version": CLOSURE_SCHEMA, "status": status,
                "serving_lifetime_id": self._receipt["serving_lifetime_id"], "bounded_unload_performed": True,
                "unload_reason": reason, "prior_serving_receipt_id": self._receipt["receipt_id"],
                "prior_serving_receipt_digest": self._receipt["receipt_digest"], "worker_current": False}
            value["closure_id"] = "experimental-serving-closure-" + semantic_digest(value)[:24]
            value["closure_digest"] = semantic_digest(value)
            _create(self._controller._handle, f"local-model/developmental-model-replacement/experimental-serving/receipts/{value['closure_id']}.json", value)
            self._closure = value

    def __enter__(self) -> "ExperimentalCognitiveEndpoint": return self
    def __exit__(self, *_: object) -> None: self.close()
