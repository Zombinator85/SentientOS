"""Deterministic evidence consumer for production local-model commissioning.

This module does not issue operator approval.  It binds a pre-effect intent to
authenticated installation custody, consumes external approval, and projects the
exact request metadata used by the normal control-plane kernel.
"""
from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from sentientos.installation_state import InstallationStateHandle
from sentientos.local_model_catalog_consumer_custody import construct_authoritative_catalog_consumer_proof
from sentientos.local_runtime_provisioning import semantic_digest

INTENT_SCHEMA = "sentientos.local_model_commissioning_intent:v1"
APPROVAL_SCHEMA = "sentientos.local_model_commissioning_approval:v1"
COMPATIBILITY_SCHEMA = "sentientos.local_model_compatibility_receipt:v2"
PLAN_SCHEMA = "sentientos.local_model_commissioning_plan:v3"
RECEIPT_SCHEMA = "sentientos.local_model_commissioning_receipt:v3"
PRINCIPAL = "deterministic_local_model_commissioning_controller"
CAPABILITY = "local_model_production_commissioning"
ACTION = "commission_exact_local_model"
TARGET_SUBSYSTEM = "local_model_chat"
EFFECTS = (
    "exact_operator_approval_evidence_read",
    "exact_authoritative_deployed_catalog_proof_read",
    "exact_hardened_model_artifact_acquisition_receipt_read",
    "exact_commissioning_intent_read",
    "bounded_zero_generation_gguf_compatibility_construction",
    "bounded_exact_local_model_load",
    "bounded_commissioning_smoke_inference",
    "local_model_commissioning_receipt_write",
)
PLACEHOLDERS = frozenset({"", "*", "anonymous", "default", "sample", "test", "placeholder"})


class CommissioningAuthorityError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def effect_set_digest() -> str:
    return str(semantic_digest({"effects": sorted(EFFECTS)}))


