"""Hardened, selection-only production local-model activation.

This module deliberately has no dependency on any model implementation.  Activation
publishes authenticated installation state; it never loads, serves, or invokes it.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionRequest, ControlPlaneKernel, LifecyclePhase
from .installation_state import InstallationStateError, InstallationStateHandle
from .local_model_catalog_consumer_custody import construct_authoritative_catalog_consumer_proof
from .local_model_production_commissioning_authority import verify_hardened_receipt
from .local_runtime_provisioning import semantic_digest

INTENT_SCHEMA = "sentientos.local_model_activation_intent:v1"
APPROVAL_SCHEMA = "sentientos.local_model_activation_approval:v1"
STATE_SCHEMA = "sentientos.local_model_activation_state:v2"
RECEIPT_SCHEMA = "sentientos.local_model_activation_receipt:v1"
TRANSACTION_SCHEMA = "sentientos.local_model_activation_transaction:v1"
FINALIZATION_SCHEMA = "sentientos.local_model_activation_finalization:v1"
PRINCIPAL = "deterministic_local_model_activation_controller"
CAPABILITY = "local_model_production_activation"
ACTION = "activate_exact_local_model_state"
TARGET_SUBSYSTEM = "local_model_chat"
ABSENT = "ABSENT"
EFFECTS = (
    "exact_operator_approval_evidence_read", "exact_authoritative_deployed_catalog_proof_read",
    "exact_hardened_local_model_commissioning_receipt_read", "exact_commissioned_artifact_identity_read",
    "exact_activation_intent_read", "exact_current_activation_state_read",
    "authoritative_active_model_compare_and_swap", "local_model_activation_receipt_write",
)
_PLACEHOLDERS = frozenset({"", "*", "anonymous", "default", "sample", "test", "placeholder",
                           "current", "latest", "any", "wildcard"})


class ProductionActivationError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _json(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionActivationError(code) from exc
    if not isinstance(value, dict):
        raise ProductionActivationError(code)
    return value


def _payload(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n").encode()


def _validate_envelope(value: Mapping[str, Any], digest_key: str, code: str) -> None:
    body = dict(value)
    claimed = body.pop(digest_key, None)
    if claimed != semantic_digest(body):
        raise ProductionActivationError(code)


def effect_set_digest() -> str:
    return str(semantic_digest({"effects": sorted(EFFECTS)}))


def activation_custody(handle: InstallationStateHandle) -> dict[str, str]:
    if not isinstance(handle, InstallationStateHandle):
        raise ProductionActivationError("authenticated_installation_handle_required")
    return {
        "activation_custody_identity": f"installation-local-model-activation:{handle.identity.value}",
        "activation_domain": "local-model/activation", "active_state_path": "local-model/activation/active.json",
        "transaction_directory": "local-model/activation/transactions",
        "receipt_directory": "local-model/activation/receipts",
    }


def _receipt(handle: InstallationStateHandle, receipt_id: str, *, allow_synthetic_for_tests: bool) -> dict[str, Any]:
    if (not receipt_id.startswith("commissioning-receipt-") or "/" in receipt_id
            or "\\" in receipt_id or receipt_id.casefold() in _PLACEHOLDERS):
        raise ProductionActivationError("commissioning_receipt_id_invalid")
    try:
        receipt = _json(handle.read_regular(handle.fixed_object(
            f"local-model/commissioning/receipts/{receipt_id}.json")), "commissioning_receipt_malformed")
    except (FileNotFoundError, InstallationStateError) as exc:
        raise ProductionActivationError("commissioning_receipt_not_in_canonical_custody") from exc
    if receipt.get("receipt_id") != receipt_id or not verify_hardened_receipt(
            receipt, allow_synthetic_for_tests=allow_synthetic_for_tests):
        raise ProductionActivationError("hardened_commissioning_receipt_v3_required")
    # Require the complete authority and no-escalation lineage, rather than merely its schema.
    required = ("commissioning_intent_id", "commissioning_intent_digest", "commissioning_plan_digest",
        "external_approval_evidence_id", "external_approval_semantic_digest", "hardened_acquisition_plan_digest",
        "hardened_acquisition_receipt_identity", "hardened_acquisition_receipt_digest",
        "model_commissioning_admission_ref", "smoke_local_model_inference_admission_ref", "smoke_receipt_digest",
        "observed_active_model_identity", "authority_map_digest", "load_configuration")
    if any(key not in receipt for key in required):
        raise ProductionActivationError("commissioning_lineage_incomplete")
    if (receipt.get("admission_outcome") != "allow" or receipt.get("control_plane_authority_class") != "model_commissioning"
            or receipt.get("model_left_loaded") is not False or receipt.get("activated") is not False
            or receipt.get("serving_authority_granted") is not False):
        raise ProductionActivationError("commissioning_lineage_invalid")
    return receipt


def _catalog(handle: InstallationStateHandle, receipt: Mapping[str, Any]) -> dict[str, Any]:
    proof = dict(construct_authoritative_catalog_consumer_proof(handle).proof)
    expected = {
        "installation_identity": receipt.get("installation_identity"),
        "custody_identity": receipt.get("catalog_custody_identity"),
        "authoritative_catalog_semantic_digest": receipt.get("current_authoritative_catalog_digest"),
        "proof_semantic_digest": receipt.get("current_authoritative_proof_digest"),
        "deployment_receipt_id": receipt.get("deployment_receipt_id"),
        "deployment_receipt_semantic_digest": receipt.get("deployment_receipt_semantic_digest"),
    }
    if any(proof.get(key) != value for key, value in expected.items()):
        raise ProductionActivationError("commissioning_catalog_provenance_stale")
    return proof


def _artifact(receipt: Mapping[str, Any]) -> dict[str, Any]:
    identity = receipt.get("observed_active_model_identity")
    if not isinstance(identity, Mapping):
        raise ProductionActivationError("commissioned_artifact_identity_missing")
    raw = (identity.get("resolved_artifact_path") or identity.get("model_path")
           or identity.get("path") or receipt.get("artifact_custody_path"))
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        raise ProductionActivationError("commissioned_artifact_path_invalid")
    path = Path(raw)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ProductionActivationError("commissioned_artifact_path_unsafe")
        resolved = path.resolve(strict=True)
        if resolved != path:
            raise ProductionActivationError("commissioned_artifact_path_unsafe")
        digest = hashlib.sha256()
        size = 0
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ProductionActivationError("commissioned_artifact_path_unsafe")
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block: break
                digest.update(block); size += len(block)
        finally: os.close(fd)
    except (OSError, RuntimeError) as exc:
        if isinstance(exc, ProductionActivationError): raise
        raise ProductionActivationError("commissioned_artifact_unavailable") from exc
    if digest.hexdigest() != receipt.get("artifact_sha256") or size != receipt.get("artifact_size_bytes"):
        raise ProductionActivationError("commissioned_artifact_stale")
    identity_path = identity.get("resolved_artifact_path") or identity.get("model_path") or identity.get("path")
    if identity_path is not None and identity_path != str(path):
        raise ProductionActivationError("commissioned_artifact_identity_mismatch")
    if (identity.get("model_content_sha256") not in {None, digest.hexdigest()}
            or identity.get("artifact_size_bytes") not in {None, size}):
        raise ProductionActivationError("commissioned_artifact_identity_mismatch")
    return {"artifact_path": str(path), "artifact_sha256": digest.hexdigest(), "artifact_size_bytes": size}


def _state_digest(state: Mapping[str, Any]) -> str:
    return str(state.get("state_semantic_digest", ""))


def _read_state(handle: InstallationStateHandle) -> dict[str, Any] | None:
    raw = handle.read_optional_regular(handle.fixed_object("local-model/activation/active.json"))
    if raw is None: return None
    state = _json(raw, "activation_state_malformed")
    if not verify_activation_state(state): raise ProductionActivationError("activation_state_invalid")
    return state


def verify_activation_state(state: Mapping[str, Any]) -> bool:
    body = {key: value for key, value in state.items()
            if key not in {"state_semantic_digest", "activation_intent_id", "activation_intent_semantic_digest"}}
    if state.get("state_semantic_digest") != semantic_digest(body): return False
    return (state.get("schema_version") == STATE_SCHEMA and state.get("status") == "commissioned_model_selected_active"
            and isinstance(state.get("generation"), int) and state["generation"] >= 1
            and state.get("model_loaded") is False and state.get("serving_started") is False
            and state.get("inference_performed") is False)


def _expected_prior(value: str) -> str:
    if value == ABSENT: return value
    if (not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            or value.casefold() in _PLACEHOLDERS):
        raise ProductionActivationError("exact_expected_prior_activation_state_required")
    return value


def prepare_activation_intent(installation_handle: InstallationStateHandle, *, commissioning_receipt_id: str,
        correlation_id: str, expected_prior_state: str, allow_synthetic_commissioning_for_tests: bool = False) -> Mapping[str, Any]:
    """Read current evidence and deterministically prepare an approval target; write nothing."""
    if not correlation_id or correlation_id.casefold() in _PLACEHOLDERS or "*" in correlation_id:
        raise ProductionActivationError("activation_correlation_id_invalid")
    expected_prior_state = _expected_prior(expected_prior_state)
    receipt = _receipt(installation_handle, commissioning_receipt_id,
                       allow_synthetic_for_tests=allow_synthetic_commissioning_for_tests)
    proof = _catalog(installation_handle, receipt)
    artifact = _artifact(receipt)
    current = _read_state(installation_handle)
    observed = ABSENT if current is None else _state_digest(current)
    if observed != expected_prior_state:
        raise ProductionActivationError("expected_prior_activation_state_mismatch")
    generation = 1 if current is None else int(current["generation"]) + 1
    custody = activation_custody(installation_handle)
    projection = {
        "schema_version": STATE_SCHEMA, "status": "commissioned_model_selected_active",
        "installation_identity": installation_handle.identity.value, **custody,
        "commissioning_receipt_id": receipt["receipt_id"],
        "commissioning_receipt_semantic_digest": receipt["receipt_semantic_digest"],
        "catalog_proof": proof, **artifact,
        **{key: receipt[key] for key in ("model_id", "artifact_id", "route_id", "runtime_id", "interpreter_path",
                                         "load_configuration", "authority_map_digest")},
        "generation": generation, "correlation_id": correlation_id,
        "model_loaded": False, "serving_started": False, "inference_performed": False,
    }
    intended_digest = semantic_digest(projection)
    value: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA, "target_principal": PRINCIPAL, "target_capability": CAPABILITY,
        "effects": sorted(EFFECTS), "effect_set_digest": effect_set_digest(), "correlation_id": correlation_id,
        "installation_identity": installation_handle.identity.value, **custody, "catalog_proof": proof,
        "deployment_receipt_id": proof["deployment_receipt_id"],
        "deployment_receipt_semantic_digest": proof["deployment_receipt_semantic_digest"],
        "commissioning_receipt_id": receipt["receipt_id"],
        "commissioning_receipt_semantic_digest": receipt["receipt_semantic_digest"], **artifact,
        **{key: receipt[key] for key in ("model_id", "artifact_id", "route_id", "runtime_id", "interpreter_path",
                                         "load_configuration", "authority_map_digest")},
        "expected_prior_activation_state": expected_prior_state, "generation": generation,
        "intended_state_projection": projection, "intended_state_digest": intended_digest,
        "model_load_performed": False, "serving_started": False, "inference_performed": False,
    }
    base = semantic_digest(value); value["intent_id"] = "activation-intent-" + base[:24]
    value["intent_semantic_digest"] = semantic_digest(value)
    return MappingProxyType(value)


def _time(value: object) -> datetime:
    try: parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError as exc: raise ProductionActivationError("activation_approval_time_invalid") from exc
    if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProductionActivationError("activation_approval_time_invalid")
    return parsed


def approval_bindings(intent: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("target_principal", "target_capability", "effects", "correlation_id", "intent_id",
        "intent_semantic_digest", "installation_identity", "activation_custody_identity", "catalog_proof",
        "deployment_receipt_id", "deployment_receipt_semantic_digest", "commissioning_receipt_id",
        "commissioning_receipt_semantic_digest", "model_id", "artifact_id", "artifact_path", "artifact_sha256",
        "artifact_size_bytes", "route_id", "runtime_id", "interpreter_path", "load_configuration",
        "authority_map_digest", "expected_prior_activation_state", "intended_state_digest")
    return {key: intent[key] for key in keys}


def verify_external_activation_approval(evidence: Mapping[str, Any], intent: Mapping[str, Any], *,
        observation_time: datetime, allow_synthetic_for_tests: bool = False, check_validity: bool = True) -> Mapping[str, Any]:
    if observation_time.tzinfo is None or observation_time.utcoffset() is None:
        raise ProductionActivationError("activation_approval_observation_time_invalid")
    value = dict(evidence); claimed = value.pop("approval_semantic_digest", None)
    if claimed != semantic_digest(value): raise ProductionActivationError("activation_approval_digest_invalid")
    value["approval_semantic_digest"] = claimed
    if value.get("schema_version") != APPROVAL_SCHEMA or value.get("approval_status") != "approved":
        raise ProductionActivationError("activation_approval_not_approved")
    for key in ("operator_identity", "approval_evidence_id", "evidence_source", "evidence_provenance"):
        item = str(value.get(key, "")).strip()
        if item.casefold() in _PLACEHOLDERS or "*" in item:
            raise ProductionActivationError("activation_approval_provenance_invalid")
    if value.get("synthetic_test_evidence") is not False and not allow_synthetic_for_tests:
        raise ProductionActivationError("synthetic_activation_approval_forbidden")
    if value.get("effects") != sorted(EFFECTS): raise ProductionActivationError("activation_approval_effects_mismatch")
    for key, expected in approval_bindings(intent).items():
        if value.get(key) != expected: raise ProductionActivationError(f"activation_approval_{key}_mismatch")
    not_before, approved, expires = (_time(value.get(k)) for k in ("not_before", "approval_timestamp", "expires_at"))
    if not_before > approved or approved > expires: raise ProductionActivationError("activation_approval_interval_invalid")
    if check_validity and observation_time < not_before: raise ProductionActivationError("activation_approval_not_yet_valid")
    if check_validity and observation_time > expires: raise ProductionActivationError("activation_approval_expired")
    return MappingProxyType(value)


def _control_metadata(intent: Mapping[str, Any], approval: Mapping[str, Any]) -> dict[str, Any]:
    return {"correlation_id": intent["correlation_id"], "activation_intent_id": intent["intent_id"],
        "activation_intent_digest": intent["intent_semantic_digest"], "activation_capability_id": CAPABILITY,
        "effect_set_digest": effect_set_digest(), "approval_evidence_id": approval["approval_evidence_id"],
        "approval_semantic_digest": approval["approval_semantic_digest"],
        "catalog_proof_digest": intent["catalog_proof"]["proof_semantic_digest"],
        "commissioning_receipt_id": intent["commissioning_receipt_id"],
        "commissioning_receipt_digest": intent["commissioning_receipt_semantic_digest"],
        "artifact_sha256": intent["artifact_sha256"], "artifact_size_bytes": intent["artifact_size_bytes"],
        "expected_prior_activation_state": intent["expected_prior_activation_state"],
        "intended_state_digest": intent["intended_state_digest"]}


def _ensure_custody(handle: InstallationStateHandle) -> None:
    for name in ("local-model", "local-model/activation", "local-model/activation/transactions",
                 "local-model/activation/receipts"):
        handle.ensure_directory(handle.fixed_object(name))


def _create_idempotent(handle: InstallationStateHandle, relative: str, value: Mapping[str, Any]) -> None:
    obj, data = handle.fixed_object(relative), _payload(value)
    try: handle.durable_create(obj, data)
    except InstallationStateError as exc:
        if exc.args != ("state_object_already_exists",) or handle.read_regular(obj) != data: raise


def _finalize(handle: InstallationStateHandle, tx: Mapping[str, Any], outcome: str,
              receipt: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"schema_version": FINALIZATION_SCHEMA, "transaction_id": tx["transaction_id"],
        "terminal_outcome": outcome, "intended_state_digest": tx["intended_state_digest"],
        "activation_receipt_id": receipt.get("receipt_id") if receipt else None,
        "activation_receipt_semantic_digest": receipt.get("receipt_semantic_digest") if receipt else None}
    value["finalization_semantic_digest"] = semantic_digest(value)
    _create_idempotent(handle, f"local-model/activation/transactions/{tx['transaction_id']}.final.json", value)
    return value


def _receipt_for(tx: Mapping[str, Any], intent: Mapping[str, Any], approval: Mapping[str, Any], decision: Any) -> dict[str, Any]:
    value: dict[str, Any] = {"schema_version": RECEIPT_SCHEMA, "status": "activation_state_transition_committed",
        "transaction_id": tx["transaction_id"], "transaction_semantic_digest": tx["transaction_semantic_digest"],
        "activation_intent_id": intent["intent_id"], "activation_intent_semantic_digest": intent["intent_semantic_digest"],
        "external_approval_evidence_id": approval["approval_evidence_id"],
        "external_approval_semantic_digest": approval["approval_semantic_digest"],
        "model_activation_admission_ref": decision.admission_decision_ref, "admission_outcome": decision.outcome.value,
        "control_plane_authority_class": decision.authority_class.value, "admitted_actor": decision.actor,
        "control_action_kind": decision.action_kind, "control_target_subsystem": decision.target_subsystem,
        "expected_prior_activation_state": intent["expected_prior_activation_state"],
        "observed_prior_activation_state": tx["observed_prior_activation_state"],
        "resulting_state_digest": intent["intended_state_digest"], "catalog_proof": intent["catalog_proof"],
        **{key: intent[key] for key in ("installation_identity", "activation_custody_identity",
            "commissioning_receipt_id", "commissioning_receipt_semantic_digest", "model_id", "artifact_id",
            "artifact_path", "artifact_sha256", "artifact_size_bytes", "route_id", "runtime_id", "interpreter_path")},
        "cas_result": "exact_prior_matched_and_replaced", "durable_publication_verified": True,
        "model_loaded": False, "serving_started": False, "inference_performed": False}
    base = semantic_digest(value); value["receipt_id"] = "activation-receipt-" + base[:24]
    value["receipt_semantic_digest"] = semantic_digest(value)
    return value


def activate_production(*, installation_handle: InstallationStateHandle, commissioning_receipt_id: str,
        approval_evidence: Mapping[str, Any], control_plane_kernel: ControlPlaneKernel, correlation_id: str,
        expected_prior_state: str, observation_time: datetime | None = None, clock: Callable[[], datetime] | None = None,
        allow_synthetic_evidence_for_tests: bool = False,
        crash_hook: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Execute one exact approved CAS.  All pre-admission failures are write-free."""
    now = clock or (lambda: datetime.now(timezone.utc))
    intent = prepare_activation_intent(installation_handle, commissioning_receipt_id=commissioning_receipt_id,
        correlation_id=correlation_id, expected_prior_state=expected_prior_state,
        allow_synthetic_commissioning_for_tests=allow_synthetic_evidence_for_tests)
    approval = verify_external_activation_approval(approval_evidence, intent, observation_time=observation_time or now(),
        allow_synthetic_for_tests=allow_synthetic_evidence_for_tests)
    metadata = _control_metadata(intent, approval)
    decision = control_plane_kernel.admit(ControlActionRequest(action_kind=ACTION,
        authority_class=AuthorityClass.MODEL_ACTIVATION, actor=PRINCIPAL, target_subsystem=TARGET_SUBSYSTEM,
        requested_phase=LifecyclePhase.RUNTIME, metadata=metadata))
    if (decision.outcome != AdmissionOutcome.ALLOW or decision.authority_class != AuthorityClass.MODEL_ACTIVATION
            or decision.actor != PRINCIPAL or decision.action_kind != ACTION or decision.target_subsystem != TARGET_SUBSYSTEM
            or decision.correlation_id != correlation_id):
        raise ProductionActivationError("model_activation_control_plane_not_allowed")
    _ensure_custody(installation_handle)
    with installation_handle.exclusive_lock(installation_handle.fixed_object("local-model/activation/activation.lock")):
        recover_activation_transactions(installation_handle,
            allow_synthetic_evidence_for_tests=allow_synthetic_evidence_for_tests)
        rebuilt = prepare_activation_intent(installation_handle, commissioning_receipt_id=commissioning_receipt_id,
            correlation_id=correlation_id, expected_prior_state=expected_prior_state,
            allow_synthetic_commissioning_for_tests=allow_synthetic_evidence_for_tests)
        if dict(rebuilt) != dict(intent): raise ProductionActivationError("activation_intent_no_longer_current")
        verify_external_activation_approval(approval, rebuilt, observation_time=now(),
            allow_synthetic_for_tests=allow_synthetic_evidence_for_tests)
        projection = dict(intent["intended_state_projection"])
        projection["activation_intent_id"] = intent["intent_id"]
        projection["activation_intent_semantic_digest"] = intent["intent_semantic_digest"]
        # The approved digest is over the acyclic projection; these references are publication metadata.
        projection["state_semantic_digest"] = semantic_digest({k: v for k, v in projection.items()
                                                                  if not k.startswith("activation_intent_")})
        if projection["state_semantic_digest"] != intent["intended_state_digest"]:
            raise ProductionActivationError("intended_state_projection_invalid")
        tx: dict[str, Any] = {"schema_version": TRANSACTION_SCHEMA,
            "activation_intent_id": intent["intent_id"], "activation_intent_semantic_digest": intent["intent_semantic_digest"],
            "expected_prior_activation_state": expected_prior_state, "observed_prior_activation_state": expected_prior_state,
            "intended_state_digest": intent["intended_state_digest"], "intended_state": projection,
            "intent": dict(intent), "approval": dict(approval),
            "admission": {"admission_decision_ref": decision.admission_decision_ref,
                "outcome": decision.outcome.value, "authority_class": decision.authority_class.value,
                "actor": decision.actor, "action_kind": decision.action_kind,
                "target_subsystem": decision.target_subsystem}}
        base = semantic_digest(tx); tx["transaction_id"] = "activation-transaction-" + base[:24]
        tx["transaction_semantic_digest"] = semantic_digest(tx)
        _create_idempotent(installation_handle, f"local-model/activation/transactions/{tx['transaction_id']}.json", tx)
        if crash_hook: crash_hook("after_transaction")
        installation_handle.durable_replace(installation_handle.fixed_object("local-model/activation/active.json"),
                                             _payload(projection))
        if crash_hook: crash_hook("after_active_state")
        receipt = _receipt_for(tx, intent, approval, decision)
        _create_idempotent(installation_handle, f"local-model/activation/receipts/{receipt['receipt_id']}.json", receipt)
        final = _finalize(installation_handle, tx, "committed", receipt)
        return {"status": "local_model_activation_committed", "active_state": projection,
                "activation_receipt": receipt, "finalization": final}


