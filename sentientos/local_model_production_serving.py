"""Effectful, inference-free serving of the current hardened activation."""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .control_plane_kernel import (AdmissionOutcome, AuthorityClass, ControlActionDecision,
                                   ControlActionRequest,
                                   ControlPlaneKernel, LifecyclePhase)
from .installation_state import (
    InstallationStateError, InstallationStateHandle,
    InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView,
)
from .local_model_production_activation import (
    ProductionActivationError, verify_current_activation,
)
from .local_model_runtime_worker import ExactRuntimeLocalModel
from .local_model_authority import digest_payload
from .local_runtime_provisioning import semantic_digest

PRINCIPAL = "deterministic_activated_model_serving_controller"
CAPABILITY = "local_model_production_serving"
TARGET_SUBSYSTEM = "local_model_chat"
ACTION = "establish_exact_activated_model_serving_session"
RECEIPT_SCHEMA = "sentientos.local_model_serving_session_receipt:v1"
RESOURCE_ADMISSION_EVIDENCE_SCHEMA = (
    "sentientos.local_model_serving_admission_evidence:v1")
SERVING_RESOURCE_ENTITLEMENT_SCHEMA = (
    "sentientos.governed_local_model_serving_entitlement_binding:v2")
LEGACY_SERVING_RESOURCE_ENTITLEMENT_SCHEMA = (
    "sentientos.governed_local_model_serving_entitlement_binding:v1")
WITNESS_SCHEMA = "sentientos.privilege_witness:model_serving:v1"
INVALIDATION_SCHEMA = "sentientos.local_model_serving_session_invalidation:v1"
SERVING_ATTEMPT_SCHEMA = "sentientos.local_model_serving_operation_attempt:v1"
SERVING_ATTEMPT_ROOT = "local-model/serving/attempts"
MAX_SERVING_OPERATION_ATTEMPTS = 256
MAX_SERVING_OPERATION_ATTEMPT_BYTES = 262_144
GAME_RECOVERY_HOLD_SCHEMA = "sentientos.game_resource_recovery_hold:v1"
GAME_RECOVERY_CLEARANCE_SCHEMA = "sentientos.game_resource_recovery_clearance:v1"
GAME_RECOVERY_HOLD_ROOT = "local-model/serving/resource-recovery-holds"
GAME_RECOVERY_CLEARANCE_ROOT = "local-model/serving/resource-recovery-clearances"
MAX_GAME_RECOVERY_HOLDS = 4096
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