def commissioning_custody(handle: InstallationStateHandle) -> dict[str, str]:
    if not isinstance(handle, InstallationStateHandle):
        raise CommissioningAuthorityError("authenticated_installation_handle_required")
    identity = f"installation-local-model-commissioning:{handle.identity.value}"
    return {
        "commissioning_output_custody_identity": identity,
        "commissioning_domain": "local-model/commissioning",
        "receipt_directory": "local-model/commissioning/receipts",
        "smoke_directory": "local-model/commissioning/smoke",
    }


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise CommissioningAuthorityError("commissioning_approval_time_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CommissioningAuthorityError("commissioning_approval_time_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CommissioningAuthorityError("commissioning_approval_time_invalid")
    return parsed


def current_proof(handle: InstallationStateHandle, acquisition_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the current proof only when it exactly matches acquisition provenance."""
    snapshot = construct_authoritative_catalog_consumer_proof(handle)
    proof = snapshot.proof
    expected = {
        "installation_identity": proof["installation_identity"],
        "catalog_custody_identity": proof["custody_identity"],
        "local_model_catalog_digest": proof["authoritative_catalog_semantic_digest"],
        "authoritative_catalog_proof_digest": proof["proof_semantic_digest"],
        "deployment_receipt_id": proof["deployment_receipt_id"],
        "deployment_receipt_semantic_digest": proof["deployment_receipt_semantic_digest"],
    }
    if any(acquisition_plan.get(key) != value for key, value in expected.items()):
        raise CommissioningAuthorityError("stale_acquisition_catalog_provenance")
    return dict(proof)


def build_intent(chain: Mapping[str, Any], handle: InstallationStateHandle, *, correlation_id: str) -> Mapping[str, Any]:
    """Build immutable governance intent before the first construction effect."""
    if not correlation_id or correlation_id.casefold() in PLACEHOLDERS or "*" in correlation_id:
        raise CommissioningAuthorityError("commissioning_correlation_id_invalid")
    evidence = chain.get("authoritative_evidence")
    if not isinstance(evidence, Mapping) or not isinstance(evidence.get("acquisition_plan"), Mapping):
        raise CommissioningAuthorityError("hardened_acquisition_evidence_required")
    plan = evidence["acquisition_plan"]
    receipt = evidence.get("acquisition_receipt")
    if not isinstance(receipt, Mapping) or receipt.get("schema_version") != "sentientos.local_model_artifact_acquisition_receipt:v2":
        raise CommissioningAuthorityError("hardened_acquisition_receipt_v2_required")
    from sentientos.local_model_artifact_acquisition import verify_acquisition_receipt
    if not verify_acquisition_receipt(receipt, plan):
        raise CommissioningAuthorityError("hardened_acquisition_receipt_invalid")
    proof = current_proof(handle, plan)
    custody = commissioning_custody(handle)
    load = {"engine": "llama_cpp", "n_ctx": 512, "n_gpu_layers": 0 if chain.get("backend_family") == "cpu" else 1,
            "offload_claim": "cpu_only" if chain.get("backend_family") == "cpu" else "conservative_accelerator_layer",
            "ambient_accelerator_detection": False}
    probe = {"mode": "bounded_model_construction_vocab_only", "semantic_generations": 0, "n_ctx": 64,
             "timeout_seconds": 60}
    smoke = {"prompt_id": "sentientos.local_model_commissioning_smoke:v1", "max_calls": 1,
             "max_input_chars": 128, "max_output_chars": 128, "max_new_tokens": 8, "timeout_seconds": 20}
    receipt_identity = str(receipt["receipt_semantic_digest"])
    value: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA, "target_principal": PRINCIPAL, "target_capability": CAPABILITY,
        "effects": sorted(EFFECTS), "effect_set_digest": effect_set_digest(), "correlation_id": correlation_id,
        "installation_identity": handle.identity.value, "catalog_custody_identity": proof["custody_identity"],
        "authoritative_catalog_semantic_digest": proof["authoritative_catalog_semantic_digest"],
        "authoritative_catalog_proof_digest": proof["proof_semantic_digest"],
        "deployment_receipt_id": proof["deployment_receipt_id"],
        "deployment_receipt_semantic_digest": proof["deployment_receipt_semantic_digest"],
        "hardened_acquisition_plan_digest": plan["acquisition_plan_digest"],
        "hardened_acquisition_receipt_identity": receipt_identity,
        "hardened_acquisition_receipt_digest": receipt_identity,
        "model_id": chain["model_id"], "artifact_id": chain["artifact_id"], "artifact_sha256": chain["artifact_sha256"],
        "artifact_size_bytes": chain["artifact_size_bytes"], "artifact_custody_path": chain["artifact_path"],
        "route_id": chain["route_id"], "engine": chain["engine"], "backend_family": chain["backend_family"],
        "runtime_id": chain["runtime_id"], "interpreter_path": chain["interpreter_path"],
        "compatibility_probe_contract": probe, "load_configuration": load, "smoke_contract": smoke,
        **custody, "receipt_destination_identity": f"{custody['commissioning_output_custody_identity']}:receipt",
        "activation_performed": False, "serving_authority_granted": False,
    }
    digest = str(semantic_digest(value)); value["intent_id"] = "commissioning-intent-" + digest[:24]
    value["intent_semantic_digest"] = semantic_digest(value)
    return MappingProxyType(value)


def expected_approval_bindings(intent: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("target_principal", "target_capability", "effects", "correlation_id", "intent_id",
            "intent_semantic_digest", "installation_identity", "catalog_custody_identity",
            "authoritative_catalog_proof_digest", "deployment_receipt_id", "deployment_receipt_semantic_digest",
            "hardened_acquisition_receipt_identity", "hardened_acquisition_receipt_digest", "model_id", "artifact_id",
            "route_id", "runtime_id", "artifact_sha256", "artifact_size_bytes", "compatibility_probe_contract",
            "load_configuration", "smoke_contract", "commissioning_output_custody_identity")
    return {key: intent.get(key) for key in keys}


def verify_external_approval(evidence: Mapping[str, Any], intent: Mapping[str, Any], *, observation_time: datetime,
                             allow_synthetic_for_tests: bool = False) -> Mapping[str, Any]:
    if observation_time.tzinfo is None or observation_time.utcoffset() is None:
        raise CommissioningAuthorityError("commissioning_approval_observation_time_invalid")
    value = dict(evidence); claimed = value.pop("approval_semantic_digest", None)
    if claimed != semantic_digest(value):
        raise CommissioningAuthorityError("commissioning_approval_digest_invalid")
    value["approval_semantic_digest"] = claimed
    if value.get("schema_version") != APPROVAL_SCHEMA or value.get("approval_status") != "approved":
        raise CommissioningAuthorityError("commissioning_approval_not_approved")
    operator = str(value.get("operator_identity", "")).strip().casefold()
    if operator in PLACEHOLDERS or "*" in operator:
        raise CommissioningAuthorityError("commissioning_approval_operator_invalid")
    if value.get("synthetic_test_evidence") is not False and not allow_synthetic_for_tests:
        raise CommissioningAuthorityError("synthetic_commissioning_approval_forbidden")
    effects = value.get("effects")
    if not isinstance(effects, list) or effects != sorted(EFFECTS) or len(effects) != len(set(map(str, effects))):
        raise CommissioningAuthorityError("commissioning_approval_effects_mismatch")
    for key, expected in expected_approval_bindings(intent).items():
        if value.get(key) != expected:
            raise CommissioningAuthorityError(f"commissioning_approval_{key}_mismatch")
    for key in ("approval_evidence_id", "evidence_source", "evidence_provenance"):
        observed = str(value.get(key, "")).strip()
        if observed.casefold() in PLACEHOLDERS or "*" in observed:
            raise CommissioningAuthorityError("commissioning_approval_provenance_invalid")
    not_before, expires, approved = (_time(value.get(k)) for k in ("not_before", "expires_at", "approval_timestamp"))
    if not_before > expires or not (not_before <= approved <= expires):
        raise CommissioningAuthorityError("commissioning_approval_interval_invalid")
    if observation_time < not_before: raise CommissioningAuthorityError("commissioning_approval_not_yet_valid")
    if observation_time > expires: raise CommissioningAuthorityError("commissioning_approval_expired")
    return MappingProxyType(value)


def child_smoke_correlation(parent: str, intent: Mapping[str, Any]) -> str:
    return f"{parent}:smoke:{str(intent['intent_semantic_digest'])[:24]}"


def control_plane_metadata(approval: Mapping[str, Any], intent: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("correlation_id", "intent_id", "intent_semantic_digest", "installation_identity",
            "catalog_custody_identity", "authoritative_catalog_proof_digest", "deployment_receipt_id",
            "deployment_receipt_semantic_digest", "hardened_acquisition_plan_digest",
            "hardened_acquisition_receipt_identity", "hardened_acquisition_receipt_digest", "model_id", "artifact_id",
            "artifact_sha256", "artifact_size_bytes", "route_id", "runtime_id", "interpreter_path",
            "commissioning_output_custody_identity")
    result = {key: intent[key] for key in keys}
    result.update({"commissioning_capability_id": CAPABILITY, "effect_set_digest": effect_set_digest(),
                   "approval_evidence_id": approval["approval_evidence_id"],
                   "approval_semantic_digest": approval["approval_semantic_digest"],
                   "compatibility_contract_digest": semantic_digest(intent["compatibility_probe_contract"]),
                   "load_configuration_digest": semantic_digest(intent["load_configuration"]),
                   "smoke_contract_digest": semantic_digest(intent["smoke_contract"]),
                   "approval_not_before": approval["not_before"], "approval_expires_at": approval["expires_at"]})
    return result


def verify_hardened_receipt(receipt: Mapping[str, Any], *, allow_synthetic_for_tests: bool = False) -> bool:
    value = dict(receipt); claimed = value.pop("receipt_semantic_digest", None)
    if receipt.get("schema_version") != RECEIPT_SCHEMA or claimed != semantic_digest(value): return False
    identity_payload = {key: item for key, item in receipt.items() if key not in {"receipt_id", "receipt_semantic_digest"}}
    if receipt.get("receipt_id") != "commissioning-receipt-" + str(semantic_digest(identity_payload))[:24]: return False
    if receipt.get("status") != "local_model_commissioned" or receipt.get("execution_principal") != PRINCIPAL: return False
    if receipt.get("commissioning_capability_id") != CAPABILITY or receipt.get("effect_set_digest") != effect_set_digest(): return False
    if receipt.get("admission_outcome") != "allow" or receipt.get("control_plane_authority_class") != "model_commissioning": return False
    if receipt.get("model_left_loaded") is not False or receipt.get("activated") is not False or receipt.get("serving_authority_granted") is not False: return False
    if receipt.get("synthetic_test_evidence") is not False and not allow_synthetic_for_tests: return False
    forbidden = ("provider_network", "tool", "memory", "action", "repository_mutation", "background_inference")
    return not any(bool(receipt.get(key)) for key in forbidden)
