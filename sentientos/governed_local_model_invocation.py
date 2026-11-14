from __future__ import annotations

import json, math, os, time, concurrent.futures, threading, uuid
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, cast

from .control_plane_kernel import (AdmissionOutcome, AuthorityClass,
    ControlActionDecision, ControlActionRequest, ControlPlaneKernel,
    LifecyclePhase, get_control_plane_kernel)
from .local_model_authority import (LocalModelAuthorityMap, LocalModelAuthorityRecord,
    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE, ROOTLESS_EXPERIMENTAL_PURPOSE,
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES,
    atomic_write_json, digest_payload, validate_authority_map)
from .causal_resource_principal import CausalResourcePrincipal
from .causal_resource_principal_authentication import AuthenticatedRootPrincipalEvidence
from .causal_resource_principal_currentness import CurrentAuthenticatedRootPrincipalEvidence
from .governed_local_model_resource_allocation import (
    GovernedLocalModelResourceAllocation,
    GovernedLocalModelResourceAllocator,
    GovernedLocalModelResourceError,
    GovernedLocalModelResourcePolicy,
)

class LocalModelInvoker(Protocol):
    def build_request(self, **kwargs: Any) -> Any: ...
    def invoke(self, request: Any, **kwargs: Any) -> Any: ...


INTERVENTION_PURPOSE = "resident_developmental_history_intervention_experiment"
MODEL_REPLACEMENT_PURPOSE = "resident_developmental_model_replacement_experiment"
SUPPORTED_PURPOSES = {"local_user_chat", "local_model_commissioning_smoke", "genesis_proposal_advice", "discernment_judgment", "maintenance_implementation", "resident_developmental_interpretation", "resident_developmental_retrieval_cognition", INTERVENTION_PURPOSE, "resident_developmental_model_replacement_experiment", ROOTLESS_EXPERIMENTAL_PURPOSE, ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE}
FORBIDDEN_EFFECTS = {"provider_network": False, "tool": False, "memory": False, "action": False, "adoption": False, "repository_mutation": False}
INVOCATION_RECEIPT_SCHEMA = "sentientos.local_model_invocation_receipt:v2"
INVOCATION_RECEIPT_SCHEMA_V3 = "sentientos.local_model_invocation_receipt:v3"
INVOCATION_RECEIPT_SCHEMA_V4 = "sentientos.local_model_invocation_receipt:v4"
LLAMA_COMPLETION_OBSERVATION_SCHEMA_V1 = "sentientos.llama_cpp_completion_observation:v1"
LLAMA_COMPLETION_OBSERVATION_SCHEMA = "sentientos.llama_cpp_completion_observation:v2"
LLAMA_COMPLETION_OBSERVATION_SCHEMA_V3 = "sentientos.llama_cpp_completion_observation:v3"
LLAMA_INVOCATION_RESOURCE_OBSERVATION_SCHEMA = (
    "sentientos.llama_cpp_invocation_resource_observation:v1")
LLAMA_BACKEND_THREAD_LIMIT_CONTROL_SCHEMA = (
    "sentientos.llama_cpp_backend_thread_limit_control:v1")
MAX_INVOCATION_RECEIPT_BYTES = 256 * 1024
MAX_INVOCATION_RECEIPTS = 256
OLLAMA_BACKEND_DIAGNOSTICS = frozenset({
    "ollama_server_memory_pressure",
    "ollama_server_context_limit",
    "ollama_server_model_unavailable",
    "ollama_server_worker_failure",
    "ollama_server_request_rejected",
    "ollama_server_other",
})


def validate_llama_completion_observation(value: object) -> bool:
    """Validate bounded backend facts and optional exact-worker resource measurements."""
    if not isinstance(value, Mapping):
        return False
    common = {"schema_version", "backend", "finish_reason", "completion_tokens",
              "prompt_tokens", "token_limit_reached"}
    schema = value.get("schema_version")
    if schema == LLAMA_COMPLETION_OBSERVATION_SCHEMA_V1:
        if set(value) != common:
            return False
    elif schema in {LLAMA_COMPLETION_OBSERVATION_SCHEMA,
                    LLAMA_COMPLETION_OBSERVATION_SCHEMA_V3}:
        expected = common | {"invocation_resources"}
        if schema == LLAMA_COMPLETION_OBSERVATION_SCHEMA_V3:
            expected.add("backend_thread_limit_control")
        if set(value) != expected:
            return False
        metrics = value.get("invocation_resources")
        if (not isinstance(metrics, Mapping)
                or set(metrics) != {"schema_version", "user_cpu_seconds",
                    "system_cpu_seconds", "wall_seconds", "process_peak_rss_bytes"}
                or metrics.get("schema_version") != LLAMA_INVOCATION_RESOURCE_OBSERVATION_SCHEMA):
            return False
        for name in ("user_cpu_seconds", "system_cpu_seconds", "wall_seconds"):
            metric = metrics.get(name)
            if metric is not None:
                try:
                    valid_metric = (not isinstance(metric, bool)
                        and isinstance(metric, (int, float))
                        and math.isfinite(float(metric)) and 0 <= float(metric) <= 3600)
                except (OverflowError, TypeError, ValueError):
                    valid_metric = False
                if not valid_metric:
                    return False
        rss = metrics.get("process_peak_rss_bytes")
        if rss is not None and (type(rss) is not int or not 0 <= rss <= 1_099_511_627_776):
            return False
        if schema == LLAMA_COMPLETION_OBSERVATION_SCHEMA_V3:
            control = value.get("backend_thread_limit_control")
            if (not isinstance(control, Mapping)
                    or set(control) != {"schema_version", "requested_ceiling",
                        "setter_function", "n_threads_argument", "n_threads_batch_argument"}
                    or control.get("schema_version") != LLAMA_BACKEND_THREAD_LIMIT_CONTROL_SCHEMA):
                return False
            requested = control.get("requested_ceiling")
            setter = control.get("setter_function")
            n_threads = control.get("n_threads_argument")
            n_threads_batch = control.get("n_threads_batch_argument")
            if requested is None:
                if setter is not None or n_threads is not None or n_threads_batch is not None:
                    return False
            elif (type(requested) is not int or not 1 <= requested <= 256
                    or setter != "llama_set_n_threads"
                    or type(n_threads) is not int or not 1 <= n_threads <= requested
                    or type(n_threads_batch) is not int
                    or not 1 <= n_threads_batch <= requested):
                return False
    else:
        return False
    if (value.get("backend") != "llama_cpp"
            or value.get("finish_reason") not in {"stop", "length", "unknown"}
            or any(value.get(name) is not None and (type(value.get(name)) is not int
                or not 0 <= value[name] <= 131072)
                for name in ("completion_tokens", "prompt_tokens"))
            or value.get("token_limit_reached") is not (
                True if value.get("finish_reason") == "length" else
                False if value.get("finish_reason") == "stop" else None)):
        return False
    return True


def validate_backend_completion_observation(value: object) -> bool:
    """Validate bounded completion facts from supported local inference backends."""
    if validate_llama_completion_observation(value):
        return True
    keys = {"schema_version", "backend", "finish_reason", "completion_tokens",
        "prompt_tokens", "token_limit_reached", "total_duration_ns",
        "load_duration_ns", "prompt_eval_duration_ns", "eval_duration_ns"}
    if not isinstance(value, Mapping):
        return False
    schema = value.get("schema_version")
    if schema == "sentientos.ollama_completion_observation:v1":
        if set(value) != keys:
            return False
    elif schema == "sentientos.ollama_completion_observation:v2":
        if set(value) != keys | {"first_token_duration_ns"}:
            return False
        first_token = value.get("first_token_duration_ns")
        if (first_token is not None and (type(first_token) is not int
                or not 0 <= first_token <= 3_600_000_000_000)):
            return False
    else:
        return False
    if (value.get("backend") != "ollama"
            or value.get("finish_reason") not in {"stop", "length", "unknown"}
            or value.get("token_limit_reached") is not (
                True if value.get("finish_reason") == "length" else
                False if value.get("finish_reason") == "stop" else None)):
        return False
    for key, maximum in (("completion_tokens", 131072), ("prompt_tokens", 131072),
            ("total_duration_ns", 3_600_000_000_000), ("load_duration_ns", 3_600_000_000_000),
            ("prompt_eval_duration_ns", 3_600_000_000_000), ("eval_duration_ns", 3_600_000_000_000)):
        item = value.get(key)
        if item is not None and (type(item) is not int or not 0 <= item <= maximum):
            return False
    return True
RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["conclusion", "lesson_candidate"],
    "additionalProperties": False,
    "properties": {
        "conclusion": {"type": "string", "minLength": 1, "maxLength": 2500},
        "lesson_candidate": {
            "anyOf": [
                {"type": "null"},
                {"type": "object", "additionalProperties": False,
                 "required": ["statement", "scope", "applicability", "uncertainty",
                              "uncertainty_rationale", "evidence_dependencies",
                              "possible_contradiction_ids"],
                 "properties": {
                    "statement": {"type": "string", "minLength": 1, "maxLength": 1200},
                    "scope": {"type": "string", "minLength": 1, "maxLength": 400},
                    "applicability": {"type": "string", "minLength": 1, "maxLength": 500},
                    "uncertainty": {"type": "string", "enum": ["low", "medium", "high", "unknown"]},
                    "uncertainty_rationale": {"type": "string", "minLength": 1, "maxLength": 500},
                    "evidence_dependencies": {"type": "array", "minItems": 1, "maxItems": 8,
                        "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 256}},
                    "possible_contradiction_ids": {"type": "array", "maxItems": 8,
                        "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 256}},
                 }},
            ],
        },
    },
}
RESIDENT_COMPANION_INTERACTION_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["disposition", "response", "evidence_ids", "history_record_ids"],
    "additionalProperties": False,
    "properties": {
        "disposition": {"type": "string", "enum": ["answer", "ask", "abstain"]},
        "response": {"type": "string", "minLength": 1, "maxLength": 1600},
        "evidence_ids": {"type": "array", "maxItems": 32, "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 256}},
        "history_record_ids": {"type": "array", "maxItems": 16, "uniqueItems": True,
            "items": {"type": "string", "pattern": "^devrec-[0-9a-f]{24}$"}},
    },
}
# Keep decoding controls identical in all history-intervention conditions.
RESIDENT_COMPANION_HISTORY_INTERVENTION_OUTPUT_SCHEMA = (
    RESIDENT_COMPANION_INTERACTION_OUTPUT_SCHEMA)
# Keep decoding controls identical in all history-intervention conditions. Withheld
# citations are rejected after inference against the empty retrieved-record allowlist.
RESIDENT_COMPANION_HISTORY_WITHHELD_OUTPUT_SCHEMA = (
    RESIDENT_COMPANION_HISTORY_INTERVENTION_OUTPUT_SCHEMA)

# Objective history interventions use one closed JSON shape for both single
# probes and suites.  The deterministic scorer still binds the exact probe
# count and rejects non-canonical or incomplete answers; this schema only
# constrains generation to the appropriate answer container.
RESIDENT_OBJECTIVE_TASK_ANSWER_OUTPUT_SCHEMA = {
    "type": "object",
    "oneOf": [
        {"required": ["answer"]},
        {"required": ["answers"]},
    ],
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "integer"},
        "answers": {"type": "array", "minItems": 2, "maxItems": 16,
            "items": {"type": "integer"}},
    },
}


def companion_history_output_schema(condition_id: Any) -> Mapping[str, Any]:
    return RESIDENT_COMPANION_HISTORY_INTERVENTION_OUTPUT_SCHEMA
RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA = {
    "type": "object", "required": ["conclusion", "reason_code", "evidence_ids"],
    "additionalProperties": False,
    "properties": {
        "conclusion": {"type": "string", "enum": ["unknown", "suspended",
            "provisionally_supported", "supported", "contested",
            "provisionally_contradicted", "contradicted", "superseded"]},
        "reason_code": {"type": "string", "minLength": 1, "maxLength": 128},
        "evidence_ids": {"type": "array", "maxItems": 256, "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 256}},
    },
}

def _digest_text(payload: Any) -> str:
    value: str = digest_payload(payload)
    return value


def _verified_model_execution_profile(
    model: Any, record: LocalModelAuthorityRecord | None,
) -> dict[str, Any] | None:
    """Describe accelerator use from a verified active local model identity."""
    if record is None or record.engine not in {"llama_cpp", "transformers"}:
        return None
    try:
        from .config import ModelConfig
        from .local_model import ActiveModelIdentity, LocalModel, candidate_configuration_digest

        if type(model) is not LocalModel:
            return None
        identity = getattr(model, "active_identity", None)
        if (type(identity) is not ActiveModelIdentity or identity.fallback
                or identity.engine != record.engine or identity.posture != "production"
                or identity.configuration_digest != record.configuration_digest):
            return None

        def profile(route: str, layers: int | None = None) -> dict[str, Any]:
            return {
                "schema_version": "sentientos.model_execution_profile:v1",
                "engine": identity.engine,
                "accelerator_route": route,
                "gpu_layers": layers,
                "configuration_digest": identity.configuration_digest,
            }

        config = getattr(model, "config", None)
        if (type(config) is not ModelConfig
                or type(identity.candidate_index) is not int
                or not isinstance(getattr(config, "candidates", None), list)
                or not 0 <= identity.candidate_index < len(config.candidates)):
            return profile("unknown")
        candidate = config.candidates[identity.candidate_index]
        engine = candidate.engine or config.default_engine
        if engine == "auto":
            engine = LocalModel._guess_engine(candidate)
        try:
            configuration_matches = (
                str(engine).lower() == identity.engine
                and candidate_configuration_digest(candidate, config, identity.engine)
                    == identity.configuration_digest)
        except (AttributeError, TypeError, ValueError):
            configuration_matches = False
        if not configuration_matches:
            return profile("unknown")
        layers: int | None = None
        accelerator_route = "unknown"
        if identity.engine == "llama_cpp":
            layers_value = candidate.options.get("gpu_layers", 0)
            if layers_value is None:
                layers_value = 0
            if type(layers_value) is int and 0 <= layers_value <= 256:
                layers = layers_value
                accelerator_route = "gpu" if layers > 0 else "cpu"
        elif identity.engine == "transformers":
            backend_model = getattr(getattr(model, "backend", None), "_model", None)
            try:
                device_map = getattr(backend_model, "hf_device_map", None)
            except Exception:
                device_map = None
            if isinstance(device_map, Mapping) and device_map:
                routes: list[str] = []
                for device in device_map.values():
                    if type(device) is int:
                        routes.append("gpu")
                    elif isinstance(device, str) and device.casefold().startswith(("cuda", "gpu")):
                        routes.append("gpu")
                    elif isinstance(device, str) and device.casefold() in {"cpu", "disk"}:
                        routes.append("cpu")
                    else:
                        try:
                            device_type = getattr(device, "type", None)
                        except Exception:
                            device_type = None
                        routes.append("gpu" if device_type == "cuda" else
                                      "cpu" if device_type == "cpu" else "unknown")
                accelerator_route = ("gpu" if "gpu" in routes else
                                     "unknown" if "unknown" in routes else "cpu")
            else:
                try:
                    device = getattr(backend_model, "device", None)
                    device_type = getattr(device, "type", None)
                except Exception:
                    device_type = None
                if device_type == "cuda":
                    accelerator_route = "gpu"
                elif device_type == "cpu":
                    accelerator_route = "cpu"
        return profile(accelerator_route, layers)
    except (AttributeError, IndexError, TypeError, ValueError):
        return None

@dataclass(frozen=True)
class LocalModelInvocationBudget:
    max_input_chars: int = 8000
    max_output_chars: int = 4000
    max_new_tokens: int = 512
    timeout_seconds: float = 30.0
    max_calls_per_correlation: int = 1

    def to_dict(self) -> dict[str, Any]: return dict(self.__dict__)

@dataclass(frozen=True)
class LocalModelInvocationRequest:
    purpose: str
    prompt: str
    model_id: str
    authority_map_digest: str
    model_artifact_digest: str | None
    caller: str
    lifecycle_phase: str
    correlation_id: str
    expected_output_format: str = "text"
    budget: LocalModelInvocationBudget = field(default_factory=LocalModelInvocationBudget)
    upstream_evidence: Mapping[str, Any] = field(default_factory=dict)
    linkage: Mapping[str, Any] = field(default_factory=dict)
    active_model_identity: Mapping[str, Any] = field(default_factory=dict)
    structured_output_schema: Mapping[str, Any] | None = None

    def semantic_payload(self) -> dict[str, Any]:
        return {"purpose": self.purpose, "prompt_digest": digest_payload({"prompt": self.prompt}), "prompt_size": len(self.prompt.encode("utf-8")), "model_id": self.model_id, "authority_map_digest": self.authority_map_digest, "model_artifact_digest": self.model_artifact_digest, "active_model_identity": dict(self.active_model_identity), "caller": self.caller, "lifecycle_phase": self.lifecycle_phase, "correlation_id": self.correlation_id, "expected_output_format": self.expected_output_format, "structured_output_schema": dict(self.structured_output_schema) if self.structured_output_schema is not None else None, "budget": self.budget.to_dict(), "upstream_evidence": dict(self.upstream_evidence), "linkage": dict(self.linkage), "allowed_effects": {"local_model_inference": True}, "forbidden_effects": dict(FORBIDDEN_EFFECTS)}

    @property
    def request_digest(self) -> str: return _digest_text(self.semantic_payload())
    @property
    def request_id(self) -> str: return "lmreq-" + self.request_digest[:24]

    def to_receipt_request_dict(self) -> dict[str, Any]:
        p = self.semantic_payload(); p.update({"request_id": self.request_id, "request_digest": self.request_digest, "raw_prompt_stored": False, "ephemeral_prompt_handling": "raw prompt used only for immediate local backend call"}); return p

@dataclass(frozen=True)
class LocalModelInvocationDecision:
    admitted: bool
    status: str
    reason_codes: tuple[str, ...]
    admission_decision_ref: str | None
    control_plane: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class GovernedLocalModelResourceInvocationContext:
    """Trusted, process-local inputs for an explicitly resource-backed call.

    This type intentionally has no mapping/JSON constructor: request data cannot
    manufacture allocator custody or verified principal evidence.
    """

    allocator: GovernedLocalModelResourceAllocator
    allocation: GovernedLocalModelResourceAllocation
    principal: CausalResourcePrincipal
    authenticated: AuthenticatedRootPrincipalEvidence
    current: CurrentAuthenticatedRootPrincipalEvidence
    policy: GovernedLocalModelResourcePolicy
    durable_attempt_nonce: str
    clock: Callable[[], str]

@dataclass(frozen=True)
class LocalModelInvocationReceipt:
    request: Mapping[str, Any]
    status: str
    reason_codes: tuple[str, ...]
    output_text: str | None
    output_digest: str | None
    output_size_bytes: int
    generation_config: Mapping[str, Any]
    admission_decision_ref: str | None
    purpose: str
    latency_ms: int
    output_truncated: bool
    fallback_occurred: bool
    effects: Mapping[str, bool]
    observed_at: str
    resource_allocation_digest: str | None = None
    resource_attempt_id: str | None = None
    resource_consumption_receipt_digests: tuple[str, ...] = ()
    resource_linkage_digest: str | None = None
    schema_version: str = INVOCATION_RECEIPT_SCHEMA
    backend_completion: Mapping[str, Any] | None = None
    cancellation_admission_decision_ref: str | None = None

    def semantic_payload(self) -> dict[str, Any]:
        payload = {"schema_version": self.schema_version, "request": dict(self.request),
            "status": self.status, "reason_codes": list(self.reason_codes),
            "output_digest": self.output_digest, "output_size_bytes": self.output_size_bytes,
            "generation_config": dict(self.generation_config),
            "admission_decision_ref": self.admission_decision_ref, "purpose": self.purpose,
            "output_truncated": self.output_truncated, "fallback_occurred": self.fallback_occurred,
            "effects": dict(self.effects), "observed_at": self.observed_at}
        if self.schema_version == INVOCATION_RECEIPT_SCHEMA_V3:
            payload["backend_completion"] = (dict(self.backend_completion)
                if self.backend_completion is not None else None)
        if self.schema_version == INVOCATION_RECEIPT_SCHEMA_V4:
            payload["backend_completion"] = (dict(self.backend_completion)
                if self.backend_completion is not None else None)
            payload["cancellation_admission_decision_ref"] = self.cancellation_admission_decision_ref
        return payload

    @property
    def receipt_digest(self) -> str: return _digest_text(self.semantic_payload())
    @property
    def receipt_id(self) -> str: return "lmrec-" + self.receipt_digest[:24]
    def to_dict(self, *, include_output: bool = False) -> dict[str, Any]:
        p = self.semantic_payload(); p.update({"receipt_id": self.receipt_id, "receipt_digest": self.receipt_digest, "latency_ms": self.latency_ms,
            "resource_allocation_digest": self.resource_allocation_digest,
            "resource_attempt_id": self.resource_attempt_id,
            "resource_consumption_receipt_digests": list(self.resource_consumption_receipt_digests)})
        if self.resource_linkage_digest is not None:
            p["resource_linkage_digest"] = self.resource_linkage_digest
        if include_output and self.output_text is not None: p["output_text"] = self.output_text
        return p


@dataclass(frozen=True)
class LocalModelResidencyReleaseReceipt:
    correlation_id: str
    model_identity_digest: str
    reason_code: str
    status: str
    reason_codes: tuple[str, ...]
    admission_decision_ref: str
    backend_result: Mapping[str, Any] | None
    observed_at: str

    def semantic_payload(self) -> dict[str, Any]:
        return {"schema_version": "sentientos.local_model_residency_release:v1",
            "correlation_id": self.correlation_id,
            "model_identity_digest": self.model_identity_digest,
            "reason_code": self.reason_code, "status": self.status,
            "reason_codes": list(self.reason_codes),
            "admission_decision_ref": self.admission_decision_ref,
            "backend_result": (dict(self.backend_result)
                if self.backend_result is not None else None),
            "observed_at": self.observed_at}

    @property
    def receipt_digest(self) -> str:
        return digest_payload(self.semantic_payload())

    def to_dict(self) -> dict[str, Any]:
        payload = self.semantic_payload()
        payload["receipt_digest"] = self.receipt_digest
        return payload


@dataclass(frozen=True)
class LocalModelResidencyPreloadReceipt:
    correlation_id: str
    model_identity_digest: str
    status: str
    reason_codes: tuple[str, ...]
    admission_decision_ref: str | None
    keep_alive: str
    workload_evidence: Mapping[str, Any]
    resource_evidence: Mapping[str, Any]
    backend_result: Mapping[str, Any] | None
    observed_at: str

    def semantic_payload(self) -> dict[str, Any]:
        return {"schema_version": "sentientos.local_model_residency_preload:v1",
            "correlation_id": self.correlation_id,
            "model_identity_digest": self.model_identity_digest,
            "status": self.status, "reason_codes": list(self.reason_codes),
            "admission_decision_ref": self.admission_decision_ref,
            "keep_alive": self.keep_alive,
            "workload_evidence": dict(self.workload_evidence),
            "resource_evidence": dict(self.resource_evidence),
            "backend_result": (dict(self.backend_result)
                if self.backend_result is not None else None),
            "observed_at": self.observed_at}

    @property
    def receipt_digest(self) -> str:
        return digest_payload(self.semantic_payload())

    def to_dict(self) -> dict[str, Any]:
        payload = self.semantic_payload()
        payload["receipt_digest"] = self.receipt_digest
        return payload


def validate_receipt(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    schema = payload.get("schema_version")
    legacy_semantic_keys = ["request", "status", "reason_codes", "output_digest",
        "output_size_bytes", "generation_config", "admission_decision_ref", "purpose",
        "output_truncated", "fallback_occurred", "effects"]
    if "schema_version" not in payload:
        # Historical v1 receipts intentionally omit schema_version and bind
        # exactly the pre-v2 field set. An explicit null is not legacy.
        semantic = {key: payload.get(key) for key in legacy_semantic_keys}
    elif schema in {INVOCATION_RECEIPT_SCHEMA, INVOCATION_RECEIPT_SCHEMA_V3,
                    INVOCATION_RECEIPT_SCHEMA_V4}:
        semantic = {key: payload.get(key) for key in (
            "schema_version", *legacy_semantic_keys, "observed_at")}
        if schema in {INVOCATION_RECEIPT_SCHEMA_V3, INVOCATION_RECEIPT_SCHEMA_V4}:
            semantic["backend_completion"] = payload.get("backend_completion")
            completion = payload.get("backend_completion")
            if (completion is None and schema == INVOCATION_RECEIPT_SCHEMA_V4):
                pass
            elif not validate_backend_completion_observation(completion):
                reasons.append("backend_completion_observation_invalid")
            elif (isinstance(completion, Mapping)
                    and completion.get("schema_version") ==
                        LLAMA_COMPLETION_OBSERVATION_SCHEMA_V3):
                thread_control = completion.get("backend_thread_limit_control")
                request_value = payload.get("request")
                request_linkage = (request_value.get("linkage")
                    if isinstance(request_value, Mapping) else None)
                expected_thread_limit = (request_linkage.get("max_backend_threads")
                    if isinstance(request_linkage, Mapping) else None)
                generation_config = payload.get("generation_config")
                actual_parameters = (generation_config.get("actual_generation_parameters")
                    if isinstance(generation_config, Mapping) else None)
                actual_thread_limit = (actual_parameters.get("max_backend_threads")
                    if isinstance(actual_parameters, Mapping) else None)
                if (not isinstance(thread_control, Mapping)
                        or thread_control.get("requested_ceiling") != expected_thread_limit
                        or actual_thread_limit != expected_thread_limit):
                    reasons.append("backend_thread_limit_control_unbound")
            if (isinstance(completion, Mapping)
                    and completion.get("finish_reason") == "length"
                    and payload.get("output_truncated") is not True):
                reasons.append("backend_completion_truncation_mismatch")
        if schema == INVOCATION_RECEIPT_SCHEMA_V4:
            semantic["cancellation_admission_decision_ref"] = payload.get(
                "cancellation_admission_decision_ref")
            if (not isinstance(semantic["cancellation_admission_decision_ref"], str)
                    or not semantic["cancellation_admission_decision_ref"]):
                reasons.append("cancellation_admission_decision_ref_invalid")
        observed_at = payload.get("observed_at")
        try:
            timestamp = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            timestamp = None
        if (not isinstance(observed_at, str) or timestamp is None
                or timestamp.tzinfo is None or timestamp.utcoffset() is None):
            reasons.append("receipt_event_time_invalid")
    else:
        semantic = {key: payload.get(key) for key in legacy_semantic_keys}
        reasons.append("receipt_schema_version_invalid")
    expected_digest = digest_payload(semantic)
    if payload.get("receipt_digest") != expected_digest:
        reasons.append("receipt_digest_mismatch")
    if payload.get("receipt_id") != "lmrec-" + expected_digest[:24]:
        reasons.append("receipt_id_mismatch")
    linkage = {"receipt_digest": payload.get("receipt_digest"),
        "allocation_digest": payload.get("resource_allocation_digest"),
        "attempt_id": payload.get("resource_attempt_id"),
        "consumption_receipt_digests": tuple(payload.get("resource_consumption_receipt_digests") or ())}
    allocation = payload.get("resource_allocation_digest")
    attempt = payload.get("resource_attempt_id")
    consumption = payload.get("resource_consumption_receipt_digests")
    # Empty linkage remains compatible with historical unlinked receipts.
    has_linkage = allocation is not None or attempt is not None or bool(consumption)
    if payload.get("resource_linkage_digest") is not None and not has_linkage:
        reasons.append("resource_linkage_fields_missing")
    if has_linkage:
        if (not isinstance(allocation, str) or not allocation or not isinstance(attempt, str)
                or not attempt or not isinstance(consumption, (list, tuple)) or not consumption
                or any(not isinstance(item, str) or not item for item in consumption)
                or payload.get("resource_linkage_digest") is None):
            reasons.append("resource_linkage_incomplete")
        expected_linkage = digest_payload(linkage)
        if payload.get("resource_linkage_digest") != expected_linkage:
            reasons.append("resource_linkage_digest_mismatch")
    effects = payload.get("effects")
    if not isinstance(effects, Mapping) or any(bool(effects.get(key)) for key in FORBIDDEN_EFFECTS):
        reasons.append("forbidden_effect_recorded")
    return not reasons, reasons


def _status_for_denial(outcome: str) -> str:
    if outcome == "defer": return "deferred"
    if outcome == "deny": return "denied"
    return "blocked_invalid"

class LocalModelPostEffectCustodyError(RuntimeError):
    """Custody failed after backend entry; the invocation must not be replayed implicitly."""

    def __init__(self, *, receipt_id: str, receipt_digest: str,
                 invocation_status: str, failure_phase: str,
                 receipt_persistence_confirmed: bool,
                 resource_linkage_persistence_confirmed: bool | None) -> None:
        self.receipt_id = receipt_id
        self.receipt_digest = receipt_digest
        self.invocation_status = invocation_status
        self.failure_phase = failure_phase
        self.receipt_persistence_confirmed = bool(receipt_persistence_confirmed)
        self.resource_linkage_persistence_confirmed = resource_linkage_persistence_confirmed
        super().__init__("post_effect_custody_unconfirmed")


class LocalModelInvocationDeferred(RuntimeError):
    """A current runtime resource policy deferred inference before backend entry."""

    def __init__(self, reason_code: str) -> None:
        if not isinstance(reason_code, str) or not reason_code:
            raise ValueError("invocation_defer_reason_required")
        self.reason_code = reason_code
        super().__init__("local_model_invocation_deferred")


class GovernedLocalModelInvoker:
    CANCELLATION_QUIESCENCE_TIMEOUT_SECONDS = 0.5

    def __init__(self, *, model: Any, authority_map: LocalModelAuthorityMap, kernel: ControlPlaneKernel | None = None, runtime_root: Path | None = None) -> None:
        self.model = model; self.authority_map = authority_map; self.kernel = kernel or get_control_plane_kernel(); self.runtime_root = Path(runtime_root or Path(os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT", "/tmp/sentientos_runtime_state")) / "governed_local_model_invocation"); self.runtime_root.mkdir(parents=True, exist_ok=True); self.invocation_counts: dict[str, int] = {}; self._evidence_sink: Callable[[Mapping[str, Any]], None] | None = None; self._active_invocation_lock = threading.Lock(); self._active_state_lock = threading.Lock(); self._active_release_event: threading.Event | None = None; self._active_cancel_reason: str | None = None; self._active_cancel_admission_ref: str | None = None; self._active_residency_preload_event: threading.Event | None = None; self._backend_quiescence_callbacks: list[Callable[[], None]] = []

    def register_evidence_sink(self, sink: Callable[[Mapping[str, Any]], None] | None) -> None:
        """Install an explicit observational receipt sink owned by the runtime."""
        self._evidence_sink = sink

    def backend_work_pending(self) -> bool:
        """Return whether this invocation owner still has an active backend worker."""
        with self._active_state_lock:
            return self._active_release_event is not None

    def on_backend_quiescence(self, callback: Callable[[], None]) -> None:
        """Run callback once the current backend worker is known to have stopped."""
        if not callable(callback):
            raise TypeError("backend_quiescence_callback_required")
        with self._active_state_lock:
            run_now = self._active_release_event is None
            if not run_now:
                self._backend_quiescence_callbacks.append(callback)
        if run_now:
            callback()

    def _mark_backend_quiescent(self, release_event: threading.Event) -> None:
        callbacks: list[Callable[[], None]] = []
        with self._active_state_lock:
            if self._active_release_event is not release_event:
                return
            self._active_release_event = None
            callbacks = self._backend_quiescence_callbacks
            self._backend_quiescence_callbacks = []
        for callback in callbacks:
            try:
                callback()
            except Exception:
                # Lifecycle bookkeeping must not change the backend result.
                pass

    def cancel_pending_generation(self, *, reason: str = "client_disconnect",
                                  cancellation_admission_decision: ControlActionDecision | None = None) -> bool:
        """Request cancellation and confirm the exact backend worker has stopped."""
        if reason not in {"client_disconnect", "workload_transition"}:
            raise ValueError("invocation_cancellation_reason_invalid")
        admission_ref: str | None = None
        if reason == "workload_transition" and cancellation_admission_decision is None:
            raise ValueError("invocation_cancellation_admission_decision_required")
        if cancellation_admission_decision is not None:
            if (type(cancellation_admission_decision) is not ControlActionDecision
                    or not self.kernel.owns_recorded_admitted_decision(
                        cancellation_admission_decision)):
                raise ValueError("invocation_cancellation_admission_decision_unverified")
            decision = cancellation_admission_decision
            inference_preemption = (
                decision.outcome == AdmissionOutcome.ALLOW
                and decision.authority_class == AuthorityClass.LOCAL_MODEL_INFERENCE
                and decision.action_kind == "local_model_inference_preemption"
                and decision.target_subsystem == "governed_local_model_invocation"
                and decision.actor in {
                    "production_chat_host_resource_governor",
                    "production_chat_game_workload_governor"})
            resource_release = (
                decision.outcome == AdmissionOutcome.ALLOW
                and decision.authority_class == AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE
                and decision.action_kind == "local_model_resource_release"
                and decision.target_subsystem == "production_chat"
                and decision.actor in {
                    "production_chat_host_resource_governor",
                    "production_chat_workload_resource_governor",
                    "production_chat_game_resource_governor"})
            if not (inference_preemption or resource_release):
                raise ValueError("invocation_cancellation_admission_scope_invalid")
            admission_ref = decision.admission_decision_ref
        with self._active_state_lock:
            event = self._active_release_event
            if event is None:
                return False
            self._active_cancel_reason = reason
            self._active_cancel_admission_ref = admission_ref
            event.set()
        cancel = getattr(self.model, "cancel_pending_generation", None)
        if not callable(cancel):
            return False
        try:
            requested = cancel() is True
        except Exception:
            return False
        if not requested or not self._active_invocation_lock.acquire(
                timeout=self.CANCELLATION_QUIESCENCE_TIMEOUT_SECONDS):
            return False
        self._active_invocation_lock.release()
        return True

    def release_model_residency(self, *, reason_code: str = "gaming_mode_entered",
                                 correlation_id: str | None = None,
                                 cancel_active: bool = True,
                                 resource_observation: Mapping[str, Any] | None = None
                                 ) -> LocalModelResidencyReleaseReceipt:
        """Admit and audit a local model release before asking Ollama to unload."""
        identity = getattr(self.model, "active_identity", None)
        identity_digest = digest_payload(identity.to_dict()) if identity is not None else "0" * 64
        correlation = correlation_id or f"gaming-release:{uuid.uuid4().hex}"
        metadata: dict[str, Any] = {"correlation_id": correlation,
            "purpose": "local_model_resource_release",
            "model_identity_digest": identity_digest,
            "reason_code": reason_code}
        if resource_observation is not None:
            metadata["resource_observation"] = dict(resource_observation)
        request = ControlActionRequest(
            action_kind="local_model_resource_release",
            authority_class=AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE,
            actor="local_development_workload_controller",
            target_subsystem="local_model_residency",
            requested_phase=LifecyclePhase.RUNTIME,
            metadata=metadata)
        decision = self.kernel.admit(request)
        status = "denied"
        reasons: list[str] = list(decision.reason_codes)
        backend_result: Mapping[str, Any] | None = None
        lock_acquired = False
        if decision.allowed:
            if identity is None or getattr(identity, "engine", None) != "ollama":
                status = "not_applicable"
                reasons = ["ollama_residency_release_not_applicable"]
            elif (self.authority_map.record_for_active_identity(
                    identity, "local_user_chat") is None
                    and self.authority_map.record_for_active_identity(
                        identity, ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE) is None
                    and not any(self.authority_map.record_for_active_identity(identity, purpose)
                        is not None for purpose in
                            ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES)):
                status = "denied"
                reasons = ["active_model_release_authority_missing"]
            else:
                try:
                    resident = self.model.is_resident()
                except Exception as exc:
                    resident = None
                    status = "release_failed"
                    reasons = [f"residency_observation_failed:{exc.__class__.__name__}"]
                if resident is False:
                    status = "already_unloaded"
                    reasons = ["local_model_already_unloaded"]
                elif resident is True:
                    lock_acquired = self._active_invocation_lock.acquire(blocking=False)
                    if not lock_acquired and cancel_active:
                        with self._active_state_lock:
                            active_release_event = self._active_release_event
                            if active_release_event is not None:
                                self._active_cancel_reason = "workload_transition"
                                self._active_cancel_admission_ref = decision.admission_decision_ref
                                active_release_event.set()
                        cancel = getattr(self.model, "cancel_pending_generation", None)
                        if callable(cancel):
                            try:
                                cancel()
                            except Exception:
                                pass
                        lock_acquired = self._active_invocation_lock.acquire(timeout=1.0)
                    if not lock_acquired:
                        status = "deferred"
                        reasons = [
                            "active_inference_did_not_quiesce" if cancel_active
                            else "active_inference_in_progress"
                        ]
                    else:
                        try:
                            backend_result = self.model.release_residency()
                            still_resident = self.model.is_resident()
                            # Ollama acknowledges keep_alive=0 before its process
                            # list consistently reflects the unload.  Confirm for
                            # a short bounded window so the receipt records the
                            # resulting state rather than a transient stale read.
                            if (still_resident
                                    and getattr(identity, "engine", None) == "ollama"):
                                deadline = time.monotonic() + 10.0
                                while still_resident and time.monotonic() < deadline:
                                    time.sleep(0.25)
                                    still_resident = self.model.is_resident()
                            if still_resident:
                                status = "release_unconfirmed"
                                reasons = ["model_remained_resident_after_release"]
                            else:
                                status = "released"
                                reasons = ["local_model_residency_released"]
                        except Exception as exc:
                            status = "release_failed"
                            reasons = [f"residency_release_failed:{exc.__class__.__name__}"]
                        finally:
                            self._active_invocation_lock.release()
        receipt = LocalModelResidencyReleaseReceipt(
            correlation_id=correlation, model_identity_digest=identity_digest,
            reason_code=reason_code, status=status, reason_codes=tuple(reasons),
            admission_decision_ref=decision.admission_decision_ref,
            backend_result=backend_result, observed_at=datetime.now(timezone.utc).isoformat())
        receipt_path = self.runtime_root / "resource_release_receipts" / (
            uuid.uuid5(uuid.NAMESPACE_URL, correlation).hex + ".json")
        receipt_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(receipt_path.parent, 0o700)
        atomic_write_json(receipt_path, receipt.to_dict())
        return receipt

    def preload_model_residency(self, *, keep_alive: str,
            workload_state: Mapping[str, Any],
            resource_state: Mapping[str, Any],
            correlation_id: str | None = None
            ) -> LocalModelResidencyPreloadReceipt:
        """Preload the exact chat model only under fresh gaming/headroom evidence.

        The operation is a no-prompt Ollama model load. It receives local-model
        inference admission and shares the invocation lock with chat generation.
        """
        identity = getattr(self.model, "active_identity", None)
        identity_digest = digest_payload(identity.to_dict()) if identity is not None else "0" * 64
        correlation = correlation_id or f"gaming-preload:{uuid.uuid4().hex}"
        evidence = workload_state.get("workload_evidence")
        foreground = (workload_state.get("mode") == "automatic"
            and workload_state.get("effective_mode") == "gaming"
            and isinstance(evidence, Mapping)
            and evidence.get("status") == "available"
            and evidence.get("game_foreground") is True)
        utilization = resource_state.get("vram_utilization_percent")
        threshold = resource_state.get("preload_threshold_percent")
        utilization_value: float | None = None
        threshold_value: float | None = None
        if isinstance(utilization, (int, float)) and not isinstance(utilization, bool):
            utilization_value = float(utilization)
        if isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
            threshold_value = float(threshold)
        observed_at = resource_state.get("observed_at")
        try:
            observed_time = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - observed_time.astimezone(timezone.utc)).total_seconds()
        except (TypeError, ValueError):
            age_seconds = None
        resource_ready = (
            resource_state.get("admission_status") == "available"
            and resource_state.get("preload_admission_status") == "available"
            and utilization_value is not None
            and threshold_value is not None
            and utilization_value < threshold_value
            and age_seconds is not None and 0.0 <= age_seconds <= 45.0)
        reasons: list[str] = []
        if not foreground:
            reasons.append("gaming_foreground_evidence_required")
        if not resource_ready:
            reasons.append("fresh_preload_vram_headroom_required")
        if keep_alive not in {"5s", "5m", "15m", "-1"}:
            reasons.append("preload_keep_alive_invalid")
        if identity is None or getattr(identity, "engine", None) != "ollama":
            reasons.append("ollama_residency_preload_not_applicable")
        elif self.authority_map.record_for_active_identity(identity, "local_user_chat") is None:
            reasons.append("active_model_chat_authority_missing")
        decision_ref: str | None = None
        backend_result: Mapping[str, Any] | None = None
        status = "deferred" if reasons else "denied"
        if not reasons:
            assert utilization_value is not None and threshold_value is not None
            request = ControlActionRequest(
                action_kind="local_model_residency_preload",
                authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
                actor="local_development_workload_controller",
                target_subsystem="local_model_residency",
                requested_phase=LifecyclePhase.RUNTIME,
                metadata={"correlation_id": correlation,
                    "purpose": "local_model_preload",
                    "model_identity_digest": identity_digest,
                    "keep_alive": keep_alive,
                    "workload_mode": "gaming",
                    "vram_utilization_percent": utilization_value,
                    "preload_threshold_percent": threshold_value})
            decision = self.kernel.admit(request)
            decision_ref = decision.admission_decision_ref
            if not decision.allowed:
                status = "deferred"
                reasons = ["local_model_preload_governance_deferred",
                    *list(decision.reason_codes)]
            else:
                preload_event = threading.Event()
                with self._active_state_lock:
                    if self._active_residency_preload_event is not None:
                        status = "deferred"
                        reasons = ["model_residency_preload_already_active"]
                    else:
                        self._active_residency_preload_event = preload_event
                acquired = (status != "deferred"
                    and self._active_invocation_lock.acquire(blocking=False))
                if not acquired:
                    with self._active_state_lock:
                        if self._active_residency_preload_event is preload_event:
                            self._active_residency_preload_event = None
                    if status != "deferred":
                        status = "deferred"
                        reasons = ["active_inference_or_model_transition"]
                else:
                    try:
                        resident = self.model.is_resident()
                        if resident:
                            status = "already_resident"
                            reasons = ["local_model_already_resident"]
                        else:
                            backend_result = self.model.preload_residency(keep_alive=keep_alive)
                            if self.model.is_resident():
                                status = "preloaded"
                                reasons = ["local_model_residency_preloaded_without_generation"]
                            else:
                                status = "preload_unconfirmed"
                                reasons = ["model_not_resident_after_preload"]
                    except Exception as exc:
                        status = "preload_failed"
                        reasons = [f"model_residency_preload_failed:{type(exc).__name__}"]
                    finally:
                        with self._active_state_lock:
                            if self._active_residency_preload_event is preload_event:
                                self._active_residency_preload_event = None
                        self._active_invocation_lock.release()
        receipt = LocalModelResidencyPreloadReceipt(
            correlation_id=correlation, model_identity_digest=identity_digest,
            status=status, reason_codes=tuple(reasons),
            admission_decision_ref=decision_ref, keep_alive=keep_alive,
            workload_evidence=(dict(evidence) if isinstance(evidence, Mapping) else {}),
            resource_evidence=dict(resource_state), backend_result=backend_result,
            observed_at=datetime.now(timezone.utc).isoformat())
        receipt_path = self.runtime_root / "resource_preload_receipts" / (
            uuid.uuid5(uuid.NAMESPACE_URL, correlation).hex + ".json")
        receipt_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(receipt_path.parent, 0o700)
        atomic_write_json(receipt_path, receipt.to_dict())
        return receipt

    def build_request(self, *, purpose: str, prompt: str, caller: str, correlation_id: str, lifecycle_phase: str = "runtime", expected_output_format: str = "text", budget: LocalModelInvocationBudget | None = None, upstream_evidence: Mapping[str, Any] | None = None, linkage: Mapping[str, Any] | None = None, structured_output_schema: Mapping[str, Any] | None = None) -> LocalModelInvocationRequest:
        identity = getattr(self.model, "active_identity", None)
        record = self.authority_map.record_for_active_identity(identity, purpose) if identity is not None else self.authority_map.eligible_record(purpose)
        production_identity = identity is not None and getattr(identity, "posture", None) == "production"
        if record is None and self.authority_map.records and not production_identity:
            record = self.authority_map.records[0]
        if record is None: raise ValueError("exact_production_authority_record_required" if production_identity else "authority_map_has_no_records")
        if structured_output_schema is not None:
            allowed_structured_purposes = {
                "discernment_judgment", "resident_developmental_interpretation",
                "resident_developmental_retrieval_cognition",
                INTERVENTION_PURPOSE,
                ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
            }
            if purpose not in allowed_structured_purposes or expected_output_format != "json":
                raise ValueError("structured output is restricted to governed JSON purposes")
            if (purpose == "resident_developmental_retrieval_cognition"
                    and dict(structured_output_schema) not in [
                        RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
                        RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA,
                        RESIDENT_COMPANION_INTERACTION_OUTPUT_SCHEMA]):
                raise ValueError("structured_output_schema_not_canonical")
            expected_intervention_schema = companion_history_output_schema(
                (linkage or {}).get("condition_id"))
            is_objective_task = "objective_task_plan_digest" in (upstream_evidence or {})
            allowed_intervention_schemas = [expected_intervention_schema]
            if is_objective_task:
                allowed_intervention_schemas.append(RESIDENT_OBJECTIVE_TASK_ANSWER_OUTPUT_SCHEMA)
            if (purpose == INTERVENTION_PURPOSE
                    and dict(structured_output_schema) not in allowed_intervention_schemas):
                raise ValueError("structured_output_schema_not_canonical")
        return LocalModelInvocationRequest(purpose=purpose, prompt=prompt, model_id=record.model_id, authority_map_digest=self.authority_map.map_digest, model_artifact_digest=record.model_content_sha256, caller=caller, lifecycle_phase=lifecycle_phase, correlation_id=correlation_id, expected_output_format=expected_output_format, budget=budget or LocalModelInvocationBudget(), upstream_evidence=upstream_evidence or {}, linkage=linkage or {}, active_model_identity=identity.to_dict() if identity is not None else {}, structured_output_schema=deepcopy(dict(structured_output_schema)) if structured_output_schema is not None else None)

    def invoke(self, request: LocalModelInvocationRequest, *, persist: bool = True, include_output_in_receipt: bool = False,
               pre_effect_guard: Callable[[], None] | None = None,
               post_effect_guard: Callable[[], None] | None = None,
               resource_context: GovernedLocalModelResourceInvocationContext | None = None,
               on_content_chunk: Callable[[str], None] | None = None) -> LocalModelInvocationReceipt:
        started = time.monotonic(); status = "blocked_invalid"; reasons: list[str] = [] ; output: str | None = None; admitted_ref = None; fallback = False; truncated = False; backend_completion: Mapping[str, Any] | None = None
        decision_payload: dict[str, Any] = {}; attempt_id: str | None = None; backend_entered = False
        invocation_lock_acquired = False
        receipt_persistence_confirmed = False
        resource_linkage_persistence_confirmed: bool | None = (
            False if resource_context is not None else None)
        generated_output: str | None = None
        cancellation_admission_ref: str | None = None
        resource_allocation_binding: dict[str, Any] | None = None
        inference_attempted = threading.Event()
        active_release_event: threading.Event | None = None
        record = self._record_for(request.model_id)
        ok, map_reasons = validate_authority_map(self.authority_map.to_dict())
        if not ok: reasons += ["authority_map_invalid", *map_reasons]
        if request.purpose not in SUPPORTED_PURPOSES: reasons.append("purpose_unsupported")
        if record is None: reasons.append("model_record_missing")
        elif record.runtime_eligibility_status != "eligible" or (request.purpose not in record.allowed_invocation_purposes and request.purpose != "local_model_commissioning_smoke"):
            if record.engine in {"null", "echo"} and request.purpose == "local_user_chat": reasons.append("simulation_backend")
            else: reasons.append("model_not_eligible_for_purpose")
        if len(request.prompt) > request.budget.max_input_chars: reasons.append("input_oversized")
        if request.expected_output_format not in {"text", "json"}: reasons.append("expected_output_format_invalid")
        thread_limit = request.linkage.get("max_backend_threads")
        keep_alive_override = request.linkage.get("ollama_keep_alive")
        if on_content_chunk is not None and not callable(on_content_chunk):
            reasons.append("stream_content_callback_invalid")
        elif on_content_chunk is not None and record is not None and record.engine != "ollama":
            reasons.append("streaming_backend_unsupported")
        if "ollama_keep_alive" in request.linkage and (
                request.purpose != "local_user_chat"
                or type(keep_alive_override) is not str
                or keep_alive_override not in {"0", "5s", "5m", "15m", "-1"}
                or record is None or record.engine != "ollama"):
            reasons.append("ollama_keep_alive_override_invalid")
        if "max_backend_threads" in request.linkage and (
                request.purpose != "local_user_chat"
                or type(thread_limit) is not int or not 1 <= thread_limit <= 256):
            reasons.append("backend_thread_ceiling_invalid")
        elif ("max_backend_threads" in request.linkage
                and getattr(self.model, "supports_per_invocation_thread_limit", False) is not True):
            reasons.append("backend_thread_limit_unavailable")
        if request.structured_output_schema is not None:
            schema = request.structured_output_schema
            if request.expected_output_format != "json": reasons.append("structured_output_schema_invalid")
            elif request.purpose == "discernment_judgment":
                if not isinstance(schema.get("oneOf"), list): reasons.append("structured_output_schema_invalid")
                from .discernment_participant import judgment_output_schema
                canonical_schema = judgment_output_schema(proposition=str(request.linkage.get("proposition") or ""), allowed_observation_namespace=str(request.linkage.get("allowed_observation_namespace") or ""))
                if dict(schema) != canonical_schema: reasons.append("structured_output_schema_not_canonical")
            elif request.purpose == "resident_developmental_retrieval_cognition":
                if schema not in [RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
                        RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA,
                        RESIDENT_COMPANION_INTERACTION_OUTPUT_SCHEMA]:
                    reasons.append("structured_output_schema_not_canonical")
            elif request.purpose == ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE:
                if schema != RESIDENT_EPISTEMIC_REVISION_OUTPUT_SCHEMA:
                    reasons.append("structured_output_schema_not_canonical")
            elif request.purpose == INTERVENTION_PURPOSE:
                expected_intervention_schema = companion_history_output_schema(
                    request.linkage.get("condition_id"))
                is_objective_task = "objective_task_plan_digest" in request.upstream_evidence
                allowed_intervention_schemas = [expected_intervention_schema]
                if is_objective_task:
                    allowed_intervention_schemas.append(
                        RESIDENT_OBJECTIVE_TASK_ANSWER_OUTPUT_SCHEMA)
                if schema not in allowed_intervention_schemas:
                    reasons.append("structured_output_schema_not_canonical")
            elif request.purpose != "resident_developmental_interpretation": reasons.append("structured_output_schema_invalid")
        if request.purpose == "genesis_proposal_advice":
            ev = dict(request.upstream_evidence.get("genesis_review") or {}) if isinstance(request.upstream_evidence, Mapping) else {}
            link = dict(request.linkage or {})
            if not ev or ev.get("status") not in {"approved", "allow", "reviewed"}: reasons.append("genesis_review_evidence_missing_or_invalid")
            for key in ("need_identity", "signal_batch_digest", "authority_map_digest", "invocation_purpose", "proposal_only"):
                if key not in link: reasons.append(f"genesis_linkage_missing_{key}")
        if self.invocation_counts.get(request.correlation_id, 0) >= request.budget.max_calls_per_correlation: reasons.append("duplicate_correlation")
        if request.authority_map_digest != self.authority_map.map_digest: reasons.append("model_authority_stale")
        if record and request.model_artifact_digest != record.model_content_sha256: reasons.append("model_digest_mismatch")
        identity = getattr(self.model, "active_identity", None)
        production_identity = identity is not None and getattr(identity, "posture", None) == "production"
        rootless_experimental_identity = (identity is not None
            and getattr(identity, "posture", None) == "rootless_experimental")
        development_identity = (identity is not None
            and getattr(identity, "posture", None) == "development_only")
        if (production_identity or rootless_experimental_identity or development_identity
                or request.purpose in {"discernment_judgment", "local_model_commissioning_smoke",
                    "maintenance_implementation", INTERVENTION_PURPOSE, MODEL_REPLACEMENT_PURPOSE}):
            if identity is None: reasons.append("active_model_identity_unavailable")
            elif identity.fallback or (production_identity and identity.posture != "production"):
                reasons.append("active_model_not_production")
            elif rootless_experimental_identity and request.purpose not in {
                    ROOTLESS_EXPERIMENTAL_PURPOSE,
                    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE}:
                reasons.append("rootless_experimental_purpose_mismatch")
            elif self.authority_map.record_for_active_identity(identity, request.purpose) != record: reasons.append("active_model_authority_mismatch")
            if identity is not None and request.active_model_identity != identity.to_dict(): reasons.append("active_model_request_identity_mismatch")

        # Structural custody and narrowing only.  This is deliberately before
        # effect admission and never creates or debits an allocation.
        if resource_context is not None and not any(r for r in reasons if r not in {"simulation_backend"}):
            try:
                if type(resource_context) is not GovernedLocalModelResourceInvocationContext:
                    raise GovernedLocalModelResourceError("trusted_resource_context_required")
                allocation = GovernedLocalModelResourceAllocation.from_mapping(resource_context.allocation.to_dict())
                if allocation != resource_context.allocation or resource_context.allocator.ledger.allocation(allocation.allocation_id) != allocation:
                    raise GovernedLocalModelResourceError("allocation_substitution")
                if resource_context.allocator.policy != resource_context.policy or allocation.policy_digest != resource_context.policy.policy_digest or allocation.epoch != resource_context.policy.epoch:
                    raise GovernedLocalModelResourceError("allocation_policy_mismatch")
                resource_allocation_binding = {
                    "schema_version": (
                        "sentientos.governed_local_model_resource_allocation_admission_context:v1"),
                    "allocation_id": allocation.allocation_id,
                    "allocation_digest": allocation.allocation_digest,
                    "allocator_id": allocation.allocator_id,
                    "resource_kind": allocation.resource_kind,
                    "policy_digest": allocation.policy_digest,
                    "policy_epoch": allocation.epoch,
                    "principal_binding_digest": allocation.principal_binding_digest,
                }
                if (allocation.resource_specific_bounds.max_cpu_seconds_per_allocation is not None
                        and (record is None or record.engine != "llama_cpp"
                            or type(thread_limit) is not int
                            or getattr(self.model, "supports_per_invocation_thread_limit", False)
                                is not True)):
                    raise GovernedLocalModelResourceError(
                        "cpu_budget_requires_verified_backend_thread_limit")
                for dimension in LocalModelInvocationBudget.__dataclass_fields__:
                    if getattr(request.budget, dimension) > getattr(allocation.resource_specific_bounds, dimension):
                        raise GovernedLocalModelResourceError(f"request_budget_exceeds_allocation:{dimension}")
            except GovernedLocalModelResourceError as exc:
                reasons.append("resource_preflight:" + str(exc).split(":", 1)[0])

        if not any(r for r in reasons if r not in {"simulation_backend"}):
            phase = LifecyclePhase(request.lifecycle_phase) if request.lifecycle_phase in LifecyclePhase._value2member_map_ else self.kernel.phase
            execution_profile = _verified_model_execution_profile(self.model, record)
            admission_metadata: dict[str, Any] = {
                "correlation_id": request.correlation_id,
                "purpose": request.purpose,
                "request_digest": request.request_digest,
            }
            if resource_allocation_binding is not None:
                # Record the exact preflighted entitlement as admission context.
                # The allocator's final_gate below remains authoritative for
                # currentness and durable debit; this binding grants no effect.
                admission_metadata["resource_allocation_binding"] = dict(
                    resource_allocation_binding)
            host_observation = request.linkage.get("host_resource_observation")
            if isinstance(host_observation, Mapping):
                observation_correlation_id = host_observation.get(
                    "observation_correlation_id")
                if isinstance(observation_correlation_id, str):
                    admission_metadata["host_resource_observation_id"] = (
                        observation_correlation_id)
            if execution_profile is not None:
                admission_metadata["model_execution_profile"] = execution_profile
            workload_mode = request.linkage.get("workload_mode")
            workload_evidence = request.linkage.get("workload_evidence")
            if (workload_mode in {"normal", "gaming"}
                    and isinstance(workload_evidence, Mapping)):
                admission_metadata["workload_mode"] = workload_mode
                admission_metadata["workload_evidence"] = dict(workload_evidence)
            cp_req = ControlActionRequest(action_kind="local_model_inference", authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE, actor=request.caller, target_subsystem="governed_local_model_invocation", requested_phase=phase, metadata=admission_metadata)
            decision = self.kernel.admit(cp_req); decision_payload = decision.to_dict(); admitted_ref = decision.admission_decision_ref
            if not decision.allowed: reasons += list(decision.reason_codes); status = _status_for_denial(decision.outcome.value)
            else:
                invocation_lock_acquired = self._active_invocation_lock.acquire(
                    blocking=False)
                if not invocation_lock_acquired:
                    with self._active_state_lock:
                        preload_in_progress = self._active_residency_preload_event is not None
                    if preload_in_progress:
                        invocation_lock_acquired = self._active_invocation_lock.acquire(
                            timeout=min(10.0, request.budget.timeout_seconds))
                if not invocation_lock_acquired:
                    status = "backend_failure"
                    reasons.append("backend_failure:RuntimeError")
                if resource_context is not None:
                    if invocation_lock_acquired:
                        try:
                            attempt_id = resource_context.allocator.final_gate(
                                allocation=resource_context.allocation,
                                principal=resource_context.principal,
                                authenticated=resource_context.authenticated,
                                current=resource_context.current,
                                policy=resource_context.policy,
                                current_time=resource_context.clock(),
                                durable_attempt_nonce=resource_context.durable_attempt_nonce,
                                requested_timeout_seconds=request.budget.timeout_seconds,
                                max_backend_threads=(thread_limit
                                    if type(thread_limit) is int else None))
                        except GovernedLocalModelResourceError as exc:
                            status = "resource_denied"; reasons.append("resource_gate:" + str(exc).split(":", 1)[0])
                        except Exception:
                            self._active_invocation_lock.release()
                            invocation_lock_acquired = False
                            raise
                if invocation_lock_acquired and (resource_context is None or attempt_id is not None):
                    try:
                        self.invocation_counts[request.correlation_id] = self.invocation_counts.get(request.correlation_id, 0) + 1
                        generation: dict[str, Any] = {"max_new_tokens": min(request.budget.max_new_tokens, int(record.generation_ceilings.get("max_new_tokens", request.budget.max_new_tokens))) if record else request.budget.max_new_tokens, "temperature": 0 if request.purpose in {"genesis_proposal_advice", "discernment_judgment", "local_model_commissioning_smoke", "resident_developmental_retrieval_cognition", INTERVENTION_PURPOSE, MODEL_REPLACEMENT_PURPOSE, ROOTLESS_EXPERIMENTAL_PURPOSE, ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE} else None, "structured_output_schema": dict(request.structured_output_schema) if request.structured_output_schema is not None else None, "use_model_chat_template": request.purpose == ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE}
                        if thread_limit is not None:
                            generation["max_backend_threads"] = thread_limit
                        if "ollama_keep_alive" in request.linkage:
                            generation["keep_alive"] = keep_alive_override
                        if on_content_chunk is not None:
                            generation["on_content_chunk"] = on_content_chunk
                        gen_kwargs: dict[str, Any] = {k: v for k, v in generation.items() if v is not None}
                        if pre_effect_guard is not None:
                            try: pre_effect_guard()
                            except Exception:
                                if resource_context is not None and attempt_id is not None:
                                    resource_context.allocator.reconcile_not_begun(resource_context.allocation, attempt_id, observed_at=resource_context.clock())
                                raise
                        latest_identity = getattr(self.model, "active_identity", None)
                        if (identity is not None and
                                (latest_identity is None
                                 or request.active_model_identity != latest_identity.to_dict())):
                            if resource_context is not None and attempt_id is not None:
                                resource_context.allocator.reconcile_not_begun(
                                    resource_context.allocation, attempt_id,
                                    observed_at=resource_context.clock())
                            self._active_invocation_lock.release()
                            invocation_lock_acquired = False
                            raise RuntimeError("active_model_request_identity_mismatch")
                        if resource_context is not None and attempt_id is not None:
                            resource_context.allocator.record_backend_entry(
                                resource_context.allocation, attempt_id,
                                observed_at=resource_context.clock())
                            backend_entered = True
                        active_release_event = threading.Event()
                        with self._active_state_lock:
                            self._active_release_event = active_release_event
                            self._active_cancel_reason = None
                            self._active_cancel_admission_ref = None
                        # Ollama supports an event check around connection setup, closing the
                        # race where disconnect lands just before the HTTP request is installed.
                        if getattr(identity, "engine", None) == "ollama":
                            gen_kwargs["_cancel_event"] = active_release_event
                        lock_release_guard = threading.Lock()
                        lock_released = False
                        def _release_invocation_lock() -> None:
                            nonlocal lock_released
                            with lock_release_guard:
                                if not lock_released:
                                    lock_released = True
                                    self._active_invocation_lock.release()
                        def _call_model() -> tuple[str, Mapping[str, Any] | None]:
                            try:
                                return _call_model_inner()
                            finally:
                                _release_invocation_lock()
                        def _call_model_inner() -> tuple[str, Mapping[str, Any] | None]:
                            inference_attempted.set()
                            metadata_generator = getattr(self.model, "generate_governed_with_metadata", None)
                            if callable(metadata_generator):
                                response = metadata_generator(request.prompt, **gen_kwargs)
                                if (isinstance(response, tuple) and len(response) == 2
                                        and isinstance(response[0], str)
                                        and (response[1] is None or isinstance(response[1], Mapping))):
                                    return response[0], response[1]
                                raise ValueError("backend_completion_response_invalid")
                            governed_generate = getattr(self.model, "generate_governed", None)
                            if governed_generate is not None:
                                return cast(str, governed_generate(request.prompt, **gen_kwargs)), None
                            try: return cast(str, self.model.generate(request.prompt, **gen_kwargs)), None
                            except TypeError:
                                if "max_backend_threads" in gen_kwargs:
                                    raise
                                return cast(str, self.model.generate(request.prompt)), None
                        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                        shutdown_without_wait = False
                        try:
                            future = executor.submit(_call_model)
                        except Exception:
                            _release_invocation_lock()
                            invocation_lock_acquired = False
                            with self._active_state_lock:
                                if self._active_release_event is active_release_event:
                                    self._active_release_event = None
                            raise
                        def _backend_future_done(_future: Any) -> None:
                            _release_invocation_lock()
                            self._mark_backend_quiescent(active_release_event)
                        future.add_done_callback(_backend_future_done)
                        invocation_lock_acquired = False
                        try:
                            output, backend_completion = future.result(timeout=max(float(request.budget.timeout_seconds), 0.001))
                        except concurrent.futures.TimeoutError as exc:
                            with self._active_state_lock:
                                self._active_cancel_reason = "timeout"
                                active_release_event.set()
                            cancel = getattr(self.model, "cancel_pending_generation", None)
                            requested = False
                            cancellation_hook_available = callable(cancel)
                            if callable(cancel):
                                try: requested = cancel() is True
                                except Exception: pass
                            future.cancel()
                            try: future.result(timeout=0.5)
                            except concurrent.futures.CancelledError: pass
                            except concurrent.futures.TimeoutError: pass
                            except Exception: pass
                            if future.done(): reasons.append("timeout_worker_terminated")
                            elif requested: reasons.append("timeout_cancellation_unconfirmed")
                            elif cancellation_hook_available: reasons.append("timeout_worker_cancellation_failed")
                            else: reasons.append("timeout_worker_cancellation_unavailable")
                            executor.shutdown(wait=False, cancel_futures=True)
                            shutdown_without_wait = True
                            raise TimeoutError() from exc
                        finally:
                            if not shutdown_without_wait:
                                executor.shutdown(wait=True, cancel_futures=True)
                                self._mark_backend_quiescent(active_release_event)
                            elif future.done():
                                self._mark_backend_quiescent(active_release_event)
                        if backend_completion is not None:
                            if not validate_backend_completion_observation(backend_completion):
                                raise ValueError("backend_completion_observation_invalid")
                            if backend_completion.get("token_limit_reached") is True:
                                truncated = True
                                reasons.append("backend_token_limit_reached")
                        generated_output = output
                        if post_effect_guard is not None:
                            try: post_effect_guard()
                            except Exception:
                                output = None; status = "serving_lifetime_stale_after_generation"; reasons.append("post_effect_currentness_failed")
                        if output is not None and len(output.encode("utf-8")) > request.budget.max_output_chars:
                            output = output.encode("utf-8")[:request.budget.max_output_chars].decode("utf-8", "ignore"); truncated = True; reasons.append("output_oversized")
                        if output is None: pass
                        elif not output.strip(): reasons.append("empty_output"); status = "degraded_fallback"; fallback = True
                        elif request.purpose == "genesis_proposal_advice" and not self._valid_genesis_advice(output): reasons.append("output_malformed"); status = "output_malformed"
                        elif request.purpose == "discernment_judgment" and not self._valid_discernment_judgment(output, request): reasons.append("output_malformed"); status = "output_malformed"
                        else: status = "admitted_simulation" if record and record.engine in {"null", "echo"} else "admitted_completed"
                    except LocalModelInvocationDeferred as exc:
                        status = "deferred"
                        reasons.extend(["runtime_resource_admission_deferred",
                            exc.reason_code])
                    except TimeoutError: status = "timeout"; reasons.append("timeout")
                    except GovernedLocalModelResourceError as exc: status = "resource_custody_failure"; reasons.append("resource_transition:" + str(exc).split(":", 1)[0])
                    except Exception as exc:
                        if active_release_event is not None and active_release_event.is_set():
                            status = "cancelled"
                            with self._active_state_lock:
                                cancel_reason = self._active_cancel_reason
                                cancellation_admission_ref = self._active_cancel_admission_ref
                            reasons.append({"workload_transition": "cancelled_for_workload_transition",
                                "client_disconnect": "cancelled_by_client_disconnect",
                                "timeout": "cancelled_after_timeout"}.get(cancel_reason or "unknown",
                                    "cancelled_by_runtime"))
                        elif str(exc) == "active_model_request_identity_mismatch":
                            status = "backend_failure"
                            reasons.append("active_model_request_identity_mismatch")
                        else:
                            status = "backend_failure"
                            diagnostic_code = getattr(exc, "diagnostic_code", None)
                            if diagnostic_code in OLLAMA_BACKEND_DIAGNOSTICS:
                                reasons.append(f"backend_failure:{diagnostic_code}")
                            else:
                                reasons.append(f"backend_failure:{exc.__class__.__name__}")
                if invocation_lock_acquired:
                    self._active_invocation_lock.release()
                    invocation_lock_acquired = False
        if status == "blocked_invalid" and not reasons: reasons.append("blocked_invalid")
        effect_occurred = inference_attempted.is_set()
        receipt_output = generated_output if generated_output is not None else output
        actual_generation_parameters = ({key: value for key, value in gen_kwargs.items()
            if key not in {"on_content_chunk", "_cancel_event"}} if "gen_kwargs" in locals() else {})
        receipt_schema = (INVOCATION_RECEIPT_SCHEMA_V4 if cancellation_admission_ref
            else INVOCATION_RECEIPT_SCHEMA_V3 if backend_completion is not None
            else INVOCATION_RECEIPT_SCHEMA)
        receipt = LocalModelInvocationReceipt(request=request.to_receipt_request_dict(), status=status, reason_codes=tuple(reasons or ["completed"]), output_text=output, output_digest=digest_payload({"output": receipt_output}) if receipt_output is not None else None, output_size_bytes=len((receipt_output or "").encode("utf-8")), generation_config={**request.budget.to_dict(), "actual_generation_parameters": actual_generation_parameters}, admission_decision_ref=admitted_ref, purpose=request.purpose, latency_ms=int((time.monotonic()-started)*1000), output_truncated=truncated, fallback_occurred=fallback, effects={"local_model_inference": effect_occurred, **FORBIDDEN_EFFECTS}, observed_at=datetime.now(timezone.utc).isoformat(), schema_version=receipt_schema, backend_completion=backend_completion, cancellation_admission_decision_ref=cancellation_admission_ref)
        if persist:
            try:
                self._persist(request, receipt, decision_payload,
                    include_output=include_output_in_receipt)
                receipt_persistence_confirmed = True
            except Exception as exc:
                if backend_entered:
                    raise LocalModelPostEffectCustodyError(
                        receipt_id=receipt.receipt_id, receipt_digest=receipt.receipt_digest,
                        invocation_status=receipt.status, failure_phase="invocation_receipt_publication",
                        receipt_persistence_confirmed=False,
                        resource_linkage_persistence_confirmed=resource_linkage_persistence_confirmed) from exc
                raise
        if resource_context is not None and attempt_id is not None and backend_entered:
            try:
                backend_resource_observation: Mapping[str, object] | None = None
                if (isinstance(backend_completion, Mapping)
                        and backend_completion.get("schema_version") ==
                            LLAMA_COMPLETION_OBSERVATION_SCHEMA_V3
                        and validate_backend_completion_observation(backend_completion)):
                    backend_metrics = backend_completion.get("invocation_resources")
                    if isinstance(backend_metrics, Mapping):
                        backend_resource_observation = {
                            "schema_version": (
                                "sentientos.governed_local_model_backend_resource_observation:v1"),
                            "backend": "llama_cpp",
                            "observation_source": "exact_runtime_worker_process",
                            "user_cpu_seconds": backend_metrics.get("user_cpu_seconds"),
                            "system_cpu_seconds": backend_metrics.get("system_cpu_seconds"),
                            "wall_seconds": backend_metrics.get("wall_seconds"),
                            "process_peak_rss_bytes": backend_metrics.get(
                                "process_peak_rss_bytes"),
                        }
                measurement = resource_context.allocator.measurement(
                    resource_context.allocation, generation_attempted=True, call_units_consumed=1,
                    generated_output_size_bytes=(len(generated_output.encode("utf-8"))
                        if generated_output is not None else None),
                    returned_output_size_bytes=(len(output.encode("utf-8"))
                        if output is not None else None),
                    output_truncated=truncated, latency_ms=receipt.latency_ms,
                    invocation_outcome=status,
                    backend_resource_observation=backend_resource_observation)
                state = ("measured_timeout" if status == "timeout" else
                    "measured_backend_failure" if status == "backend_failure" else
                    "measured_cancelled" if status == "cancelled" else
                    "measured_completed")
                measured = resource_context.allocator.append_receipt(
                    resource_context.allocation, attempt_id, state=state,
                    observed_at=resource_context.clock(), measurement=measurement)
                reconciled = resource_context.allocator.append_receipt(
                    resource_context.allocation, attempt_id, state="reconciled",
                    observed_at=resource_context.clock(), measurement=measurement,
                    effect_receipt_digest=receipt.receipt_digest)
            except Exception as exc:
                raise LocalModelPostEffectCustodyError(
                    receipt_id=receipt.receipt_id, receipt_digest=receipt.receipt_digest,
                    invocation_status=receipt.status, failure_phase="resource_ledger_reconciliation",
                    receipt_persistence_confirmed=receipt_persistence_confirmed,
                    resource_linkage_persistence_confirmed=False) from exc
            try:
                receipt = replace(receipt,
                    resource_allocation_digest=resource_context.allocation.allocation_digest,
                    resource_attempt_id=attempt_id,
                    resource_consumption_receipt_digests=(measured.receipt_digest,
                        reconciled.receipt_digest))
                receipt = replace(receipt, resource_linkage_digest=digest_payload({
                    "receipt_digest": receipt.receipt_digest,
                    "allocation_digest": receipt.resource_allocation_digest,
                    "attempt_id": receipt.resource_attempt_id,
                    "consumption_receipt_digests": receipt.resource_consumption_receipt_digests}))
            except Exception as exc:
                raise LocalModelPostEffectCustodyError(
                    receipt_id=receipt.receipt_id, receipt_digest=receipt.receipt_digest,
                    invocation_status=receipt.status, failure_phase="resource_linkage_construction",
                    receipt_persistence_confirmed=receipt_persistence_confirmed,
                    resource_linkage_persistence_confirmed=False) from exc
            if persist:
                try:
                    self._persist(request, receipt, decision_payload,
                        include_output=include_output_in_receipt)
                    resource_linkage_persistence_confirmed = True
                except Exception as exc:
                    raise LocalModelPostEffectCustodyError(
                        receipt_id=receipt.receipt_id, receipt_digest=receipt.receipt_digest,
                        invocation_status=receipt.status, failure_phase="resource_linkage_publication",
                        receipt_persistence_confirmed=True,
                        resource_linkage_persistence_confirmed=False) from exc
        if self._evidence_sink is not None:
            try:
                self._evidence_sink(receipt.to_dict(include_output=False))
            except Exception as exc:
                if backend_entered:
                    raise LocalModelPostEffectCustodyError(
                        receipt_id=receipt.receipt_id, receipt_digest=receipt.receipt_digest,
                        invocation_status=receipt.status, failure_phase="observational_evidence_sink",
                        receipt_persistence_confirmed=receipt_persistence_confirmed,
                        resource_linkage_persistence_confirmed=resource_linkage_persistence_confirmed) from exc
                raise
        return receipt

    def _record_for(self, model_id: str) -> LocalModelAuthorityRecord | None:
        return next((r for r in self.authority_map.records if r.model_id == model_id), None)

    def _persist(self, request: LocalModelInvocationRequest, receipt: LocalModelInvocationReceipt, decision: Mapping[str, Any], *, include_output: bool) -> None:
        atomic_write_json(self.runtime_root / "requests" / f"{request.request_id}.json", request.to_receipt_request_dict())
        if decision: atomic_write_json(self.runtime_root / "decisions" / f"{request.request_id}.json", dict(decision))
        atomic_write_json(self.runtime_root / "receipts" / f"{receipt.receipt_id}.json", receipt.to_dict(include_output=include_output))

    @staticmethod
    def _valid_genesis_advice(text: str) -> bool:
        try: data = json.loads(text)
        except json.JSONDecodeError: return False
        if not isinstance(data, Mapping): return False
        required = {"objective_refinement", "proposed_directives", "testing_requirements", "rationale", "capability_interpretation"}
        if not required.issubset(data): return False
        blob = json.dumps(data).lower()
        forbidden = ["import ", "subprocess", "shell", "git ", "openai", "huggingface", "http://", "https://", "adoptionrite", "specbinder", "write_file", "memory"]

        try:
            from .genesis_model_advice import parse_advice_output
            payload, reasons = parse_advice_output(text)
            return payload is not None and not reasons
        except Exception:
            return not any(item in blob for item in forbidden)

    @staticmethod
    def _valid_discernment_judgment(text: str, request: LocalModelInvocationRequest) -> bool:
        try:
            from .discernment_participant import validate_judgment_output
            validate_judgment_output(
                json.loads(text),
                allowed_observation_namespace=str(request.linkage.get("allowed_observation_namespace") or ""),
                expected_proposition=str(request.linkage.get("proposition") or ""),
            )
            return True
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