def _semantic_digest(value: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ProductionServingError("activation_state_digest_invalid")
    return value


def _valid_resource_serving_decision_record(binding: Mapping[str, Any], *,
        record_key: str, reference_key: str, correlation_key: str) -> bool:
    record = binding.get(record_key)
    fields = {
        "event_type", "timestamp", "final_disposition", "outcome",
        "reason_codes", "delegate_checks_consulted", "lifecycle_phase",
        "current_phase", "requested_phase", "authority_class", "action_kind",
        "actor_source", "actor", "execution_owner", "target_subsystem",
        "delegated_outcomes", "federation_context", "proof_budget_context",
        "protected_mutation_intent", "correlation_id", "admission_decision_ref",
    }
    reasons = record.get("reason_codes") if isinstance(record, Mapping) else None
    checks = (record.get("delegate_checks_consulted")
        if isinstance(record, Mapping) else None)
    correlation = binding.get(correlation_key)
    reference = binding.get(reference_key)
    current_phase = record.get("current_phase") if isinstance(record, Mapping) else None
    return bool(
        isinstance(record, Mapping)
        and set(record) == fields
        and record.get("event_type") == "control_plane_decision"
        and isinstance(record.get("timestamp"), str) and record.get("timestamp")
        and record.get("final_disposition") == "allow"
        and record.get("outcome") == "allow"
        and isinstance(reasons, (list, tuple))
        and all(isinstance(item, str) and item for item in reasons)
        and isinstance(checks, (list, tuple))
        and all(isinstance(item, str) and item for item in checks)
        and isinstance(current_phase, str)
        and current_phase == LifecyclePhase.RUNTIME.value
        and record.get("lifecycle_phase") == current_phase
        and record.get("requested_phase") == LifecyclePhase.RUNTIME.value
        and record.get("authority_class") == AuthorityClass.MODEL_SERVING.value
        and record.get("action_kind") == ACTION
        and record.get("actor_source") == PRINCIPAL
        and record.get("actor") == PRINCIPAL
        and record.get("execution_owner") == PRINCIPAL
        and record.get("target_subsystem") == TARGET_SUBSYSTEM
        and isinstance(record.get("delegated_outcomes"), Mapping)
        and isinstance(correlation, str) and bool(correlation)
        and record.get("correlation_id") == correlation
        and isinstance(reference, str) and bool(reference)
        and record.get("admission_decision_ref") == reference)


def _decision_retains_current_entitlement(record: object,
        binding: Mapping[str, Any], *, expected_observation_id: str | None = None
        ) -> bool:
    if not isinstance(record, Mapping):
        return False
    delegated = record.get("delegated_outcomes")
    governor = (delegated.get("runtime_governor")
        if isinstance(delegated, Mapping) else None)
    evidence_refs = (governor.get("evidence_refs")
        if isinstance(governor, Mapping) else None)
    observation = (evidence_refs.get("resource_entitlement_evidence")
        if isinstance(evidence_refs, Mapping) else None)
    evidence_entitlement = (evidence_refs.get(
        "serving_resource_entitlement_binding")
        if isinstance(evidence_refs, Mapping) else None)
    if (not isinstance(evidence_refs, Mapping)
            or not isinstance(observation, Mapping)):
        return False
    observation_fields = {
        "schema_version", "allocation_id", "allocation_digest", "allocator_id",
        "resource_kind", "policy_digest", "policy_epoch",
        "principal_binding_digest", "remaining_call_entitlement",
        "entitlement_status", "invalidation_reason_code", "checked_at",
        "observation_id", "observation_digest",
    }
    if set(observation) != observation_fields:
        return False
    observation_body = {key: value for key, value in observation.items()
        if key not in {"observation_id", "observation_digest"}}
    observation_digest = observation.get("observation_digest")
    observation_id = observation.get("observation_id")
    try:
        checked_at = datetime.fromisoformat(str(observation.get(
            "checked_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    expected_fields = (
        "allocation_id", "allocation_digest", "allocator_id", "resource_kind",
        "policy_digest", "policy_epoch", "principal_binding_digest")
    entitlement = binding.get("governed_inference_entitlement_binding")
    load_configuration = binding.get("load_configuration")
    activation_state = binding.get("activation_state")
    activation_state_digest = (activation_state.get("state_semantic_digest")
        if isinstance(activation_state, Mapping) else None)
    activation_state_body = ({key: value for key, value in activation_state.items()
        if key not in {"state_semantic_digest", "activation_intent_id",
            "activation_intent_semantic_digest"}}
        if isinstance(activation_state, Mapping) else None)
    configured_gpu_layers = (load_configuration.get("n_gpu_layers")
        if isinstance(load_configuration, Mapping) else None)
    expected_route = ("gpu" if configured_gpu_layers else "cpu")
    return bool(
        observation.get("schema_version") ==
            "sentientos.governed_local_model_resource_entitlement_observation:v2"
        and observation.get("entitlement_status") == "current"
        and observation.get("invalidation_reason_code") is None
        and type(observation.get("remaining_call_entitlement")) is int
        and observation["remaining_call_entitlement"] > 0
        and checked_at.tzinfo is not None and checked_at.utcoffset() is not None
        and isinstance(observation_digest, str)
        and observation_digest == digest_payload(observation_body)
        and isinstance(observation_id, str)
        and observation_id == "lmentitlement-" + observation_digest[:24]
        and (expected_observation_id is None
            or observation_id == expected_observation_id)
        and isinstance(entitlement, Mapping)
        and entitlement.get("schema_version") == SERVING_RESOURCE_ENTITLEMENT_SCHEMA
        and all(observation.get(key) == entitlement.get(key)
            for key in expected_fields)
        and isinstance(activation_state, Mapping)
        and isinstance(activation_state_body, Mapping)
        and activation_state_digest == semantic_digest(activation_state_body)
        and activation_state_digest ==
            binding.get("activation_state_semantic_digest")
        and activation_state.get("load_configuration") == load_configuration
        and _same_serving_resource_entitlement(
            evidence_entitlement, entitlement)
        and type(configured_gpu_layers) is int
        and 0 <= configured_gpu_layers <= 256
        and evidence_refs.get("model_gpu_layers") == configured_gpu_layers
        and evidence_refs.get("model_gpu_layer_entitlement") ==
            entitlement.get("max_gpu_layers")
        and evidence_refs.get("model_gpu_layer_entitlement_invalid") is False
        and evidence_refs.get("model_configuration_digest") ==
            semantic_digest(load_configuration)
        and evidence_refs.get("model_accelerator_route") == expected_route
    )


def _valid_resource_admission_evidence_binding(binding: Mapping[str, Any]) -> bool:
    schema = binding.get("resource_admission_evidence_schema")
    specs = (
        ("model_serving_admission_decision_record", "model_serving_admission_ref",
         "control_plane_correlation_id"),
        ("resource_admission_revalidation_decision",
         "resource_admission_revalidation_decision_ref",
         "resource_admission_revalidation_correlation_id"),
    )
    if schema is None:
        return all(binding.get(record_key) is None or
            _valid_resource_serving_decision_record(binding,
                record_key=record_key, reference_key=reference_key,
                correlation_key=correlation_key)
            for record_key, reference_key, correlation_key in specs)
    if schema != RESOURCE_ADMISSION_EVIDENCE_SCHEMA:
        return False
    initial_record, initial_reference, initial_correlation = specs[0]
    if not all(key in binding for key in (
            initial_record, initial_reference, initial_correlation)):
        return False
    if not _valid_resource_serving_decision_record(binding,
            record_key=initial_record, reference_key=initial_reference,
            correlation_key=initial_correlation):
        return False
    expected_observation_id = binding.get("resource_entitlement_observation_id")
    if expected_observation_id is not None:
        if (not isinstance(expected_observation_id, str)
                or not expected_observation_id
                or not _decision_retains_current_entitlement(
                    binding.get(initial_record), binding,
                    expected_observation_id=expected_observation_id)):
            return False
    postload_record, postload_reference, postload_correlation = specs[1]
    postload_keys = (postload_record, postload_reference, postload_correlation)
    if not any(key in binding for key in postload_keys):
        return expected_observation_id is None
    if (not all(key in binding for key in postload_keys)
            or not _valid_resource_serving_decision_record(binding,
                record_key=postload_record, reference_key=postload_reference,
                correlation_key=postload_correlation)):
        return False
    return (expected_observation_id is None
        or _decision_retains_current_entitlement(
            binding.get(postload_record), binding))


def _valid_serving_resource_entitlement(value: object) -> bool:
    base_fields = {
        "schema_version", "binding_scope", "allocation_id", "allocation_digest",
        "allocator_id", "resource_kind", "policy_digest", "policy_epoch",
        "principal_binding_digest", "remaining_call_entitlement", "checked_at",
    }
    if not isinstance(value, Mapping):
        return False
    schema = value.get("schema_version")
    if schema == LEGACY_SERVING_RESOURCE_ENTITLEMENT_SCHEMA:
        fields = base_fields
    elif schema == SERVING_RESOURCE_ENTITLEMENT_SCHEMA:
        fields = base_fields | {"max_gpu_layers"}
    else:
        return False
    if set(value) != fields:
        return False
    max_gpu_layers = value.get("max_gpu_layers")
    if (schema == SERVING_RESOURCE_ENTITLEMENT_SCHEMA
            and max_gpu_layers is not None
            and (type(max_gpu_layers) is not int or not 0 <= max_gpu_layers <= 256)):
        return False
    checked_at = value.get("checked_at")
    try:
        timestamp = datetime.fromisoformat(
            str(checked_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return bool(
        value.get("schema_version") in {
            LEGACY_SERVING_RESOURCE_ENTITLEMENT_SCHEMA,
            SERVING_RESOURCE_ENTITLEMENT_SCHEMA}
        and value.get("binding_scope") == "inference_call_entitlement"
        and isinstance(value.get("allocation_id"), str)
        and re.fullmatch(r"lmalloc-[0-9a-f]{24}", value["allocation_id"]) is not None
        and isinstance(value.get("allocation_digest"), str)
        and re.fullmatch(r"[0-9a-f]{64}", value["allocation_digest"]) is not None
        and value.get("allocator_id") ==
            "sentientos.governed_local_model_resource_allocator.v1"
        and value.get("resource_kind") ==
            "governed_local_model_invocation_call_entitlement.v1"
        and isinstance(value.get("policy_digest"), str)
        and re.fullmatch(r"[0-9a-f]{64}", value["policy_digest"]) is not None
        and type(value.get("policy_epoch")) is int and value["policy_epoch"] >= 1
        and isinstance(value.get("principal_binding_digest"), str)
        and re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}",
            value["principal_binding_digest"]) is not None
        and type(value.get("remaining_call_entitlement")) is int
        and value["remaining_call_entitlement"] > 0
        and isinstance(checked_at, str) and bool(checked_at)
        and timestamp.tzinfo is not None and timestamp.utcoffset() is not None)


def _same_serving_resource_entitlement(left: object, right: object) -> bool:
    """Compare the stable allocation identity across load revalidation."""
    if (not _valid_serving_resource_entitlement(left)
            or not _valid_serving_resource_entitlement(right)):
        return False
    identity_fields = (
        "schema_version", "binding_scope", "allocation_id", "allocation_digest",
        "allocator_id", "resource_kind", "policy_digest", "policy_epoch",
        "principal_binding_digest", "max_gpu_layers",
    )
    assert isinstance(left, Mapping) and isinstance(right, Mapping)
    return all(left.get(field) == right.get(field) for field in identity_fields)


def _admission_decision_payload(kernel: Any, decision: Any) -> Mapping[str, Any] | None:
    recorded_payload = getattr(kernel, "recorded_decision_payload", None)
    if callable(recorded_payload):
        payload = recorded_payload(decision)
        return payload if isinstance(payload, Mapping) else None
    to_dict = getattr(decision, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        return payload if isinstance(payload, Mapping) else None
    return None


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
    prior_state = activation.get("observed_prior_activation_state")
    if (activation.get("expected_prior_activation_state") != prior_state
            or (state.get("generation") == 1 and prior_state != "ABSENT")
            or (state.get("generation", 0) > 1 and
                (not isinstance(prior_state, str) or len(prior_state) != 64
                 or any(character not in "0123456789abcdef" for character in prior_state)))):
        raise ProductionServingError("activation_predecessor_binding_invalid")
    # The canonical verifier has re-read catalog, commissioning, and artifact bytes and
    # reconstructed the exact activation predecessor chain. Bind its digest to this serving
    # lifetime so model-selection lineage stays distinct from the loaded model identity.
    history = verified.get("activation_history")
    if not isinstance(history, (tuple, list)) or not history:
        raise ProductionServingError("activation_history_unavailable")
    history_digest = semantic_digest({"activation_history": list(history)})
    return {"active_state": dict(state), "activation_receipt": dict(activation),
            "activation_history_digest": history_digest,
            "catalog_proof": dict(verified["catalog_proof"])}


def _attempt_id(identity: Mapping[str, Any]) -> str:
    return "serving-attempt-" + semantic_digest(dict(identity))[:24]


def read_serving_operation_attempts(handle: Any, *, maximum: int = MAX_SERVING_OPERATION_ATTEMPTS
        ) -> tuple[dict[str, Any], ...]:
    if type(maximum) is not int or not 1 <= maximum <= MAX_SERVING_OPERATION_ATTEMPTS:
        raise ProductionServingError("serving_attempt_bound_invalid")
    relative = SERVING_ATTEMPT_ROOT
    try:
        if type(handle) is InstallationStateHandle:
            names = handle.list_regular_names(
                handle.fixed_object(relative), max_entries=maximum)
        elif type(handle) in (InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView):
            names = handle.list_regular_names(relative, max_entries=maximum)
        else:
            raise ProductionServingError("serving_attempt_custody_owner_invalid")
    except InstallationStateError as exc:
        if exc.code in {"state_directory_missing", "state_parent_missing"}:
            return ()
        raise ProductionServingError("serving_attempt_custody_unavailable") from exc
    attempts: list[dict[str, Any]] = []
    total_bytes = 0
    for name in sorted(names):
        if (not isinstance(name, str) or not name.endswith(".json")
                or len(name) != len("serving-attempt-") + 24 + 5
                or any(character not in "0123456789abcdef"
                    for character in name[len("serving-attempt-"):-5])):
            raise ProductionServingError("serving_attempt_name_invalid")
        path = relative + "/" + name
        try:
            if type(handle) is InstallationStateHandle:
                raw = handle.read_regular_bounded(
                    handle.fixed_object(path), max_bytes=MAX_SERVING_OPERATION_ATTEMPT_BYTES)
            else:
                raw = handle.read_regular_bounded(
                    path, max_bytes=MAX_SERVING_OPERATION_ATTEMPT_BYTES)
            total_bytes += len(raw)
            if total_bytes > MAX_SERVING_OPERATION_ATTEMPTS * MAX_SERVING_OPERATION_ATTEMPT_BYTES:
                raise ProductionServingError("serving_attempt_retention_limit_exceeded")
            attempt = json.loads(raw.decode("utf-8"))
        except ProductionServingError:
            raise
        except (InstallationStateError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
            raise ProductionServingError("serving_attempt_custody_invalid") from exc
        if (not isinstance(attempt, dict) or raw != _canonical(attempt)
                or set(attempt) != {"schema_version", "attempt_id", "installation_identity",
                    "serving_operation_id", "activation_state_semantic_digest",
                    "activation_generation", "model_id", "operation_intent_digest",
                    "admission_decision_ref", "reserved_at", "attempt_posture",
                    "current_model_claimed", "inference_performed", "effect_authority",
                    "independent_signature", "attempt_semantic_digest"}
                or attempt.get("schema_version") != SERVING_ATTEMPT_SCHEMA
                or attempt.get("attempt_id") != name[:-5]
                or attempt.get("installation_identity") != handle.identity.value
                or not isinstance(attempt.get("serving_operation_id"), str)
                or not attempt.get("serving_operation_id")
                or len(attempt["serving_operation_id"]) > MAX_OPERATION_ID_LENGTH
                or attempt.get("attempt_id") != _attempt_id({
                    "installation_identity": attempt.get("installation_identity"),
                    "serving_operation_id": attempt.get("serving_operation_id"),
                    "activation_state_semantic_digest":
                        attempt.get("activation_state_semantic_digest")})
                or not isinstance(attempt.get("activation_state_semantic_digest"), str)
                or len(attempt["activation_state_semantic_digest"]) != 64
                or any(character not in "0123456789abcdef"
                    for character in attempt["activation_state_semantic_digest"])
                or type(attempt.get("activation_generation")) is not int
                or attempt["activation_generation"] < 1
                or not isinstance(attempt.get("model_id"), str) or not attempt["model_id"]
                or not isinstance(attempt.get("operation_intent_digest"), str)
                or len(attempt["operation_intent_digest"]) != 64
                or any(character not in "0123456789abcdef" for character in attempt["operation_intent_digest"])
                or not isinstance(attempt.get("admission_decision_ref"), str)
                or not attempt["admission_decision_ref"]
                or attempt.get("attempt_posture") != "durably_reserved_before_model_load"
                or attempt.get("current_model_claimed") is not False
                or attempt.get("inference_performed") is not False
                or attempt.get("effect_authority") is not False
                or attempt.get("independent_signature") is not False
                or attempt.get("attempt_semantic_digest")
                    != semantic_digest({key: value for key, value in attempt.items()
                        if key != "attempt_semantic_digest"})):
            raise ProductionServingError("serving_attempt_identity_invalid")
        try:
            timestamp = datetime.fromisoformat(
                str(attempt.get("reserved_at", "")).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ProductionServingError("serving_attempt_time_invalid") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ProductionServingError("serving_attempt_time_invalid")
        attempts.append(attempt)
    return tuple(attempts)


def read_serving_operation_history(handle: Any, *, maximum: int = MAX_SERVING_OPERATION_ATTEMPTS
        ) -> tuple[dict[str, Any], ...]:
    """Reconcile durable operation reservations with exact owner receipts.

    A reservation without a receipt remains outcome-unknown. Historical receipts
    predating reservations remain readable but are explicitly unbound.
    """
    attempts = read_serving_operation_attempts(handle, maximum=maximum)
    by_operation = {item["serving_operation_id"]: item for item in attempts}
    if len(by_operation) != len(attempts):
        raise ProductionServingError("serving_operation_attempt_collision")
    receipt_root = "local-model/serving/receipts"
    try:
        if type(handle) is InstallationStateHandle:
            names = handle.list_regular_names(handle.fixed_object(receipt_root), max_entries=maximum)
        elif type(handle) in (InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView):
            names = handle.list_regular_names(receipt_root, max_entries=maximum)
        else:
            raise ProductionServingError("serving_receipt_custody_owner_invalid")
    except InstallationStateError as exc:
        if exc.code in {"state_directory_missing", "state_parent_missing"}:
            names = ()
        else:
            raise ProductionServingError("serving_receipt_custody_unavailable") from exc
    receipts: list[dict[str, Any]] = []
    receipt_bytes = 0
    for name in sorted(names):
        if (not isinstance(name, str) or not name.startswith("serving-receipt-")
                or not name.endswith(".json") or len(name) != len("serving-receipt-") + 24 + 5
                or any(char not in "0123456789abcdef" for char in name[len("serving-receipt-"):-5])):
            raise ProductionServingError("serving_receipt_name_invalid")
        path = receipt_root + "/" + name
        try:
            raw = (handle.read_regular_bounded(handle.fixed_object(path),
                    max_bytes=MAX_SERVING_OPERATION_ATTEMPT_BYTES)
                if type(handle) is InstallationStateHandle else
                handle.read_regular_bounded(path, max_bytes=MAX_SERVING_OPERATION_ATTEMPT_BYTES))
            receipt_bytes += len(raw)
            if receipt_bytes > maximum * MAX_SERVING_OPERATION_ATTEMPT_BYTES:
                raise ProductionServingError("serving_receipt_retention_limit_exceeded")
            receipt = json.loads(raw.decode("utf-8"))
        except ProductionServingError:
            raise
        except (InstallationStateError, OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
            raise ProductionServingError("serving_receipt_custody_invalid") from exc
        legacy_receipt_fields = {
            "schema_version", "status", "session_id", "binding",
            "control_plane_authority_class", "admission_outcome", "model_loaded",
            "serving_session_bound", "inference_performed",
            "local_model_inference_authority_granted", "adjacent_authority_granted",
            "receipt_id", "receipt_semantic_digest",
        }
        linked_receipt_fields = legacy_receipt_fields | {
            "serving_operation_attempt_id", "serving_operation_attempt_semantic_digest",
            "model_loaded_at",
        }
        receipt_fields = frozenset(receipt) if isinstance(receipt, dict) else frozenset()
        contextual_receipt_fields = {
            frozenset(legacy_receipt_fields | {"resource_admission_context"}),
            frozenset(linked_receipt_fields | {"resource_admission_context"}),
        }
        if (not isinstance(receipt, dict) or raw != _canonical(receipt)
                or (receipt_fields not in {frozenset(legacy_receipt_fields),
                    frozenset(linked_receipt_fields)}
                    and receipt_fields not in contextual_receipt_fields)
                or ("resource_admission_context" in receipt
                    and not isinstance(receipt.get("resource_admission_context"), dict))
                or receipt.get("status") not in {"production_current", "serving_session_bound"}
                or ("serving_operation_attempt_id" in receipt
                    and (not isinstance(receipt.get("model_loaded_at"), str)
                        or not isinstance(receipt.get("serving_operation_attempt_id"), str)
                        or not receipt.get("serving_operation_attempt_id")
                        or not isinstance(receipt.get("serving_operation_attempt_semantic_digest"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}",
                            receipt.get("serving_operation_attempt_semantic_digest", ""))))
                or receipt.get("local_model_inference_authority_granted") is not False
                or receipt.get("adjacent_authority_granted") is not False
                or receipt.get("schema_version") != RECEIPT_SCHEMA
                or receipt.get("receipt_semantic_digest") != semantic_digest(
                    {key: value for key, value in receipt.items() if key != "receipt_semantic_digest"})
                or receipt.get("receipt_id") != name[:-5]
                or receipt.get("receipt_id") != "serving-receipt-" + semantic_digest(
                    {key: value for key, value in receipt.items()
                     if key not in {"receipt_id", "receipt_semantic_digest"}})[:24]
                or receipt.get("control_plane_authority_class") != AuthorityClass.MODEL_SERVING.value
                or receipt.get("admission_outcome") != AdmissionOutcome.ALLOW.value
                or receipt.get("model_loaded") is not True
                or receipt.get("serving_session_bound") is not True
                or receipt.get("inference_performed") is not False):
            raise ProductionServingError("serving_receipt_identity_invalid")
        binding = receipt.get("binding")
        if (not isinstance(binding, dict)
                or binding.get("installation_identity") != handle.identity.value
                or not isinstance(binding.get("serving_operation_id"), str)
                or receipt.get("session_id") != "serving-session-" + semantic_digest(binding)[:24]):
            raise ProductionServingError("serving_receipt_binding_invalid")
        loaded_at = receipt.get("model_loaded_at")
        if loaded_at is not None:
            try:
                timestamp = datetime.fromisoformat(str(loaded_at).replace("Z", "+00:00"))
            except (TypeError, ValueError) as exc:
                raise ProductionServingError("serving_receipt_time_invalid") from exc
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ProductionServingError("serving_receipt_time_invalid")
        if not _valid_resource_admission_evidence_binding(binding):
            raise ProductionServingError(
                "serving_resource_admission_evidence_binding_invalid")
        resource_entitlement = binding.get(
            "governed_inference_entitlement_binding")
        resource_admission_context = receipt.get("resource_admission_context")
        context_entitlement = (resource_admission_context.get(
            "governed_inference_entitlement_binding")
            if isinstance(resource_admission_context, Mapping) else None)
        context_observation_id = (resource_admission_context.get(
            "resource_entitlement_observation_id")
            if isinstance(resource_admission_context, Mapping) else None)
        if (resource_entitlement is not None
                and (not _valid_serving_resource_entitlement(resource_entitlement)
                    or context_entitlement != resource_entitlement)):
            raise ProductionServingError(
                "serving_resource_entitlement_binding_invalid")
        if context_entitlement is not None and resource_entitlement is None:
            raise ProductionServingError(
                "serving_resource_entitlement_binding_invalid")
        if (binding.get("resource_entitlement_observation_id") is not None
                and binding.get("resource_entitlement_observation_id")
                    != context_observation_id):
            raise ProductionServingError(
                "serving_resource_entitlement_observation_binding_invalid")
        if (context_observation_id is not None
                and binding.get("resource_entitlement_observation_id") is None):
            raise ProductionServingError(
                "serving_resource_entitlement_observation_binding_invalid")
        receipts.append(receipt)
    by_receipt_operation: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        binding = receipt["binding"]
        operation_id = binding["serving_operation_id"]
        if operation_id in by_receipt_operation:
            raise ProductionServingError("serving_operation_receipt_collision")
        by_receipt_operation[operation_id] = receipt
    history: list[dict[str, Any]] = []
    for attempt in attempts:
        receipt = by_receipt_operation.pop(attempt["serving_operation_id"], None)
        if receipt is not None:
            binding = receipt["binding"]
            top_attempt_id = receipt.get("serving_operation_attempt_id")
            top_attempt_digest = receipt.get("serving_operation_attempt_semantic_digest")
            if ((top_attempt_id is None) != (top_attempt_digest is None)
                    or (top_attempt_id is not None and (
                        top_attempt_id != attempt["attempt_id"]
                        or top_attempt_digest != attempt["attempt_semantic_digest"]))):
                raise ProductionServingError("serving_attempt_receipt_reference_incomplete")
            intent_fields = ("installation_identity", "activation_state_semantic_digest",
                "activation_generation", "activation_predecessor_state_digest",
                "activation_receipt_id", "activation_receipt_semantic_digest",
                "activation_history_digest", "model_id", "artifact_id", "runtime_id",
                "authority_map_digest", "serving_operation_id")
            intent = {key: binding[key] for key in intent_fields if key in binding}
            if (len(intent) != len(intent_fields)
                    or semantic_digest(intent) != attempt["operation_intent_digest"]
                    or binding.get("activation_state_semantic_digest")
                        != attempt["activation_state_semantic_digest"]
                    or binding.get("activation_generation") != attempt["activation_generation"]
                    or binding.get("model_id") != attempt["model_id"]
                    or binding.get("model_serving_admission_ref") != attempt["admission_decision_ref"]
                    or receipt.get("serving_operation_attempt_id", attempt["attempt_id"])
                        != attempt["attempt_id"]
                    or receipt.get("serving_operation_attempt_semantic_digest",
                        attempt["attempt_semantic_digest"]) != attempt["attempt_semantic_digest"]
                    or ((binding.get("serving_operation_attempt_id") is not None
                         or binding.get("serving_operation_attempt_semantic_digest") is not None)
                        and (binding.get("serving_operation_attempt_id") != attempt["attempt_id"]
                            or binding.get("serving_operation_attempt_semantic_digest")
                                != attempt["attempt_semantic_digest"]))):
                raise ProductionServingError("serving_attempt_receipt_lineage_mismatch")
            status = "serving_receipt_verified"
        else:
            status = "reservation_outcome_unknown"
        row = {"status": status, "attempt": attempt,
            "attempt_semantic_digest": attempt["attempt_semantic_digest"],
            "receipt": receipt,
            "receipt_semantic_digest": receipt.get("receipt_semantic_digest") if receipt else None}
        row["history_semantic_digest"] = semantic_digest(row)
        history.append(row)
    for operation_id, receipt in sorted(by_receipt_operation.items()):
        binding = receipt.get("binding")
        linked_attempt_fields = (
            receipt.get("serving_operation_attempt_id"),
            receipt.get("serving_operation_attempt_semantic_digest"),
            binding.get("serving_operation_attempt_id") if isinstance(binding, Mapping) else None,
            binding.get("serving_operation_attempt_semantic_digest")
                if isinstance(binding, Mapping) else None,
        )
        if any(item is not None for item in linked_attempt_fields):
            raise ProductionServingError("serving_receipt_attempt_predecessor_missing")
        row = {"status": "legacy_receipt_without_reservation", "attempt": None,
            "attempt_semantic_digest": None, "receipt": receipt,
            "receipt_semantic_digest": receipt["receipt_semantic_digest"]}
        row["history_semantic_digest"] = semantic_digest(row)
        history.append(row)
    if len(history) > maximum * 2:
        raise ProductionServingError("serving_operation_history_retention_limit_exceeded")
    return tuple(history)


def _reject_replayed_lifetime(handle: InstallationStateHandle, operation_id: str,
                              activation_digest: str) -> None:
    del activation_digest
    # One canonical bounded reader checks receipt shape and exact reservation
    # joins before deciding whether an operation ID has already been used.
    history = read_serving_operation_history(handle, maximum=MAX_SERVING_OPERATION_ATTEMPTS)
    for item in history:
        attempt = item.get("attempt")
        receipt = item.get("receipt")
        binding = receipt.get("binding") if isinstance(receipt, Mapping) else None
        if ((isinstance(attempt, Mapping)
                and attempt.get("serving_operation_id") == operation_id)
                or (isinstance(binding, Mapping)
                    and binding.get("serving_operation_id") == operation_id)):
            raise ProductionServingError("serving_operation_reused")


def _reserve_serving_operation_attempt(handle: InstallationStateHandle, *,
        operation_intent: Mapping[str, Any], admission_decision_ref: str) -> dict[str, Any]:
    if not isinstance(admission_decision_ref, str) or not admission_decision_ref:
        raise ProductionServingError("serving_attempt_admission_reference_missing")
    operation_id = str(operation_intent["serving_operation_id"])
    identity = {
        "installation_identity": handle.identity.value,
        "serving_operation_id": operation_id,
        "activation_state_semantic_digest": operation_intent["activation_state_semantic_digest"],
    }
    attempt_id = _attempt_id(identity)
    body: dict[str, Any] = {
        "schema_version": SERVING_ATTEMPT_SCHEMA,
        "attempt_id": attempt_id,
        **identity,
        "activation_generation": operation_intent["activation_generation"],
        "model_id": operation_intent["model_id"],
        "operation_intent_digest": semantic_digest(dict(operation_intent)),
        "admission_decision_ref": admission_decision_ref,
        "reserved_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "attempt_posture": "durably_reserved_before_model_load",
        "current_model_claimed": False,
        "inference_performed": False,
        "effect_authority": False,
        "independent_signature": False,
    }
    body["attempt_semantic_digest"] = semantic_digest(body)
    raw = _canonical(body)
    if len(raw) > MAX_SERVING_OPERATION_ATTEMPT_BYTES:
        raise ProductionServingError("serving_attempt_too_large")
    directory = handle.fixed_object(SERVING_ATTEMPT_ROOT)
    handle.ensure_directory(directory)
    target = handle.fixed_object(SERVING_ATTEMPT_ROOT + "/" + attempt_id + ".json")
    lock = handle.fixed_object("local-model/serving/operation-owner.lock")
    try:
        with handle.exclusive_lock(lock):
            _reject_replayed_lifetime(handle, operation_id,
                str(operation_intent["activation_state_semantic_digest"]))
            handle.durable_create(target, raw)
    except ProductionServingError:
        raise
    except InstallationStateError as exc:
        raise ProductionServingError("serving_attempt_publication_failed") from exc
    return body




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

    _RESOURCE_RELEASE_ACTORS = frozenset({
        "production_chat_host_resource_governor",
        "production_chat_game_resource_governor",
        "production_chat_workload_resource_governor",
        "production_chat_resource_entitlement_governor",
    })

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
        self._last_released_session_id: str | None = None
        self._admission_context_provider: Callable[
            [str, Mapping[str, Any]], Mapping[str, Any]
        ] | None = None
        self._resource_recovery_activation_digest: str | None = None
        self._resource_recovery_pending = False
        self._resource_recovery_requires_game_clearance = False
        self._resource_recovery_game_clearance_after: dict[str, str] | None = None
        self._pending_game_recovery_holds: dict[str, dict[str, Any]] = {}
        self._lifecycle_lock = threading.RLock()
        for relative in ("local-model", "local-model/serving", "local-model/serving/receipts",
                SERVING_ATTEMPT_ROOT, GAME_RECOVERY_HOLD_ROOT,
                GAME_RECOVERY_CLEARANCE_ROOT):
            installation_handle.ensure_directory(installation_handle.fixed_object(relative))
        self._pending_game_recovery_holds = self._load_pending_game_recovery_holds()
        if self._pending_game_recovery_holds:
            latest = next(reversed(self._pending_game_recovery_holds.values()))
            self._resource_recovery_pending = True
            self._resource_recovery_requires_game_clearance = True
            self._resource_recovery_game_clearance_after = {
                "source_id": latest["game_source_id"],
                "generation_id": latest["game_generation_id"],
                "observed_at": latest["game_pressure_observed_at"],
            }

    def _load_pending_game_recovery_holds(self) -> dict[str, dict[str, Any]]:
        try:
            names = self._handle.list_regular_names(
                self._handle.fixed_object(GAME_RECOVERY_HOLD_ROOT),
                max_entries=MAX_GAME_RECOVERY_HOLDS)
        except (InstallationStateError, OSError) as exc:
            raise ProductionServingError("game_resource_recovery_hold_state_unavailable") from exc
        pending: dict[str, dict[str, Any]] = {}
        for name in names:
            if re.fullmatch(r"game-recovery-[0-9a-f]{32}\.json", name) is None:
                raise ProductionServingError("game_resource_recovery_hold_name_invalid")
            try:
                raw = self._handle.read_regular_bounded(
                    self._handle.fixed_object(f"{GAME_RECOVERY_HOLD_ROOT}/{name}"),
                    max_bytes=MAX_SERVING_OPERATION_ATTEMPT_BYTES)
                marker = json.loads(raw)
            except (InstallationStateError, OSError, ValueError) as exc:
                raise ProductionServingError("game_resource_recovery_hold_invalid") from exc
            if not isinstance(marker, dict):
                raise ProductionServingError("game_resource_recovery_hold_invalid")
            supplied_digest = marker.get("marker_semantic_digest")
            body = {key: value for key, value in marker.items()
                if key != "marker_semantic_digest"}
            hold_id = marker.get("hold_id")
            expected_name = f"game-recovery-{hold_id}.json"
            record = marker.get("release_admission_record")
            delegated = record.get("delegated_outcomes") if isinstance(
                record, Mapping) else None
            governor = delegated.get("runtime_governor") if isinstance(
                delegated, Mapping) else None
            evidence_refs = governor.get("evidence_refs") if isinstance(
                governor, Mapping) else None
            release_evidence = (evidence_refs.get("resource_observation_evidence")
                if isinstance(evidence_refs, Mapping) else None)
            release_target = (evidence_refs.get("resource_release_target")
                if isinstance(evidence_refs, Mapping) else None)
            release_ref = marker.get("release_admission_decision_ref")
            identity_digest = marker.get("model_identity_digest")
            if (marker.get("schema_version") != GAME_RECOVERY_HOLD_SCHEMA
                    or set(marker) != {
                        "schema_version", "hold_id", "release_admission_decision_ref",
                        "release_admission_record", "serving_session_id",
                        "model_identity_digest", "game_source_id", "game_generation_id",
                        "game_pressure_observed_at", "marker_semantic_digest"}
                    or name != expected_name
                    or not isinstance(release_ref, str)
                    or not release_ref.startswith("kernel_decision:")
                    or hold_id != hashlib.sha256(release_ref.encode("utf-8")).hexdigest()[:32]
                    or not isinstance(supplied_digest, str)
                    or semantic_digest(body) != supplied_digest
                    or not isinstance(record, Mapping)
                    or record.get("final_disposition") != "allow"
                    or record.get("event_type") != "control_plane_decision"
                    or record.get("outcome") != "allow"
                    or record.get("authority_class") != "local_model_resource_release"
                    or record.get("action_kind") != "local_model_resource_release"
                    or record.get("actor") != "production_chat_game_resource_governor"
                    or record.get("target_subsystem") != "production_chat"
                    or record.get("current_phase") != "runtime"
                    or record.get("requested_phase") != "runtime"
                    or record.get("correlation_id") != release_ref[len("kernel_decision:"):]
                    or record.get("admission_decision_ref") != release_ref
                    or not isinstance(release_evidence, Mapping)
                    or release_evidence.get("status") != "current"
                    or release_evidence.get("workload_mode") != "normal"
                    or not isinstance(marker.get("serving_session_id"), str)
                    or re.fullmatch(r"serving-session-[0-9a-f]{24}",
                        str(marker.get("serving_session_id"))) is None
                    or not isinstance(identity_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", identity_digest) is None
                    or not isinstance(marker.get("game_source_id"), str)
                    or not marker.get("game_source_id")
                    or not isinstance(marker.get("game_generation_id"), str)
                    or not marker.get("game_generation_id")
                    or not isinstance(marker.get("game_pressure_observed_at"), str)
                    or not marker.get("game_pressure_observed_at")
                    or type(release_evidence.get("process_cpu_percent")) not in {
                        int, float}
                    or not math.isfinite(float(
                        release_evidence.get("process_cpu_percent", float("nan"))))
                    or release_evidence.get("process_cpu_percent") < 100.0
                    or release_evidence.get("game_performance_source_id") !=
                        marker.get("game_source_id")
                    or release_evidence.get("game_performance_generation_id") !=
                        marker.get("game_generation_id")
                    or release_evidence.get("game_performance_observed_at") !=
                        marker.get("game_pressure_observed_at")
                    or not isinstance(release_target, Mapping)
                    or release_target.get("schema_version") !=
                        "sentientos.production_chat_resource_release_target:v1"
                    or release_target.get("serving_session_id") !=
                        marker.get("serving_session_id")
                    or release_target.get("model_identity_digest") != identity_digest):
                raise ProductionServingError("game_resource_recovery_hold_binding_invalid")
            clearance_name = f"{hold_id}.json"
            try:
                clearance_raw = self._handle.read_regular_bounded(
                    self._handle.fixed_object(
                        f"{GAME_RECOVERY_CLEARANCE_ROOT}/{clearance_name}"),
                    max_bytes=MAX_SERVING_OPERATION_ATTEMPT_BYTES)
            except (InstallationStateError, OSError):
                pending[hold_id] = marker
                continue
            try:
                clearance = json.loads(clearance_raw)
            except ValueError as exc:
                raise ProductionServingError(
                    "game_resource_recovery_clearance_invalid") from exc
            clearance_body = ({key: value for key, value in clearance.items()
                if key != "clearance_semantic_digest"}
                if isinstance(clearance, dict) else {})
            try:
                clearance_at = datetime.fromisoformat(str(
                    clearance.get("game_observed_at", "")).replace("Z", "+00:00")
                    ) if isinstance(clearance, dict) else None
                pressure_at = datetime.fromisoformat(str(
                    marker.get("game_pressure_observed_at", "")).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                clearance_at = pressure_at = None
            if (not isinstance(clearance, dict)
                    or set(clearance) != {
                        "schema_version", "hold_id", "hold_semantic_digest",
                        "game_source_id", "game_generation_id", "game_message_id",
                        "game_observed_at", "game_foreground", "game_process_running",
                        "clearance_semantic_digest"}
                    or clearance.get("schema_version") != GAME_RECOVERY_CLEARANCE_SCHEMA
                    or clearance.get("hold_id") != hold_id
                    or clearance.get("hold_semantic_digest") != supplied_digest
                    or clearance.get("game_source_id") != marker.get("game_source_id")
                    or clearance.get("game_generation_id") !=
                        marker.get("game_generation_id")
                    or not isinstance(clearance.get("game_message_id"), str)
                    or re.fullmatch(r"[0-9a-f]{64}",
                        str(clearance.get("game_message_id"))) is None
                    or clearance.get("game_foreground") is not False
                    or clearance.get("game_process_running") is not False
                    or not isinstance(clearance.get("clearance_semantic_digest"), str)
                    or semantic_digest(clearance_body) !=
                        clearance.get("clearance_semantic_digest")
                    or clearance_at is None or pressure_at is None
                    or clearance_at.tzinfo is None or clearance_at.utcoffset() is None
                    or pressure_at.tzinfo is None or pressure_at.utcoffset() is None
                    or clearance_at.astimezone(timezone.utc)
                        <= pressure_at.astimezone(timezone.utc)):
                raise ProductionServingError(
                    "game_resource_recovery_clearance_binding_invalid")
        return pending

    def _write_game_recovery_hold(self, expected: ServingSession,
            admission_decision: ControlActionDecision,
            game_evidence: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        reference = admission_decision.admission_decision_ref
        hold_id = hashlib.sha256(reference.encode("utf-8")).hexdigest()[:32]
        record = self._kernel.recorded_decision_payload(admission_decision)
        if not isinstance(record, Mapping):
            raise ProductionServingError("game_resource_recovery_admission_record_required")
        delegated = record.get("delegated_outcomes")
        governor = delegated.get("runtime_governor") if isinstance(
            delegated, Mapping) else None
        evidence_refs = governor.get("evidence_refs") if isinstance(
            governor, Mapping) else None
        release_evidence = (evidence_refs.get("resource_observation_evidence")
            if isinstance(evidence_refs, Mapping) else None)
        release_target = (evidence_refs.get("resource_release_target")
            if isinstance(evidence_refs, Mapping) else None)
        if (not isinstance(release_evidence, Mapping)
                or release_evidence.get("status") != "current"
                or release_evidence.get("workload_mode") != "normal"
                or release_evidence.get("process_cpu_percent") is None
                or isinstance(release_evidence.get("process_cpu_percent"), bool)
                or not isinstance(release_evidence.get("process_cpu_percent"), (int, float))
                or not math.isfinite(float(release_evidence["process_cpu_percent"]))
                or float(release_evidence["process_cpu_percent"]) < 100.0
                or release_evidence.get("game_performance_source_id") !=
                    game_evidence.get("source_id")
                or release_evidence.get("game_performance_generation_id") !=
                    game_evidence.get("generation_id")
                or release_evidence.get("game_performance_observed_at") !=
                    game_evidence.get("observed_at")
                or not isinstance(release_target, Mapping)
                or release_target.get("serving_session_id") != expected.session_id):
            raise ProductionServingError("game_resource_recovery_admission_evidence_mismatch")
        marker: dict[str, Any] = {
            "schema_version": GAME_RECOVERY_HOLD_SCHEMA,
            "hold_id": hold_id,
            "release_admission_decision_ref": reference,
            "release_admission_record": dict(record),
            "serving_session_id": expected.session_id,
            "model_identity_digest": digest_payload(dict(
                expected.binding["observed_loaded_model_identity"])),
            "game_source_id": game_evidence["source_id"],
            "game_generation_id": game_evidence["generation_id"],
            "game_pressure_observed_at": game_evidence["observed_at"],
        }
        marker["marker_semantic_digest"] = semantic_digest(marker)
        if len(_canonical(marker)) > MAX_SERVING_OPERATION_ATTEMPT_BYTES:
            raise ProductionServingError("game_resource_recovery_hold_size_exceeded")
        _create(self._handle,
            f"{GAME_RECOVERY_HOLD_ROOT}/game-recovery-{hold_id}.json", marker)
        return hold_id, marker

    def _game_clearance_is_current(self, evidence: object) -> bool:
        if (not isinstance(evidence, Mapping)
                or evidence.get("game_foreground") is not False
                or evidence.get("game_process_running") is not False):
            return False
        markers = tuple(self._pending_game_recovery_holds.values())
        if not markers and self._resource_recovery_game_clearance_after is not None:
            markers = (self._resource_recovery_game_clearance_after,)
        if not markers:
            return False
        try:
            clearance_at = datetime.fromisoformat(
                str(evidence["observed_at"]).replace("Z", "+00:00"))
            if clearance_at.tzinfo is None or clearance_at.utcoffset() is None:
                return False
            for marker in markers:
                pressure_at = datetime.fromisoformat(str(
                    marker.get("game_pressure_observed_at", marker.get("observed_at", ""))
                ).replace("Z", "+00:00"))
                if (evidence.get("source_id") != marker.get(
                        "game_source_id", marker.get("source_id"))
                        or evidence.get("generation_id") != marker.get(
                            "game_generation_id", marker.get("generation_id"))
                        or pressure_at.tzinfo is None or pressure_at.utcoffset() is None
                        or clearance_at.astimezone(timezone.utc)
                            <= pressure_at.astimezone(timezone.utc)):
                    return False
        except (KeyError, TypeError, ValueError):
            return False
        return True

    def _current_game_recovery_clearance(self) -> Mapping[str, Any] | None:
        getter = getattr(self._kernel,
            "current_verified_game_workload_evidence", None)
        try:
            evidence = getter() if callable(getter) else None
        except Exception:
            evidence = None
        return (evidence if isinstance(evidence, Mapping)
            and self._game_clearance_is_current(evidence) else None)

    def _record_game_recovery_clearances(self, evidence: Mapping[str, Any]) -> None:
        for hold_id, marker in self._pending_game_recovery_holds.items():
            clearance: dict[str, Any] = {
                "schema_version": GAME_RECOVERY_CLEARANCE_SCHEMA,
                "hold_id": hold_id,
                "hold_semantic_digest": marker["marker_semantic_digest"],
                "game_source_id": evidence["source_id"],
                "game_generation_id": evidence["generation_id"],
                "game_message_id": evidence["message_id"],
                "game_observed_at": evidence["observed_at"],
                "game_foreground": False,
                "game_process_running": False,
            }
            clearance["clearance_semantic_digest"] = semantic_digest(clearance)
            _create(self._handle,
                f"{GAME_RECOVERY_CLEARANCE_ROOT}/{hold_id}.json", clearance)
        self._pending_game_recovery_holds.clear()

    def _same_activation(self, verified: Mapping[str, Any], session: ServingSession) -> bool:
        state = verified["active_state"]
        if session.binding.get("activation_state_semantic_digest") != state.get("state_semantic_digest"):
            return False
        if session.binding.get("activation_generation") != state.get("generation"):
            return False
        if session.binding.get("activation_state") != state:
            return False
        if session.binding.get("activation_history_digest") != verified.get("activation_history_digest"):
            return False
        if self._model is None:
            return False
        try:
            loaded_identity = _identity(self._model.active_identity)
        except Exception:
            return False
        if loaded_identity != session.binding.get("observed_loaded_model_identity"):
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
        with self._lifecycle_lock:
            return self._current_session_locked()

    def _current_session_locked(self) -> ServingSession | None:
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

    def observed_current_session(self) -> ServingSession | None:
        """Return a current opaque session without invalidating or unloading it."""
        session = self._session
        if session is None:
            return None
        try:
            verified = _verified(self._handle, self._allow_synthetic)
        except ProductionServingError:
            return None
        if not self._same_activation(verified, session) or not self._alive():
            return None
        return session

    def serving_is_current(self) -> bool:
        """Inspect readiness without invalidating, unloading, or exposing model custody."""
        return self.observed_current_session() is not None

    def resource_recovery_pending(self) -> bool:
        """Report whether a governed resource release left a recoverable serving lifetime."""
        with self._lifecycle_lock:
            return self._resource_recovery_pending

    def recover_after_resource_release(self) -> dict[str, Any]:
        """Attempt a fresh governed serving admission after an exact resource release."""
        with self._lifecycle_lock:
            if not self._resource_recovery_pending:
                return {"status": "not_pending"}
            clearance: Mapping[str, Any] | None = None
            if self._resource_recovery_requires_game_clearance:
                clearance = self._current_game_recovery_clearance()
                if clearance is None:
                    return {"status": "deferred",
                        "reason_code": "fresh_verified_game_clearance_required"}
            if self._session is not None or self._model is not None:
                return {"status": "skipped", "reason_code": "serving_session_already_current"}
            provider = self._admission_context_provider
            activation_digest = self._resource_recovery_activation_digest
            if provider is None or activation_digest is None:
                return {"status": "deferred",
                    "reason_code": "fresh_serving_admission_context_unavailable"}
            operation_id = "resource-recovery-" + uuid.uuid4().hex
            try:
                session = self._establish_locked(operation_id=operation_id,
                    expected_activation_state_digest=activation_digest,
                    admission_context_provider=provider)
            except ProductionServingError as exc:
                return {"status": "deferred", "reason_code": exc.code}
            if clearance is not None and self._pending_game_recovery_holds:
                try:
                    self._record_game_recovery_clearances(clearance)
                except ProductionServingError as exc:
                    self._invalidate_locked("game_recovery_clearance_publication_failed")
                    return {"status": "deferred", "reason_code": exc.code}
            self._resource_recovery_pending = False
            self._resource_recovery_requires_game_clearance = False
            self._resource_recovery_game_clearance_after = None
            return {"status": "restored", "serving_operation_id": operation_id,
                "serving_session_id": session.session_id,
                "serving_operation_attempt_id": session.binding.get(
                    "serving_operation_attempt_id")}

    def _current_inference_model(self, expected: ServingSession) -> Any:
        """Package-private handoff for the separately governed inference bridge."""
        with self._lifecycle_lock:
            return self._current_inference_model_locked(expected)

    def _current_inference_model_locked(self, expected: ServingSession) -> Any:
        current = self.current_session()
        if current is None or current != expected or self._model is None:
            raise ProductionServingError("serving_session_not_current")
        if _identity(self._model.active_identity) != expected.binding.get("observed_loaded_model_identity"):
            self._invalidate("loaded_model_identity_changed")
            raise ProductionServingError("loaded_model_identity_changed")
        return self._model

    def _invalidate_inference_session(self, expected: ServingSession, reason: str) -> None:
        with self._lifecycle_lock:
            if self._session == expected:
                self._invalidate_locked(reason)

    def establish(self, *, operation_id: str,
                  expected_activation_state_digest: str | None = None,
                  admission_context_provider: Callable[
                      [str, Mapping[str, Any]], Mapping[str, Any]
                  ] | None = None
                  ) -> ServingSession:
        with self._lifecycle_lock:
            clearance: Mapping[str, Any] | None = None
            if self._pending_game_recovery_holds:
                clearance = self._current_game_recovery_clearance()
                if clearance is None:
                    raise ProductionServingError(
                        "fresh_verified_game_clearance_required")
            session = self._establish_locked(operation_id=operation_id,
                expected_activation_state_digest=expected_activation_state_digest,
                admission_context_provider=admission_context_provider)
            if clearance is not None:
                try:
                    self._record_game_recovery_clearances(clearance)
                except ProductionServingError:
                    self._invalidate_locked(
                        "game_recovery_clearance_publication_failed")
                    raise
            self._admission_context_provider = admission_context_provider
            self._resource_recovery_activation_digest = session.binding.get(
                "activation_state_semantic_digest")
            self._resource_recovery_pending = False
            self._resource_recovery_requires_game_clearance = False
            self._resource_recovery_game_clearance_after = None
            return session

    def _establish_locked(self, *, operation_id: str,
                  expected_activation_state_digest: str | None = None,
                  admission_context_provider: Callable[
                      [str, Mapping[str, Any]], Mapping[str, Any]
                  ] | None = None
                  ) -> ServingSession:
        operation_id = _operation_id(operation_id)
        if expected_activation_state_digest is not None:
            expected_activation_state_digest = _semantic_digest(expected_activation_state_digest)
        before = _verified(self._handle, self._allow_synthetic)
        if (expected_activation_state_digest is not None
                and before["active_state"].get("state_semantic_digest") != expected_activation_state_digest):
            raise ProductionServingError("expected_activation_state_mismatch")
        existing = self.current_session()
        if existing is not None:
            if existing.binding.get("serving_operation_id") != operation_id:
                raise ProductionServingError("current_serving_operation_mismatch")
            return existing
        state, activation, proof = before["active_state"], before["activation_receipt"], before["catalog_proof"]
        _reject_replayed_lifetime(self._handle, operation_id, state["state_semantic_digest"])
        intent = {"installation_identity": self._handle.identity.value,
                  "activation_state_semantic_digest": state["state_semantic_digest"],
                  "activation_generation": state["generation"],
                  "activation_predecessor_state_digest": activation["observed_prior_activation_state"],
                  "activation_receipt_id": activation["receipt_id"],
                  "activation_receipt_semantic_digest": activation["receipt_semantic_digest"],
                  "activation_history_digest": before["activation_history_digest"],
                  "model_id": state["model_id"], "artifact_id": state["artifact_id"],
                  "runtime_id": state["runtime_id"], "authority_map_digest": state["authority_map_digest"]}
        operation_intent = {**intent, "serving_operation_id": operation_id}
        correlation = "model-serving:" + semantic_digest(operation_intent)
        admission_context: Mapping[str, Any] = {}
        if admission_context_provider is not None:
            try:
                admission_context = admission_context_provider(correlation, state)
            except Exception as exc:
                raise ProductionServingError("model_serving_resource_preflight_unavailable") from exc
            if not isinstance(admission_context, Mapping):
                raise ProductionServingError("model_serving_resource_preflight_invalid")
        resource_entitlement_binding = admission_context.get(
            "governed_inference_entitlement_binding")
        if (resource_entitlement_binding is not None
                and not _valid_serving_resource_entitlement(
                    resource_entitlement_binding)):
            raise ProductionServingError(
                "model_serving_resource_entitlement_binding_invalid")
        admission_metadata = {**dict(admission_context), **operation_intent,
            "correlation_id": correlation}
        decision = self._kernel.admit(ControlActionRequest(
            action_kind=ACTION, authority_class=AuthorityClass.MODEL_SERVING, actor=PRINCIPAL,
            target_subsystem=TARGET_SUBSYSTEM, requested_phase=LifecyclePhase.RUNTIME,
            metadata=admission_metadata))
        if (decision.outcome != AdmissionOutcome.ALLOW or decision.authority_class != AuthorityClass.MODEL_SERVING
                or decision.actor != PRINCIPAL or decision.action_kind != ACTION
                or decision.target_subsystem != TARGET_SUBSYSTEM or decision.correlation_id != correlation):
            raise ProductionServingError("model_serving_control_plane_not_allowed")
        admission_decision_record = _admission_decision_payload(self._kernel, decision)
        if (callable(getattr(self._kernel, "recorded_decision_payload", None))
                and (not isinstance(admission_decision_record, Mapping)
                    or admission_decision_record.get("admission_decision_ref")
                        != decision.admission_decision_ref
                    or admission_decision_record.get("correlation_id") != correlation
                    or admission_decision_record.get("outcome") != AdmissionOutcome.ALLOW.value)):
            raise ProductionServingError("model_serving_admission_record_unavailable")
        serving_attempt = _reserve_serving_operation_attempt(
            self._handle, operation_intent=operation_intent,
            admission_decision_ref=decision.admission_decision_ref)
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
                    or after["activation_history_digest"] != before["activation_history_digest"]
                    or after["catalog_proof"] != proof):
                raise ProductionServingError("activation_changed_during_load")
            resource_revalidation_decision_ref: str | None = None
            resource_revalidation_correlation: str | None = None
            resource_revalidation_decision_record: Mapping[str, Any] | None = None
            if admission_context_provider is not None:
                # The first resource admission authorizes beginning the exact
                # load. Game presence and host pressure can change while a GPU
                # model is loading, so require a fresh control-plane decision
                # before publishing the resident serving session.
                resource_revalidation_correlation = (
                    correlation + ":post-load-resource-revalidation")
                try:
                    post_load_context = admission_context_provider(
                        resource_revalidation_correlation, state)
                except Exception as exc:
                    raise ProductionServingError(
                        "model_serving_resource_revalidation_unavailable") from exc
                if not isinstance(post_load_context, Mapping):
                    raise ProductionServingError(
                        "model_serving_resource_revalidation_invalid")
                post_load_entitlement_binding = post_load_context.get(
                    "governed_inference_entitlement_binding")
                if ((resource_entitlement_binding is None)
                        != (post_load_entitlement_binding is None)
                        or (resource_entitlement_binding is not None
                            and not _same_serving_resource_entitlement(
                                resource_entitlement_binding,
                                post_load_entitlement_binding))):
                    raise ProductionServingError(
                        "model_serving_resource_entitlement_changed_during_load")
                post_load_metadata = {**dict(post_load_context), **operation_intent,
                    "correlation_id": resource_revalidation_correlation,
                    "resource_admission_phase": "post_load_revalidation",
                    "serving_operation_attempt_id": serving_attempt["attempt_id"],
                    "serving_operation_attempt_semantic_digest":
                        serving_attempt["attempt_semantic_digest"]}
                post_load_decision = self._kernel.admit(ControlActionRequest(
                    action_kind=ACTION, authority_class=AuthorityClass.MODEL_SERVING,
                    actor=PRINCIPAL, target_subsystem=TARGET_SUBSYSTEM,
                    requested_phase=LifecyclePhase.RUNTIME,
                    metadata=post_load_metadata))
                if (post_load_decision.outcome != AdmissionOutcome.ALLOW
                        or post_load_decision.authority_class != AuthorityClass.MODEL_SERVING
                        or post_load_decision.actor != PRINCIPAL
                        or post_load_decision.action_kind != ACTION
                        or post_load_decision.target_subsystem != TARGET_SUBSYSTEM
                        or post_load_decision.correlation_id
                            != resource_revalidation_correlation
                        or not isinstance(post_load_decision.admission_decision_ref, str)
                        or not post_load_decision.admission_decision_ref):
                    raise ProductionServingError(
                        "model_serving_resource_policy_changed_during_load")
                resource_revalidation_decision_ref = (
                    post_load_decision.admission_decision_ref)
                decision_payload = _admission_decision_payload(
                    self._kernel, post_load_decision)
                if (not isinstance(decision_payload, Mapping)
                        or decision_payload.get("admission_decision_ref")
                            != resource_revalidation_decision_ref
                        or decision_payload.get("correlation_id")
                            != resource_revalidation_correlation
                        or decision_payload.get("outcome") != AdmissionOutcome.ALLOW.value):
                    raise ProductionServingError(
                        "model_serving_resource_revalidation_record_unavailable")
                resource_revalidation_decision_record = dict(decision_payload)
            resource_revalidation_binding = (
                {"resource_admission_revalidation_decision_ref":
                    resource_revalidation_decision_ref,
                 "resource_admission_revalidation_correlation_id":
                    resource_revalidation_correlation,
                 "resource_admission_revalidation_decision":
                    dict(resource_revalidation_decision_record)}
                if resource_revalidation_decision_ref is not None
                and resource_revalidation_correlation is not None
                and resource_revalidation_decision_record is not None else {})
            binding = {**operation_intent,
                       "serving_operation_attempt_id": serving_attempt["attempt_id"],
                       "serving_operation_attempt_semantic_digest": serving_attempt["attempt_semantic_digest"],
                       "control_plane_correlation_id": correlation,
                       **resource_revalidation_binding,
                       "activation_state": state, "catalog_proof": proof,
                       "catalog_proof_semantic_digest": proof["proof_semantic_digest"],
                       "commissioning_receipt_id": state["commissioning_receipt_id"],
                       "commissioning_receipt_semantic_digest": state["commissioning_receipt_semantic_digest"],
                       **{k: state[k] for k in ("artifact_path", "artifact_sha256", "artifact_size_bytes", "route_id",
                                                "runtime_id", "interpreter_path", "load_configuration", "authority_map_digest")},
                       "observed_loaded_model_identity": observed,
                       "model_serving_admission_ref": decision.admission_decision_ref}
            if resource_entitlement_binding is not None:
                binding["governed_inference_entitlement_binding"] = dict(
                    resource_entitlement_binding)
                entitlement_observation_id = admission_context.get(
                    "resource_entitlement_observation_id")
                if (isinstance(entitlement_observation_id, str)
                        and entitlement_observation_id):
                    binding["resource_entitlement_observation_id"] = (
                        entitlement_observation_id)
            if admission_decision_record is not None:
                binding["model_serving_admission_decision_record"] = dict(
                    admission_decision_record)
                binding["resource_admission_evidence_schema"] = (
                    RESOURCE_ADMISSION_EVIDENCE_SCHEMA)
            session_id = "serving-session-" + semantic_digest(binding)[:24]
            session = ServingSession(session_id, MappingProxyType(binding))
            receipt = {"schema_version": RECEIPT_SCHEMA, "status": "serving_session_bound", **session.to_dict(),
                       "serving_operation_attempt_id": serving_attempt["attempt_id"],
                       "serving_operation_attempt_semantic_digest": serving_attempt["attempt_semantic_digest"],
                       "model_loaded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                       "control_plane_authority_class": AuthorityClass.MODEL_SERVING.value,
                       "admission_outcome": "allow", "model_loaded": True, "serving_session_bound": True,
                       "inference_performed": False, "local_model_inference_authority_granted": False,
                       "adjacent_authority_granted": False}
            if admission_context:
                receipt["resource_admission_context"] = dict(admission_context)
            receipt["receipt_id"] = "serving-receipt-" + semantic_digest(receipt)[:24]
            receipt["receipt_semantic_digest"] = semantic_digest(receipt)
            # The persistent receipt cannot contain its own identity in its
            # session binding; expose the verified reference only to the live
            # opaque session after its canonical identity is fixed.
            session = ServingSession(session_id, MappingProxyType({
                **binding,
                "serving_receipt_id": receipt["receipt_id"],
                "serving_receipt_semantic_digest": receipt["receipt_semantic_digest"],
            }))
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
        with self._lifecycle_lock:
            self._invalidate_locked(reason)

    def _invalidate_locked(self, reason: str) -> None:
        session, model = self._session, self._model
        if model is not None:
            # Keep the exact serving references until shutdown succeeds. If a
            # worker refuses to close, its owner must retain the handle so a
            # governed caller can report the failed release and retry it.
            model.close()
            worker = getattr(model, "_process", None)
            poll = getattr(worker, "poll", None)
            if callable(poll) and poll() is None:
                raise ProductionServingError("exact_runtime_worker_exit_unconfirmed")
        self._session = self._model = None
        if session is None:
            return
        self._last_released_session_id = session.session_id
        invalidation = {"schema_version": INVALIDATION_SCHEMA, "session_id": session.session_id,
                        "serving_operation_id": session.binding["serving_operation_id"],
                        "prior_status": session.status, "status": "non_current_unloaded", "reason": reason}
        invalidation["invalidation_id"] = "serving-invalidation-" + semantic_digest(invalidation)[:24]
        invalidation["invalidation_semantic_digest"] = semantic_digest(invalidation)
        _create(self._handle, f"local-model/serving/invalidations/{invalidation['invalidation_id']}.json", invalidation)
        self._session = replace(session, status="non_current_unloaded")
        self._session = None

    def _owns_resource_release_admission(self, decision: object,
            expected: ServingSession) -> bool:
        if (type(decision) is not ControlActionDecision
                or not decision.allowed
                or decision.authority_class != AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE
                or decision.action_kind != "local_model_resource_release"
                or decision.actor not in self._RESOURCE_RELEASE_ACTORS
                or decision.target_subsystem != "production_chat"
                or decision.current_phase != LifecyclePhase.RUNTIME
                or decision.requested_phase != LifecyclePhase.RUNTIME
                or not isinstance(decision.correlation_id, str)
                or not decision.correlation_id or len(decision.correlation_id) > 256):
            return False
        owns = getattr(self._kernel, "owns_recorded_admitted_decision", None)
        payload_getter = getattr(self._kernel, "recorded_decision_payload", None)
        if not callable(owns) or not callable(payload_getter):
            return False
        try:
            if not owns(decision):
                return False
            payload = payload_getter(decision)
        except Exception:
            return False
        base_valid = (isinstance(payload, Mapping)
            and payload.get("event_type") == "control_plane_decision"
            and payload.get("outcome") == AdmissionOutcome.ALLOW.value
            and payload.get("authority_class") ==
                AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE.value
            and payload.get("action_kind") == "local_model_resource_release"
            and payload.get("actor") == decision.actor
            and payload.get("target_subsystem") == "production_chat"
            and payload.get("current_phase") == LifecyclePhase.RUNTIME.value
            and payload.get("requested_phase") == LifecyclePhase.RUNTIME.value
            and payload.get("correlation_id") == decision.correlation_id
            and payload.get("admission_decision_ref") == decision.admission_decision_ref)
        if not base_valid:
            return False
        delegated = payload.get("delegated_outcomes")
        governor = delegated.get("runtime_governor") if isinstance(delegated, Mapping) else None
        evidence_refs = governor.get("evidence_refs") if isinstance(governor, Mapping) else None
        target = (evidence_refs.get("resource_release_target")
            if isinstance(evidence_refs, Mapping) else None)
        identity = expected.binding.get("observed_loaded_model_identity")
        return (isinstance(target, Mapping)
            and set(target) == {"schema_version", "serving_session_id",
                "model_identity_digest"}
            and target.get("schema_version") ==
                "sentientos.production_chat_resource_release_target:v1"
            and target.get("serving_session_id") == expected.session_id
            and isinstance(identity, Mapping)
            and target.get("model_identity_digest") == digest_payload(dict(identity)))

    def release_current_session_after_resource_admission(
            self, expected: ServingSession, *, reason: str,
            admission_decision: ControlActionDecision | None = None,
            require_verified_game_clearance_for_recovery: bool = False,
            game_clearance_evidence: Mapping[str, Any] | None = None) -> bool:
        """Close this exact serving worker only for this kernel-owned release admission."""
        if not self._owns_resource_release_admission(admission_decision, expected):
            raise ProductionServingError("resource_release_admission_not_owned")
        with self._lifecycle_lock:
            if self._session != expected or self._model is None:
                # A concurrent, already admitted release can win this race.
                # Confirm that exact session was invalidated; a replacement
                # session stays a distinct live effect and is never reported
                # as closed here.
                return (self._session is None and self._model is None
                    and expected.session_id == self._last_released_session_id)
            if require_verified_game_clearance_for_recovery:
                if (admission_decision.actor != "production_chat_game_resource_governor"
                        or not isinstance(game_clearance_evidence, Mapping)
                        or any(not isinstance(game_clearance_evidence.get(key), str)
                            or not game_clearance_evidence.get(key)
                            for key in ("source_id", "generation_id", "observed_at"))):
                    raise ProductionServingError(
                        "game_resource_recovery_evidence_required")
                hold_id, marker = self._write_game_recovery_hold(
                    expected, admission_decision, game_clearance_evidence)
                self._pending_game_recovery_holds[hold_id] = marker
                self._resource_recovery_pending = True
                self._resource_recovery_requires_game_clearance = True
                self._resource_recovery_game_clearance_after = {
                    "source_id": game_clearance_evidence["source_id"],
                    "generation_id": game_clearance_evidence["generation_id"],
                    "observed_at": game_clearance_evidence["observed_at"],
                }
            self._invalidate_locked(reason)
            released = self._session is None and self._model is None
            if released and self._admission_context_provider is not None:
                self._resource_recovery_pending = True
                self._resource_recovery_requires_game_clearance = bool(
                    require_verified_game_clearance_for_recovery)
                self._resource_recovery_game_clearance_after = (
                    {key: str(game_clearance_evidence[key]) for key in (
                        "source_id", "generation_id", "observed_at")}
                    if require_verified_game_clearance_for_recovery
                        and isinstance(game_clearance_evidence, Mapping)
                        and all(isinstance(game_clearance_evidence.get(key), str)
                            and game_clearance_evidence.get(key) for key in (
                                "source_id", "generation_id", "observed_at"))
                    else None)
            return released

    def close(self) -> None:
        with self._lifecycle_lock:
            self._invalidate_locked("controller_closed")
            self._resource_recovery_pending = False
            self._resource_recovery_requires_game_clearance = False
            self._resource_recovery_game_clearance_after = None
            self._admission_context_provider = None
            self._resource_recovery_activation_digest = None