def recover_activation_transactions(handle: InstallationStateHandle, *,
        allow_synthetic_evidence_for_tests: bool = False) -> tuple[dict[str, Any], ...]:
    """Complete evidence for committed state, never roll an uncommitted transaction forward."""
    directory = handle.fixed_object("local-model/activation/transactions")
    try: names = handle.list_regular_names(directory)
    except (FileNotFoundError, InstallationStateError): return ()
    unresolved = [name for name in names if name.endswith(".json") and not name.endswith(".final.json")
                  and f"{name[:-5]}.final.json" not in names]
    if len(unresolved) > 1: raise ProductionActivationError("manual_recovery_required")
    results: list[dict[str, Any]] = []
    for name in unresolved:
        tx = _json(handle.read_regular(directory.child(name)), "activation_transaction_malformed")
        _validate_envelope(tx, "transaction_semantic_digest", "activation_transaction_invalid")
        if name != f"{tx.get('transaction_id')}.json": raise ProductionActivationError("activation_transaction_invalid")
        state = _read_state(handle)
        if state is None or _state_digest(state) != tx.get("intended_state_digest"):
            results.append(_finalize(handle, tx, "not_committed")); continue
        if dict(state) != tx.get("intended_state"): raise ProductionActivationError("manual_recovery_required")
        approval = tx.get("approval")
        intent, admission = tx.get("intent"), tx.get("admission")
        if not isinstance(approval, Mapping) or not isinstance(intent, Mapping) or not isinstance(admission, Mapping):
            raise ProductionActivationError("manual_recovery_required")
        # Expiry cannot invalidate completion; digest and immutable identity still must verify.
        verify_external_activation_approval(approval, intent, observation_time=_time(approval.get("approval_timestamp")),
            allow_synthetic_for_tests=allow_synthetic_evidence_for_tests, check_validity=False)
        decision = SimpleNamespace(admission_decision_ref=admission.get("admission_decision_ref"),
            outcome=SimpleNamespace(value=admission.get("outcome")),
            authority_class=SimpleNamespace(value=admission.get("authority_class")), actor=admission.get("actor"),
            action_kind=admission.get("action_kind"), target_subsystem=admission.get("target_subsystem"))
        receipt = _receipt_for(tx, intent, approval, decision)
        _create_idempotent(handle, f"local-model/activation/receipts/{receipt['receipt_id']}.json", receipt)
        results.append(_finalize(handle, tx, "committed_evidence_recovery", receipt))
    return tuple(results)


