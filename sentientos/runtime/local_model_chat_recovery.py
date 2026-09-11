"""Explicit, externally approved recovery of one hardened local-model chat lifetime.

Recovery is deliberately not a supervisor policy.  This module consumes an immutable
operator request, independently asks for ``DAEMON_RESTART``, starts one fixed child,
and observes readiness without ever invoking inference.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos.control_plane_kernel import (AdmissionOutcome, AuthorityClass,
                                              ControlActionRequest, ControlPlaneKernel,
                                              LifecyclePhase)
from sentientos.installation_state import (InstallationIdentity, InstallationStateError,
                                           InstallationStateHandle, InstallationStateRegistry)
from sentientos.local_model_production_activation import (ProductionActivationError,
                                                          verify_current_activation)
from sentientos.local_model_production_serving import _operation_id
from sentientos.local_runtime_provisioning import semantic_digest

from .local_model_chat_service import SERVICE_ID, LocalModelChatServiceAdapter, LocalModelChatStartup
from .supervisor import RuntimeSupervisor, runtime_state_root

INTENT_SCHEMA = "sentientos.local_model_chat_recovery_intent:v1"
APPROVAL_SCHEMA = "sentientos.local_model_chat_recovery_approval:v1"
REQUEST_SCHEMA = "sentientos.local_model_chat_recovery_request:v1"
RECEIPT_SCHEMA = "sentientos.local_model_chat_recovery_receipt:v1"
SNAPSHOT_SCHEMA = "sentientos.local_model_chat_runtime_startup:v1"
PRINCIPAL = "deterministic_local_model_chat_recovery_controller"
ACTION = "restart_daemon"
ELIGIBLE_STATES = frozenset({"unhealthy", "failed"})
PLACEHOLDER_PROVENANCE = frozenset({"", "*", "any", "unknown", "placeholder", "test", "synthetic"})


class LocalModelChatRecoveryError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n").encode()


def _without(value: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in keys}


def startup_configuration_digest(config: LocalModelChatStartup) -> str:
    config.validate()
    return cast(str, semantic_digest({"service_id": SERVICE_ID,
                            "installation_identity": config.installation_identity,
                            "host": config.host, "port": config.port,
                            "restart_policy": "never"}))


def build_startup_snapshot(config: LocalModelChatStartup, supervisor_generation: str) -> dict[str, Any]:
    if not config.enabled or not config.installation_identity or not config.serving_operation_id:
        raise LocalModelChatRecoveryError("enabled_startup_required")
    body: dict[str, Any] = {"schema_version": SNAPSHOT_SCHEMA, "snapshot_version": 1,
        "runtime_supervisor_generation": supervisor_generation, "service_id": SERVICE_ID,
        "installation_identity": InstallationIdentity.parse(config.installation_identity).value,
        "serving_operation_id": _operation_id(config.serving_operation_id),
        "host": config.host, "port": config.port,
        "startup_configuration_digest": startup_configuration_digest(config),
        "restart_policy": "never"}
    body["snapshot_semantic_digest"] = semantic_digest(body)
    return body


def startup_snapshot_path(root: Path | None = None) -> Path:
    return (root or runtime_state_root()) / "local-model-chat-startup.json"


def write_startup_snapshot(snapshot: Mapping[str, Any], root: Path | None = None) -> None:
    path = startup_snapshot_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = _canonical(snapshot)
    temporary = path.with_name("." + path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(data); stream.flush()
        import os
        os.fsync(stream.fileno())
    temporary.replace(path)


def read_startup_snapshot(root: Path | None = None) -> dict[str, Any]:
    try:
        value = json.loads(startup_snapshot_path(root).read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise LocalModelChatRecoveryError("runtime_startup_snapshot_unavailable") from exc
    if (not isinstance(value, dict) or value.get("schema_version") != SNAPSHOT_SCHEMA
            or value.get("service_id") != SERVICE_ID or value.get("restart_policy") != "never"
            or value.get("snapshot_semantic_digest") != semantic_digest(_without(value, "snapshot_semantic_digest"))):
        raise LocalModelChatRecoveryError("runtime_startup_snapshot_invalid")
    return value


def _read_json(handle: InstallationStateHandle, relative: str, code: str) -> dict[str, Any]:
    try:
        value = json.loads(handle.read_regular(handle.fixed_object(relative)))
    except (OSError, ValueError, TypeError, InstallationStateError) as exc:
        raise LocalModelChatRecoveryError(code) from exc
    if not isinstance(value, dict):
        raise LocalModelChatRecoveryError(code)
    return value


def verified_serving_receipts(handle: InstallationStateHandle) -> tuple[dict[str, Any], ...]:
    directory = handle.fixed_object("local-model/serving/receipts")
    try:
        names = handle.list_regular_names(directory)
    except InstallationStateError as exc:
        raise LocalModelChatRecoveryError("serving_receipt_custody_unavailable") from exc
    receipts: list[dict[str, Any]] = []
    for name in names:
        if not name.endswith(".json"):
            raise LocalModelChatRecoveryError("serving_receipt_malformed")
        receipt = _read_json(handle, f"local-model/serving/receipts/{name}", "serving_receipt_malformed")
        digest = receipt.get("receipt_semantic_digest")
        if (receipt.get("schema_version") != "sentientos.local_model_serving_session_receipt:v1"
                or digest != semantic_digest(_without(receipt, "receipt_semantic_digest"))
                or receipt.get("control_plane_authority_class") != AuthorityClass.MODEL_SERVING.value
                or receipt.get("admission_outcome") != "allow" or receipt.get("model_loaded") is not True
                or receipt.get("serving_session_bound") is not True
                or receipt.get("inference_performed") is not False):
            raise LocalModelChatRecoveryError("serving_receipt_malformed")
        binding = receipt.get("binding")
        if not isinstance(binding, dict) or binding.get("installation_identity") != handle.identity.value:
            raise LocalModelChatRecoveryError("serving_receipt_installation_mismatch")
        receipts.append(receipt)
    return tuple(receipts)


def exact_prior_serving_receipt(handle: InstallationStateHandle, operation_id: str) -> dict[str, Any]:
    operation_id = _operation_id(operation_id)
    matches = [item for item in verified_serving_receipts(handle)
               if item["binding"].get("serving_operation_id") == operation_id]
    if not matches:
        raise LocalModelChatRecoveryError("prior_serving_receipt_missing")
    if len(matches) != 1:
        raise LocalModelChatRecoveryError("prior_serving_receipt_ambiguous")
    return matches[0]


def require_fresh_operation(handle: InstallationStateHandle, replacement: str, prior: str) -> str:
    replacement = _operation_id(replacement)
    if replacement == prior:
        raise LocalModelChatRecoveryError("replacement_serving_operation_not_fresh")
    if any(item["binding"].get("serving_operation_id") == replacement
           for item in verified_serving_receipts(handle)):
        raise LocalModelChatRecoveryError("replacement_serving_operation_reused")
    return replacement


def _activation_provenance(verified: Mapping[str, Any]) -> dict[str, Any]:
    state, receipt = verified["active_state"], verified["activation_receipt"]
    return {"activation_state_semantic_digest": state["state_semantic_digest"],
            "activation_generation": state["generation"],
            "activation_receipt_id": receipt["receipt_id"],
            "activation_receipt_semantic_digest": receipt["receipt_semantic_digest"],
            "model_id": state["model_id"], "artifact_id": state["artifact_id"],
            "runtime_id": state["runtime_id"], "authority_map_digest": state["authority_map_digest"]}


def build_recovery_intent(*, snapshot: Mapping[str, Any], prior_receipt: Mapping[str, Any],
                          activation: Mapping[str, Any], replacement_serving_operation_id: str,
                          recovery_correlation_id: str) -> dict[str, Any]:
    prior = str(snapshot["serving_operation_id"])
    replacement = _operation_id(replacement_serving_operation_id)
    if replacement == prior:
        raise LocalModelChatRecoveryError("replacement_serving_operation_not_fresh")
    if not recovery_correlation_id.strip() or recovery_correlation_id.lower() in PLACEHOLDER_PROVENANCE:
        raise LocalModelChatRecoveryError("recovery_correlation_id_invalid")
    provenance = _activation_provenance(activation)
    binding = prior_receipt.get("binding", {})
    if any(binding.get(key) != value for key, value in provenance.items()):
        raise LocalModelChatRecoveryError("prior_activation_provenance_mismatch")
    body: dict[str, Any] = {"schema_version": INTENT_SCHEMA,
        "installation_identity": snapshot["installation_identity"],
        "runtime_supervisor_generation": snapshot["runtime_supervisor_generation"],
        "service_id": SERVICE_ID, "startup_configuration_digest": snapshot["startup_configuration_digest"],
        "prior_serving_operation_id": prior, "prior_serving_session_id": prior_receipt["session_id"],
        "prior_serving_receipt_id": prior_receipt["receipt_id"],
        "prior_serving_receipt_semantic_digest": prior_receipt["receipt_semantic_digest"],
        **provenance, "replacement_serving_operation_id": replacement,
        "recovery_correlation_id": recovery_correlation_id,
        "intended_restart_target": SERVICE_ID, "recovery_inference": False}
    body["intent_id"] = "local-model-chat-recovery-intent-" + semantic_digest(body)[:24]
    body["intent_semantic_digest"] = semantic_digest(body)
    return body


def _current_activation(handle: InstallationStateHandle) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], verify_current_activation(handle))
    except ProductionActivationError as exc:
        raise LocalModelChatRecoveryError("current_activation_invalid:" + exc.code) from exc


def prepare_recovery_intent(*, installation_identity: str,
                            replacement_serving_operation_id: str,
                            recovery_correlation_id: str) -> dict[str, Any]:
    identity = InstallationIdentity.parse(installation_identity)
    snapshot = read_startup_snapshot()
    if snapshot.get("installation_identity") != identity.value:
        raise LocalModelChatRecoveryError("startup_installation_mismatch")
    supervisor = _read_runtime_supervisor_status()
    _require_eligible(supervisor, snapshot)
    handle = InstallationStateRegistry.system().open(identity)
    prior = exact_prior_serving_receipt(handle, str(snapshot["serving_operation_id"]))
    require_fresh_operation(handle, replacement_serving_operation_id, str(snapshot["serving_operation_id"]))
    return build_recovery_intent(snapshot=snapshot, prior_receipt=prior,
        activation=_current_activation(handle), replacement_serving_operation_id=replacement_serving_operation_id,
        recovery_correlation_id=recovery_correlation_id)


def _read_runtime_supervisor_status() -> dict[str, Any]:
    try:
        value = json.loads((runtime_state_root() / "supervisor-state.json").read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise LocalModelChatRecoveryError("runtime_supervisor_state_unavailable") from exc
    if not isinstance(value, dict):
        raise LocalModelChatRecoveryError("runtime_supervisor_state_invalid")
    # Persisted state and public status use different schema/shape; normalize it.
    if value.get("schema") == "sentientos.runtime_supervisor_state:v1":
        value = {**value, "state": "panic" if value.get("panic_latched") else "running",
                 "services": {key: {"state": state} for key, state in value.get("service_states", {}).items()}}
    return value


def _require_eligible(status: Mapping[str, Any], snapshot: Mapping[str, Any]) -> None:
    if status.get("panic_latched") or status.get("state") == "panic":
        raise LocalModelChatRecoveryError("runtime_panic_latched")
    if status.get("generation") != snapshot.get("runtime_supervisor_generation"):
        raise LocalModelChatRecoveryError("supervisor_generation_mismatch")
    services = status.get("services")
    service = services.get(SERVICE_ID) if isinstance(services, Mapping) else None
    state = service.get("state") if isinstance(service, Mapping) else None
    if state not in ELIGIBLE_STATES:
        raise LocalModelChatRecoveryError("service_not_eligible:" + str(state))


def verify_approval(approval: Mapping[str, Any], intent: Mapping[str, Any], *, now: float | None = None,
                    allow_synthetic_evidence_for_tests: bool = False) -> dict[str, Any]:
    value = dict(approval)
    if (intent.get("schema_version") != INTENT_SCHEMA
            or intent.get("intent_semantic_digest") != semantic_digest(_without(intent, "intent_semantic_digest"))):
        raise LocalModelChatRecoveryError("recovery_intent_semantic_digest_invalid")
    if value.get("schema_version") != APPROVAL_SCHEMA or value.get("approval_status") != "approved":
        raise LocalModelChatRecoveryError("recovery_approval_invalid")
    for field in ("evidence_source", "evidence_provenance"):
        item = value.get(field)
        if (not isinstance(item, str) or item.strip().lower() in PLACEHOLDER_PROVENANCE
                or "*" in item):
            raise LocalModelChatRecoveryError("recovery_approval_provenance_invalid")
    for field in ("operator_identity", "evidence_id"):
        item = value.get(field)
        if (not isinstance(item, str) or item.strip().lower() in PLACEHOLDER_PROVENANCE
                or "*" in item):
            raise LocalModelChatRecoveryError("recovery_approval_identity_invalid")
    synthetic = value.get("synthetic_test_evidence")
    if not isinstance(synthetic, bool) or (synthetic and not allow_synthetic_evidence_for_tests):
        raise LocalModelChatRecoveryError("synthetic_recovery_approval_forbidden")
    bindings = {"intent_id": "intent_id", "intent_semantic_digest": "intent_semantic_digest",
        "installation_identity": "installation_identity", "runtime_supervisor_generation": "runtime_supervisor_generation",
        "prior_serving_operation_id": "prior_serving_operation_id",
        "replacement_serving_operation_id": "replacement_serving_operation_id",
        "expected_activation_state_digest": "activation_state_semantic_digest",
        "recovery_correlation_id": "recovery_correlation_id"}
    if any(value.get(approval_key) != intent.get(intent_key) for approval_key, intent_key in bindings.items()):
        raise LocalModelChatRecoveryError("recovery_approval_intent_mismatch")
    if value.get("approval_semantic_digest") != semantic_digest(_without(value, "approval_semantic_digest")):
        raise LocalModelChatRecoveryError("recovery_approval_semantic_digest_invalid")
    instant = datetime.fromtimestamp(now, timezone.utc) if now is not None else datetime.now(timezone.utc)
    try:
        parsed = [datetime.fromisoformat(str(value[key]).replace("Z", "+00:00"))
                  for key in ("not_before", "approved_at", "expires_at")]
    except (KeyError, ValueError, TypeError) as exc:
        raise LocalModelChatRecoveryError("recovery_approval_time_invalid") from exc
    if any(item.tzinfo is None or item.utcoffset() is None for item in parsed):
        raise LocalModelChatRecoveryError("recovery_approval_time_invalid")
    not_before, approved, expires = parsed
    if not_before > approved or approved > expires:
        raise LocalModelChatRecoveryError("recovery_approval_interval_invalid")
    if instant < not_before:
        raise LocalModelChatRecoveryError("recovery_approval_not_yet_valid")
    if instant > expires:
        raise LocalModelChatRecoveryError("recovery_approval_expired")
    return value


def publish_recovery_request(*, installation_identity: str, approval: Mapping[str, Any]) -> dict[str, Any]:
    intent = prepare_recovery_intent(installation_identity=installation_identity,
        replacement_serving_operation_id=str(approval.get("replacement_serving_operation_id", "")),
        recovery_correlation_id=str(approval.get("recovery_correlation_id", "")))
    verified = verify_approval(approval, intent)
    body: dict[str, Any] = {"schema_version": REQUEST_SCHEMA, "intent": intent, "approval": verified,
                            "inference_performed": False}
    body["request_id"] = "local-model-chat-recovery-request-" + semantic_digest(body)[:24]
    body["request_semantic_digest"] = semantic_digest(body)
    handle = InstallationStateRegistry.system().open(InstallationIdentity.parse(installation_identity))
    directory = handle.fixed_object("local-model/recovery/requests"); handle.ensure_directory(directory)
    try:
        handle.durable_create(directory.child(body["request_id"] + ".json"), _canonical(body))
    except InstallationStateError as exc:
        raise LocalModelChatRecoveryError("recovery_request_already_exists") from exc
    return body


class ProductionLocalModelChatRecoveryController:
    """Own exactly one-request-at-a-time recovery transaction for canonical chat."""

    def __init__(self, supervisor: RuntimeSupervisor, adapter: LocalModelChatServiceAdapter,
                 control_plane_kernel: ControlPlaneKernel, installation_handle: InstallationStateHandle,
                 *, readiness_timeout: float = 10.0, clock: Callable[[], float] = time.time,
                 sleeper: Callable[[float], None] = time.sleep,
                 allow_synthetic_evidence_for_tests: bool = False) -> None:
        if not isinstance(adapter, LocalModelChatServiceAdapter):
            raise LocalModelChatRecoveryError("hardened_local_model_chat_adapter_required")
        if not isinstance(installation_handle, InstallationStateHandle):
            raise LocalModelChatRecoveryError("authenticated_installation_handle_required")
        self._supervisor, self._adapter, self._kernel, self._handle = supervisor, adapter, control_plane_kernel, installation_handle
        self._timeout, self._clock, self._sleep = readiness_timeout, clock, sleeper
        self._allow_synthetic = allow_synthetic_evidence_for_tests
        self._requests = installation_handle.fixed_object("local-model/recovery/requests")
        self._receipts = installation_handle.fixed_object("local-model/recovery/receipts")
        self._lock = installation_handle.fixed_object("local-model/recovery/locks/controller.lock")
        for directory in (self._requests, self._receipts,
                          installation_handle.fixed_object("local-model/recovery/locks")):
            installation_handle.ensure_directory(directory)

    def process_pending(self) -> tuple[dict[str, Any], ...]:
        outcomes = []
        for name in self._handle.list_regular_names(self._requests):
            outcomes.append(self.process_request(name))
        return tuple(outcomes)

    def _existing_receipt(self, request_id: str) -> dict[str, Any] | None:
        existing = self._handle.read_optional_regular(self._receipts.child(request_id + ".json"))
        if existing is None:
            return None
        try:
            loaded = json.loads(existing)
        except (ValueError, TypeError) as exc:
            raise LocalModelChatRecoveryError("recovery_receipt_malformed") from exc
        if (not isinstance(loaded, dict) or loaded.get("schema_version") != RECEIPT_SCHEMA
                or loaded.get("request_id") != request_id
                or loaded.get("installation_identity") != self._handle.identity.value
                or loaded.get("receipt_semantic_digest")
                != semantic_digest(_without(loaded, "receipt_semantic_digest"))):
            raise LocalModelChatRecoveryError("recovery_receipt_malformed")
        return loaded

    def process_request(self, name: str) -> dict[str, Any]:
        request_id = name[:-5] if name.endswith(".json") else name
        loaded = self._existing_receipt(request_id)
        if loaded is not None:
            return loaded
        with self._handle.exclusive_lock(self._lock):
            loaded = self._existing_receipt(request_id)
            if loaded is not None:
                return loaded
            attempted = completed = False; readiness = "not_observed"; decision_ref = None; outcome = "not_requested"
            try:
                request = _read_json(self._handle, f"local-model/recovery/requests/{name}", "recovery_request_malformed")
                if (request.get("schema_version") != REQUEST_SCHEMA
                        or request.get("request_id") != request_id
                        or request.get("request_semantic_digest") != semantic_digest(_without(request, "request_semantic_digest"))):
                    raise LocalModelChatRecoveryError("recovery_request_malformed")
                intent = request["intent"]; approval = verify_approval(request["approval"], intent,
                    now=self._clock(), allow_synthetic_evidence_for_tests=self._allow_synthetic)
                snapshot = read_startup_snapshot(self._supervisor.root)
                _require_eligible(self._supervisor.status(), snapshot)
                if intent.get("runtime_supervisor_generation") != self._supervisor.generation:
                    raise LocalModelChatRecoveryError("supervisor_generation_mismatch")
                if intent.get("startup_configuration_digest") != snapshot.get("startup_configuration_digest"):
                    raise LocalModelChatRecoveryError("startup_configuration_mismatch")
                if intent.get("prior_serving_operation_id") != snapshot.get("serving_operation_id"):
                    raise LocalModelChatRecoveryError("recovery_request_stale")
                prior = exact_prior_serving_receipt(self._handle, str(snapshot["serving_operation_id"]))
                replacement = require_fresh_operation(self._handle, str(intent["replacement_serving_operation_id"]),
                                                      str(snapshot["serving_operation_id"]))
                current = _current_activation(self._handle); provenance = _activation_provenance(current)
                reconstructed = build_recovery_intent(snapshot=snapshot, prior_receipt=prior,
                    activation=current, replacement_serving_operation_id=replacement,
                    recovery_correlation_id=str(intent["recovery_correlation_id"]))
                if reconstructed != intent:
                    raise LocalModelChatRecoveryError("recovery_intent_stale_or_mismatched")
                metadata = {"correlation_id": intent["recovery_correlation_id"], "subject": SERVICE_ID,
                    "recovery_scope": "local", "intent_id": intent["intent_id"],
                    "intent_semantic_digest": intent["intent_semantic_digest"],
                    "approval_id": approval["evidence_id"], "approval_semantic_digest": approval["approval_semantic_digest"],
                    "runtime_supervisor_generation": self._supervisor.generation,
                    "prior_serving_operation_id": intent["prior_serving_operation_id"],
                    "replacement_serving_operation_id": replacement,
                    "expected_activation_state_digest": provenance["activation_state_semantic_digest"]}
                decision = self._kernel.admit(ControlActionRequest(action_kind=ACTION,
                    authority_class=AuthorityClass.DAEMON_RESTART, actor=PRINCIPAL,
                    target_subsystem=SERVICE_ID, requested_phase=LifecyclePhase.RUNTIME, metadata=metadata))
                decision_ref, outcome = decision.admission_decision_ref, decision.outcome.value
                if (decision.outcome != AdmissionOutcome.ALLOW or decision.authority_class != AuthorityClass.DAEMON_RESTART
                        or decision.action_kind != ACTION or decision.actor != PRINCIPAL
                        or decision.target_subsystem != SERVICE_ID
                        or decision.correlation_id != intent["recovery_correlation_id"]):
                    raise LocalModelChatRecoveryError("daemon_restart_not_allowed:" + outcome)
                attempted = True
                self._adapter._restart_with_fresh_serving_operation(
                    replacement_serving_operation_id=replacement,
                    expected_activation_state_digest=provenance["activation_state_semantic_digest"])
                completed = True
                deadline = self._clock() + self._timeout
                while self._clock() <= deadline:
                    state = self._supervisor._observe_explicit_recovery(SERVICE_ID)
                    if state == "healthy" and self._adapter.health().reason == "serving_current":
                        readiness = "serving_current"; break
                    self._sleep(min(.1, max(0.0, deadline - self._clock())))
                if readiness != "serving_current":
                    self._adapter.force_stop()
                    raise LocalModelChatRecoveryError("post_restart_semantic_readiness_timeout")
                advanced = dict(snapshot); advanced["serving_operation_id"] = replacement
                advanced["snapshot_version"] = int(snapshot.get("snapshot_version", 1)) + 1
                advanced["snapshot_semantic_digest"] = semantic_digest(_without(advanced, "snapshot_semantic_digest"))
                write_startup_snapshot(advanced, self._supervisor.root)
                status, reason = "recovered", "serving_current"
            except Exception as exc:
                status, reason = "failed", exc.code if isinstance(exc, LocalModelChatRecoveryError) else type(exc).__name__
                intent = locals().get("intent", {})
                approval = locals().get("approval", {})
                prior = locals().get("prior", {})
            receipt: dict[str, Any] = {"schema_version": RECEIPT_SCHEMA, "request_id": request_id,
                "intent_id": intent.get("intent_id"), "intent_semantic_digest": intent.get("intent_semantic_digest"),
                "approval_id": approval.get("evidence_id"), "approval_semantic_digest": approval.get("approval_semantic_digest"),
                "installation_identity": self._handle.identity.value, "runtime_supervisor_generation": self._supervisor.generation,
                "service_id": SERVICE_ID, "prior_serving_operation_id": intent.get("prior_serving_operation_id"),
                "replacement_serving_operation_id": intent.get("replacement_serving_operation_id"),
                "expected_activation_state_digest": intent.get("activation_state_semantic_digest"),
                "prior_serving_receipt_id": prior.get("receipt_id"),
                "prior_serving_receipt_semantic_digest": prior.get("receipt_semantic_digest"),
                "daemon_restart_decision_ref": decision_ref, "daemon_restart_outcome": outcome,
                "child_restart_attempted": attempted, "child_restart_completed": completed,
                "post_restart_semantic_readiness": readiness, "model_serving_granted_by_recovery": False,
                "inference_performed": False, "local_model_inference_authority_granted": False,
                "terminal_status": status, "terminal_reason": reason}
            receipt["receipt_semantic_digest"] = semantic_digest(receipt)
            self._handle.durable_create(self._receipts.child(request_id + ".json"), _canonical(receipt))
            return receipt