def verify_current_activation(handle: InstallationStateHandle, *,
        allow_synthetic_evidence_for_tests: bool = False) -> dict[str, Any]:
    """Read-only verification for a future separately governed loading boundary."""
    state = _read_state(handle)
    if state is None: raise ProductionActivationError("current_activation_absent")
    commissioning = _receipt(handle, str(state.get("commissioning_receipt_id")),
                              allow_synthetic_for_tests=allow_synthetic_evidence_for_tests)
    proof, artifact = _catalog(handle, commissioning), _artifact(commissioning)
    if state.get("catalog_proof") != proof or any(state.get(k) != v for k, v in artifact.items()):
        raise ProductionActivationError("current_activation_evidence_stale")
    receipts = handle.fixed_object("local-model/activation/receipts")
    witnesses: list[dict[str, Any]] = []
    for name in handle.list_regular_names(receipts):
        receipt = _json(handle.read_regular(receipts.child(name)), "activation_receipt_malformed")
        try: _validate_envelope(receipt, "receipt_semantic_digest", "activation_receipt_invalid")
        except ProductionActivationError: continue
        if (receipt.get("schema_version") == RECEIPT_SCHEMA and receipt.get("resulting_state_digest") == _state_digest(state)
                and name == f"{receipt.get('receipt_id')}.json"):
            final = _json(handle.read_regular(handle.fixed_object(
                f"local-model/activation/transactions/{receipt['transaction_id']}.final.json")),
                "activation_finalization_missing")
            _validate_envelope(final, "finalization_semantic_digest", "activation_finalization_invalid")
            if final.get("terminal_outcome") not in {"committed", "committed_evidence_recovery"}:
                raise ProductionActivationError("activation_finalization_invalid")
            witnesses.append(receipt)
    if len(witnesses) != 1: raise ProductionActivationError("current_activation_witness_invalid")
    return {"status": "current_local_model_activation_verified", "active_state": state,
            "activation_receipt": witnesses[0], "catalog_proof": proof,
            "model_loaded": False, "serving_started": False, "inference_performed": False}
