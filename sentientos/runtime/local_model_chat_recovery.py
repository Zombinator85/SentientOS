"""Explicit, externally approved recovery of one hardened local-model chat lifetime.

Recovery is deliberately not a supervisor policy.  This module consumes an immutable
operator request, independently asks for ``DAEMON_RESTART``, starts one fixed child,
and observes readiness without ever invoking inference.
"""
from __future__ import annotations

import json
import os
import stat
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos.chat_process_generation import verify_stored_chat_process_handoff
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
PHASE_SCHEMA = "sentientos.local_model_chat_recovery_phase:v1"
MAX_PHASE_RECORD_BYTES = 262_144
MAX_PHASE_RECORDS = 256
MAX_SERVING_RECEIPTS = 256
MAX_SERVING_RECEIPT_BYTES = 262_144
SNAPSHOT_SCHEMA = "sentientos.local_model_chat_runtime_startup:v1"
MAX_STARTUP_SNAPSHOT_BYTES = 131_072
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


def build_startup_snapshot(config: LocalModelChatStartup, supervisor_generation: str, *,
                           runtime_handoff: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not config.enabled or not config.installation_identity or not config.serving_operation_id:
        raise LocalModelChatRecoveryError("enabled_startup_required")
    body: dict[str, Any] = {"schema_version": SNAPSHOT_SCHEMA, "snapshot_version": 1,
        "runtime_supervisor_generation": supervisor_generation, "service_id": SERVICE_ID,
        "installation_identity": InstallationIdentity.parse(config.installation_identity).value,
        "serving_operation_id": _operation_id(config.serving_operation_id),
        "host": config.host, "port": config.port,
        "startup_configuration_digest": startup_configuration_digest(config),
        "restart_policy": "never"}
    if runtime_handoff is not None:
        if not isinstance(runtime_handoff, Mapping):
            raise LocalModelChatRecoveryError("runtime_handoff_snapshot_invalid")
        body["chat_process_handoff"] = dict(runtime_handoff)
    body["snapshot_semantic_digest"] = semantic_digest(body)
    return body


def startup_snapshot_path(root: Path | None = None) -> Path:
    return (root or runtime_state_root()) / "local-model-chat-startup.json"


def _read_snapshot_bytes(path: Path) -> bytes:
    if os.name != "posix" or not all(hasattr(os, name) for name in (
            "O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC")):
        raise LocalModelChatRecoveryError("runtime_snapshot_platform_unsupported")
    parent_fd = -1
    descriptor = -1
    try:
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent_fd)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_STARTUP_SNAPSHOT_BYTES:
            raise LocalModelChatRecoveryError("runtime_startup_snapshot_size_or_type_invalid")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(16_384, MAX_STARTUP_SNAPSHOT_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_STARTUP_SNAPSHOT_BYTES:
                raise LocalModelChatRecoveryError("runtime_startup_snapshot_too_large")
        after = os.fstat(descriptor)
        raw = b"".join(chunks)
        if (len(raw) != before.st_size or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
            raise LocalModelChatRecoveryError("runtime_startup_snapshot_changed_during_read")
        return raw
    except LocalModelChatRecoveryError:
        raise
    except OSError as exc:
        raise LocalModelChatRecoveryError("runtime_startup_snapshot_unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_fd >= 0:
            os.close(parent_fd)


def write_startup_snapshot(snapshot: Mapping[str, Any], root: Path | None = None) -> None:
    if (not isinstance(snapshot, Mapping)
            or snapshot.get("snapshot_semantic_digest")
                != semantic_digest(_without(snapshot, "snapshot_semantic_digest"))):
        raise LocalModelChatRecoveryError("runtime_startup_snapshot_digest_invalid")
    path = startup_snapshot_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = _canonical(snapshot)
    if len(data) > MAX_STARTUP_SNAPSHOT_BYTES:
        raise LocalModelChatRecoveryError("runtime_startup_snapshot_too_large")
    if os.name != "posix" or not all(hasattr(os, name) for name in (
            "O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC")):
        raise LocalModelChatRecoveryError("runtime_snapshot_platform_unsupported")
    parent_fd = -1
    descriptor = -1
    temporary = "." + path.name + ".tmp-" + uuid.uuid4().hex
    published = False
    try:
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptor = os.open(temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=parent_fd)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("snapshot_write_incomplete")
            view = view[written:]
        os.fsync(descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise LocalModelChatRecoveryError("runtime_startup_snapshot_type_invalid")
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        published = True
        os.fsync(parent_fd)
        if _read_snapshot_bytes(path) != data:
            raise LocalModelChatRecoveryError("runtime_startup_snapshot_publication_mismatch")
    except LocalModelChatRecoveryError:
        raise
    except OSError as exc:
        raise LocalModelChatRecoveryError("runtime_startup_snapshot_publication_failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_fd >= 0:
            if not published:
                try:
                    os.unlink(temporary, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
            os.close(parent_fd)



def read_startup_snapshot(root: Path | None = None) -> dict[str, Any]:
    try:
        value = json.loads(_read_snapshot_bytes(startup_snapshot_path(root)))
    except LocalModelChatRecoveryError:
        raise
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


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


def verified_serving_receipts(handle: InstallationStateHandle) -> tuple[dict[str, Any], ...]:
    """Read a fixed, bounded set of immutable serving receipts without following links."""
    directory = handle.fixed_object("local-model/serving/receipts")
    try:
        names = handle.list_regular_names(directory, max_entries=MAX_SERVING_RECEIPTS)
    except InstallationStateError as exc:
        raise LocalModelChatRecoveryError("serving_receipt_custody_unavailable") from exc
    receipts: list[dict[str, Any]] = []
    for name in names:
        if not name.endswith(".json"):
            raise LocalModelChatRecoveryError("serving_receipt_malformed")
        try:
            raw = handle.read_regular_bounded(
                handle.fixed_object(f"local-model/serving/receipts/{name}"),
                max_bytes=MAX_SERVING_RECEIPT_BYTES)
            receipt = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except LocalModelChatRecoveryError:
            raise
        except (UnicodeError, ValueError, TypeError, RecursionError, InstallationStateError) as exc:
            raise LocalModelChatRecoveryError("serving_receipt_malformed") from exc
        digest = receipt.get("receipt_semantic_digest") if isinstance(receipt, dict) else None
        binding = receipt.get("binding") if isinstance(receipt, dict) else None
        if (not isinstance(receipt, dict) or raw != _canonical(receipt)
                or receipt.get("schema_version") != "sentientos.local_model_serving_session_receipt:v1"
                or not isinstance(receipt.get("receipt_id"), str)
                or receipt.get("receipt_id") != name[:-5]
                or receipt.get("receipt_id") != "serving-receipt-" + semantic_digest({
                    key: item for key, item in receipt.items()
                    if key not in {"receipt_id", "receipt_semantic_digest"}})[:24]
                or digest != semantic_digest(_without(receipt, "receipt_semantic_digest"))
                or receipt.get("control_plane_authority_class") != AuthorityClass.MODEL_SERVING.value
                or receipt.get("admission_outcome") != "allow" or receipt.get("model_loaded") is not True
                or receipt.get("serving_session_bound") is not True
                or receipt.get("inference_performed") is not False
                or not isinstance(binding, dict)
                or binding.get("installation_identity") != handle.identity.value
                or not isinstance(receipt.get("session_id"), str)
                or receipt.get("session_id") != "serving-session-" + semantic_digest(binding)[:24]):
            raise LocalModelChatRecoveryError("serving_receipt_malformed")
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
    prior_handoff = snapshot.get("chat_process_handoff")
    if prior_handoff is not None:
        if not isinstance(prior_handoff, Mapping):
            raise LocalModelChatRecoveryError("startup_process_handoff_invalid")
        body["prior_chat_process_handoff"] = dict(prior_handoff)
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
        self._phases = installation_handle.fixed_object("local-model/recovery/phases")
        self._lock = installation_handle.fixed_object("local-model/recovery/locks/controller.lock")
        for directory in (self._requests, self._receipts, self._phases,
                          installation_handle.fixed_object("local-model/recovery/phases/attempts"),
                          installation_handle.fixed_object("local-model/recovery/phases/readiness"),
                          installation_handle.fixed_object("local-model/recovery/phases/completed"),
                          installation_handle.fixed_object("local-model/recovery/locks")):
            installation_handle.ensure_directory(directory)

    def process_pending(self) -> tuple[dict[str, Any], ...]:
        outcomes = []
        for name in self._handle.list_regular_names(self._requests):
            outcomes.append(self.process_request(name))
        return tuple(outcomes)

    def _existing_receipt(self, request_id: str) -> dict[str, Any] | None:
        name = request_id + ".json"
        try:
            names = self._handle.list_regular_names(self._receipts, max_entries=MAX_PHASE_RECORDS)
        except InstallationStateError as exc:
            raise LocalModelChatRecoveryError("recovery_receipt_directory_invalid") from exc
        if name not in names:
            return None
        try:
            existing = self._handle.read_regular_bounded(
                self._receipts.child(name), max_bytes=MAX_PHASE_RECORD_BYTES)
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


    def _phase_path(self, phase: str, request_id: str):
        if phase not in {"attempts", "readiness", "completed"}:
            raise LocalModelChatRecoveryError("recovery_phase_invalid")
        directory = self._handle.fixed_object(f"local-model/recovery/phases/{phase}")
        return directory, directory.child(request_id + ".json")

    def _read_phase(self, phase: str, request_id: str) -> dict[str, Any] | None:
        directory, target = self._phase_path(phase, request_id)
        try:
            names = self._handle.list_regular_names(directory, max_entries=MAX_PHASE_RECORDS)
        except InstallationStateError as exc:
            raise LocalModelChatRecoveryError("recovery_phase_directory_invalid") from exc
        if request_id + ".json" not in names:
            return None
        try:
            raw = self._handle.read_regular_bounded(target, max_bytes=MAX_PHASE_RECORD_BYTES)
        except InstallationStateError as exc:
            raise LocalModelChatRecoveryError("recovery_phase_read_failed") from exc
        if len(raw) > MAX_PHASE_RECORD_BYTES:
            raise LocalModelChatRecoveryError("recovery_phase_too_large")
        try:
            value = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise LocalModelChatRecoveryError("recovery_phase_malformed") from exc
        if (not isinstance(value, dict) or value.get("schema_version") != PHASE_SCHEMA
                or value.get("phase") != phase or value.get("request_id") != request_id
                or value.get("installation_identity") != self._handle.identity.value
                or value.get("phase_semantic_digest")
                    != semantic_digest(_without(value, "phase_semantic_digest"))
                or raw != _canonical(value)):
            raise LocalModelChatRecoveryError("recovery_phase_malformed")
        return value

    def _publish_phase(self, phase: str, value: Mapping[str, Any]) -> dict[str, Any]:
        body = dict(value)
        body["schema_version"] = PHASE_SCHEMA
        body["phase"] = phase
        body["installation_identity"] = self._handle.identity.value
        body["phase_semantic_digest"] = semantic_digest(body)
        raw = _canonical(body)
        if len(raw) > MAX_PHASE_RECORD_BYTES:
            raise LocalModelChatRecoveryError("recovery_phase_too_large")
        directory, target = self._phase_path(phase, str(body.get("request_id", "")))
        try:
            names = self._handle.list_regular_names(directory, max_entries=MAX_PHASE_RECORDS)
        except InstallationStateError as exc:
            raise LocalModelChatRecoveryError("recovery_phase_directory_invalid") from exc
        name = str(body["request_id"]) + ".json"
        if name in names:
            existing = self._read_phase(phase, str(body["request_id"]))
            if existing is None or _canonical(existing) != raw:
                raise LocalModelChatRecoveryError("recovery_phase_identity_conflict")
            return existing
        if len(names) >= MAX_PHASE_RECORDS:
            raise LocalModelChatRecoveryError("recovery_phase_retention_limit_exceeded")
        try:
            self._handle.durable_create(target, raw)
        except InstallationStateError as exc:
            raise LocalModelChatRecoveryError("recovery_phase_publication_failed") from exc
        return body

    @staticmethod
    def _phase_time() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _phase_lineage(self, request_id: str) -> dict[str, Any]:
        attempt = self._read_phase("attempts", request_id)
        readiness = self._read_phase("readiness", request_id)
        completed = self._read_phase("completed", request_id)
        result: dict[str, Any] = {}
        if attempt is not None:
            result["attempt_phase_digest"] = attempt["phase_semantic_digest"]
            result["attempt_started_at"] = attempt["phase_observed_at"]
        if readiness is not None:
            result["readiness_phase_digest"] = readiness["phase_semantic_digest"]
            result["readiness_observed_at"] = readiness["readiness_observed_at"]
            if isinstance(readiness.get("successor_serving_receipt_id"), str):
                result["successor_serving_receipt_id"] = readiness["successor_serving_receipt_id"]
                result["successor_serving_receipt_semantic_digest"] = (
                    readiness["successor_serving_receipt_semantic_digest"])
                result["successor_serving_session_id"] = readiness["successor_serving_session_id"]
        if completed is not None:
            result["completion_phase_digest"] = completed["phase_semantic_digest"]
            result["snapshot_advanced_at"] = completed["snapshot_advanced_at"]
            result["advanced_snapshot_digest"] = completed["advanced_snapshot_digest"]
        return result

    def _verify_phase_handoff(self, value: object, *, required: bool) -> dict[str, Any] | None:
        if value is None and not required:
            return None
        if not isinstance(value, Mapping):
            raise LocalModelChatRecoveryError("recovery_phase_handoff_missing")
        if value.get("status") != "runtime_launcher_child_launch_and_source_bound":
            raise LocalModelChatRecoveryError("recovery_phase_handoff_status_invalid")
        try:
            verified = verify_stored_chat_process_handoff(
                handle=self._handle, handoff_id=str(value.get("handoff_id", "")),
                expected_digest=str(value.get("handoff_digest", "")))
        except Exception as exc:
            raise LocalModelChatRecoveryError("recovery_phase_handoff_invalid") from exc
        fields = ("handoff_id", "handoff_digest", "process_instance_id",
            "software_generation_digest", "process_id", "parent_process_id",
            "startup_timestamp", "source_generation_scope")
        if any(value.get(key) != verified.get(key) for key in fields):
            raise LocalModelChatRecoveryError("recovery_phase_handoff_mismatch")
        return dict(value)

    def _phase_receipt(self, request_id: str, request: Mapping[str, Any]) -> dict[str, Any] | None:
        attempt = self._read_phase("attempts", request_id)
        readiness = self._read_phase("readiness", request_id)
        completed = self._read_phase("completed", request_id)
        if attempt is None:
            if readiness is not None or completed is not None:
                raise LocalModelChatRecoveryError("recovery_phase_predecessor_missing")
            return None
        intent, approval = request.get("intent"), request.get("approval")
        if (not isinstance(intent, Mapping) or not isinstance(approval, Mapping)
                or intent.get("intent_semantic_digest")
                    != semantic_digest(_without(intent, "intent_semantic_digest"))):
            raise LocalModelChatRecoveryError("recovery_request_malformed")
        bound = (("request_id", request_id), ("intent_id", intent.get("intent_id")),
            ("intent_semantic_digest", intent.get("intent_semantic_digest")),
            ("approval_id", approval.get("evidence_id")),
            ("approval_semantic_digest", approval.get("approval_semantic_digest")),
            ("runtime_supervisor_generation", intent.get("runtime_supervisor_generation")),
            ("prior_serving_receipt_id", intent.get("prior_serving_receipt_id")),
            ("prior_serving_receipt_semantic_digest", intent.get("prior_serving_receipt_semantic_digest")))
        for phase in (attempt, readiness, completed):
            if phase is None:
                continue
            if any(phase.get(key) != value for key, value in bound):
                raise LocalModelChatRecoveryError("recovery_phase_request_binding_mismatch")
        try:
            attempt_time = datetime.fromisoformat(
                str(attempt.get("phase_observed_at", "")).replace("Z", "+00:00"))
            if attempt_time.tzinfo is None or attempt_time.utcoffset() is None:
                raise ValueError("recovery_phase_time_invalid")
            approval_checked_at = attempt.get("approval_checked_at")
            if type(approval_checked_at) not in (int, float):
                raise ValueError("recovery_phase_approval_time_missing")
            verify_approval(approval, intent, now=float(approval_checked_at),
                allow_synthetic_evidence_for_tests=self._allow_synthetic)
        except Exception as exc:
            raise LocalModelChatRecoveryError("recovery_phase_approval_invalid") from exc
        if (attempt.get("decision_outcome") != AdmissionOutcome.ALLOW.value
                or not isinstance(attempt.get("phase_observed_at"), str)
                or not isinstance(attempt.get("daemon_restart_decision_ref"), str)):
            raise LocalModelChatRecoveryError("recovery_phase_admission_mismatch")
        if readiness is not None:
            if (readiness.get("attempt_phase_digest") != attempt.get("phase_semantic_digest")
                    or readiness.get("post_restart_semantic_readiness") != "serving_current"
                    or not isinstance(readiness.get("successor_chat_process_handoff"), Mapping)):
                raise LocalModelChatRecoveryError("recovery_readiness_phase_invalid")
            serving_ids = (readiness.get("successor_serving_receipt_id"),
                readiness.get("successor_serving_receipt_semantic_digest"),
                readiness.get("successor_serving_session_id"))
            if any(value is not None for value in serving_ids) and (
                    not all(isinstance(value, str) and value for value in serving_ids)
                    or len(serving_ids[1]) != 64
                    or any(char not in "0123456789abcdef" for char in serving_ids[1])):
                raise LocalModelChatRecoveryError("recovery_readiness_serving_receipt_binding_invalid")
        if completed is not None:
            if (readiness is None
                    or completed.get("attempt_phase_digest") != attempt.get("phase_semantic_digest")
                    or completed.get("readiness_phase_digest") != readiness.get("phase_semantic_digest")
                    or not isinstance(completed.get("advanced_snapshot_digest"), str)):
                raise LocalModelChatRecoveryError("recovery_completion_phase_invalid")
        ready = readiness is not None
        complete = completed is not None
        intent_predecessor = intent.get("prior_chat_process_handoff")
        if attempt.get("predecessor_chat_process_handoff") != intent_predecessor:
            raise LocalModelChatRecoveryError("recovery_phase_predecessor_intent_mismatch")
        predecessor = self._verify_phase_handoff(
            attempt.get("predecessor_chat_process_handoff"), required=False)
        successor = self._verify_phase_handoff(
            readiness.get("successor_chat_process_handoff") if readiness is not None else None,
            required=readiness is not None)
        predecessor_operation = (
            predecessor.get("configured_serving_operation_id") if predecessor is not None else None)
        successor_operation = (
            successor.get("configured_serving_operation_id") if successor is not None else None)
        if (predecessor_operation is not None
                and predecessor_operation != intent.get("prior_serving_operation_id")):
            raise LocalModelChatRecoveryError("recovery_phase_predecessor_serving_operation_mismatch")
        if (successor_operation is not None
                and successor_operation != intent.get("replacement_serving_operation_id")):
            raise LocalModelChatRecoveryError("recovery_phase_successor_serving_operation_mismatch")
        predecessor_operation_posture = (
            "handoff_unavailable" if predecessor is None else
            "exact_handoff_launch_operation_binding" if predecessor_operation is not None else
            "legacy_handoff_operation_unknown")
        successor_operation_posture = (
            "handoff_unavailable" if successor is None else
            "exact_handoff_launch_operation_binding" if successor_operation is not None else
            "legacy_handoff_operation_unknown")
        if ready and predecessor is not None and successor is not None:
            successor_prior = successor.get("prior_snapshot_generation")
            if (not isinstance(successor_prior, Mapping)
                    or successor_prior.get("handoff") != predecessor):
                raise LocalModelChatRecoveryError("recovery_phase_successor_predecessor_mismatch")
        receipt: dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA, "request_id": request_id,
            "intent_id": intent.get("intent_id"),
            "intent_semantic_digest": intent.get("intent_semantic_digest"),
            "approval_id": approval.get("evidence_id"),
            "approval_semantic_digest": approval.get("approval_semantic_digest"),
            "installation_identity": self._handle.identity.value,
            "runtime_supervisor_generation": attempt.get("runtime_supervisor_generation"),
            "service_id": SERVICE_ID,
            "prior_serving_operation_id": intent.get("prior_serving_operation_id"),
            "replacement_serving_operation_id": intent.get("replacement_serving_operation_id"),
            "expected_activation_state_digest": intent.get("activation_state_semantic_digest"),
            "prior_serving_receipt_id": intent.get("prior_serving_receipt_id"),
            "prior_serving_receipt_semantic_digest": intent.get("prior_serving_receipt_semantic_digest"),
            "daemon_restart_decision_ref": attempt.get("daemon_restart_decision_ref"),
            "daemon_restart_outcome": attempt.get("decision_outcome"),
            "child_restart_attempted": True if ready else None,
            "child_restart_completed": True if ready else None,
            "post_restart_semantic_readiness": "serving_current" if ready else "not_durably_observed",
            "predecessor_chat_process_handoff": predecessor,
            "successor_chat_process_handoff": successor,
            "predecessor_serving_operation_binding_posture": predecessor_operation_posture,
            "successor_serving_operation_binding_posture": successor_operation_posture,
            "successor_configured_serving_operation_id": successor_operation,
            "chat_process_handoff_lineage_posture": readiness.get(
                "chat_process_handoff_lineage_posture", "unavailable") if readiness else "unavailable",
            "recovery_phase_lineage": self._phase_lineage(request_id),
            "successor_serving_receipt_id": readiness.get("successor_serving_receipt_id") if readiness else None,
            "successor_serving_receipt_semantic_digest": (
                readiness.get("successor_serving_receipt_semantic_digest") if readiness else None),
            "successor_serving_session_id": readiness.get("successor_serving_session_id") if readiness else None,
            "recovery_phase_reconstruction": (
                "durable_completion_phase" if complete else
                "readiness_observed_completion_unconfirmed" if ready else
                "attempt_started_terminal_outcome_unobserved"),
            "model_serving_granted_by_recovery": False,
            "inference_performed": False, "local_model_inference_authority_granted": False,
            "terminal_status": "recovered" if complete else "incomplete",
            "terminal_reason": (
                "serving_current_snapshot_advanced" if complete else
                "readiness_observed_snapshot_completion_unconfirmed" if ready else
                "recovery_interrupted_outcome_unobserved"),
        }
        receipt["receipt_semantic_digest"] = semantic_digest(receipt)
        try:
            self._handle.durable_create(
                self._receipts.child(request_id + ".json"), _canonical(receipt))
        except InstallationStateError as exc:
            raise LocalModelChatRecoveryError("recovery_receipt_publication_failed") from exc
        return receipt


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
            prior_chat_handoff: dict[str, Any] | None = None
            successor_chat_handoff: dict[str, Any] | None = None
            successor_serving_receipt: dict[str, Any] | None = None
            readiness_phase_record: dict[str, Any] | None = None
            handoff_lineage_posture = "unavailable"
            try:
                request = _read_json(self._handle, f"local-model/recovery/requests/{name}", "recovery_request_malformed")
                if (request.get("schema_version") != REQUEST_SCHEMA
                        or request.get("request_id") != request_id
                        or request.get("request_semantic_digest") != semantic_digest(_without(request, "request_semantic_digest"))):
                    raise LocalModelChatRecoveryError("recovery_request_malformed")
                phase_receipt = self._phase_receipt(request_id, request)
                if phase_receipt is not None:
                    return phase_receipt
                intent = request["intent"]
                approval_checked_at = self._clock()
                approval = verify_approval(request["approval"], intent,
                    now=approval_checked_at, allow_synthetic_evidence_for_tests=self._allow_synthetic)
                snapshot = read_startup_snapshot(self._supervisor.root)
                _require_eligible(self._supervisor.status(), snapshot)
                if intent.get("runtime_supervisor_generation") != self._supervisor.generation:
                    raise LocalModelChatRecoveryError("supervisor_generation_mismatch")
                if intent.get("startup_configuration_digest") != snapshot.get("startup_configuration_digest"):
                    raise LocalModelChatRecoveryError("startup_configuration_mismatch")
                if intent.get("prior_serving_operation_id") != snapshot.get("serving_operation_id"):
                    raise LocalModelChatRecoveryError("recovery_request_stale")
                prior = exact_prior_serving_receipt(self._handle, str(snapshot["serving_operation_id"]))
                snapshot_handoff = snapshot.get("chat_process_handoff")
                observed_handoff = self._adapter.current_runtime_handoff()
                if snapshot_handoff is not None:
                    if (not isinstance(snapshot_handoff, Mapping)
                            or not isinstance(observed_handoff, Mapping)
                            or dict(snapshot_handoff) != dict(observed_handoff)
                            or intent.get("prior_chat_process_handoff") != dict(snapshot_handoff)):
                        raise LocalModelChatRecoveryError("chat_process_predecessor_handoff_mismatch")
                    prior_chat_handoff = dict(observed_handoff)
                elif observed_handoff is not None or "prior_chat_process_handoff" in intent:
                    raise LocalModelChatRecoveryError("chat_process_predecessor_handoff_unbound")
                replacement = require_fresh_operation(self._handle, str(intent["replacement_serving_operation_id"]),
                                                      str(snapshot["serving_operation_id"]))
                current = _current_activation(self._handle); provenance = _activation_provenance(current)
                reconstructed = build_recovery_intent(snapshot=snapshot, prior_receipt=prior,
                    activation=current, replacement_serving_operation_id=replacement,
                    recovery_correlation_id=str(intent["recovery_correlation_id"]))
                if reconstructed != intent:
                    raise LocalModelChatRecoveryError("recovery_intent_stale_or_mismatched")
                self._adapter.bind_prior_startup_snapshot(snapshot)
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
                attempt_phase = self._publish_phase("attempts", {
                    "request_id": request_id,
                    "intent_id": intent["intent_id"],
                    "intent_semantic_digest": intent["intent_semantic_digest"],
                    "approval_id": approval["evidence_id"],
                    "approval_semantic_digest": approval["approval_semantic_digest"],
                    "runtime_supervisor_generation": self._supervisor.generation,
                    "prior_serving_receipt_id": prior.get("receipt_id"),
                    "prior_serving_receipt_semantic_digest": prior.get("receipt_semantic_digest"),
                    "daemon_restart_decision_ref": str(decision_ref or ""),
                    "decision_outcome": outcome,
                    "approval_checked_at": approval_checked_at,
                    "predecessor_chat_process_handoff": prior_chat_handoff,
                    "chat_process_handoff_lineage_posture": (
                        "predecessor_handoff_verified" if prior_chat_handoff is not None
                        else "predecessor_handoff_unavailable"),
                    "phase_observed_at": self._phase_time(),
                })
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
                successor_serving_receipt = exact_prior_serving_receipt(self._handle, replacement)
                serving_binding = successor_serving_receipt.get("binding")
                if (not isinstance(serving_binding, Mapping)
                        or serving_binding.get("serving_operation_id") != replacement
                        or not isinstance(successor_serving_receipt.get("receipt_id"), str)
                        or not isinstance(successor_serving_receipt.get("receipt_semantic_digest"), str)):
                    raise LocalModelChatRecoveryError("successor_serving_receipt_binding_invalid")
                observed_successor_handoff = self._adapter.current_runtime_handoff()
                if observed_successor_handoff is not None:
                    successor_chat_handoff = dict(observed_successor_handoff)
                if prior_chat_handoff is not None and successor_chat_handoff is not None:
                    if (prior_chat_handoff.get("handoff_id") == successor_chat_handoff.get("handoff_id")
                            or prior_chat_handoff.get("process_instance_id")
                                == successor_chat_handoff.get("process_instance_id")):
                        self._adapter.force_stop()
                        raise LocalModelChatRecoveryError("chat_process_successor_handoff_not_fresh")
                    handoff_lineage_posture = "verified_predecessor_successor_process_handoffs"
                elif successor_chat_handoff is not None:
                    handoff_lineage_posture = "successor_handoff_verified_predecessor_unavailable"
                readiness_phase_record = self._publish_phase("readiness", {
                    **{key: value for key, value in attempt_phase.items()
                       if key not in {"schema_version", "phase", "phase_semantic_digest"}},
                    "attempt_phase_digest": attempt_phase["phase_semantic_digest"],
                    "successor_chat_process_handoff": successor_chat_handoff,
                    "successor_serving_receipt_id": successor_serving_receipt["receipt_id"],
                    "successor_serving_receipt_semantic_digest": (
                        successor_serving_receipt["receipt_semantic_digest"]),
                    "successor_serving_session_id": successor_serving_receipt["session_id"],
                    "chat_process_handoff_lineage_posture": handoff_lineage_posture,
                    "post_restart_semantic_readiness": readiness,
                    "readiness_observed_at": self._phase_time(),
                })
                advanced = dict(snapshot); advanced["serving_operation_id"] = replacement
                if successor_chat_handoff is not None:
                    advanced["chat_process_handoff"] = successor_chat_handoff
                else:
                    advanced.pop("chat_process_handoff", None)
                advanced["snapshot_version"] = int(snapshot.get("snapshot_version", 1)) + 1
                advanced["snapshot_semantic_digest"] = semantic_digest(_without(advanced, "snapshot_semantic_digest"))
                write_startup_snapshot(advanced, self._supervisor.root)
                self._publish_phase("completed", {
                    **{key: value for key, value in readiness_phase_record.items()
                       if key not in {"schema_version", "phase", "phase_semantic_digest"}},
                    "readiness_phase_digest": readiness_phase_record["phase_semantic_digest"],
                    "advanced_snapshot_digest": advanced["snapshot_semantic_digest"],
                    "snapshot_advanced_at": self._phase_time(),
                })
                status, reason = "recovered", "serving_current"
            except Exception as exc:
                status, reason = "failed", exc.code if isinstance(exc, LocalModelChatRecoveryError) else type(exc).__name__
                intent = locals().get("intent", {})
                approval = locals().get("approval", {})
                prior = locals().get("prior", {})
            if status == "recovered":
                request_value = locals().get("request")
                if isinstance(request_value, Mapping):
                    phase_receipt = self._phase_receipt(request_id, request_value)
                    if phase_receipt is not None:
                        return phase_receipt
                raise LocalModelChatRecoveryError("recovery_completion_phase_missing")
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
                "post_restart_semantic_readiness": readiness,
                "predecessor_chat_process_handoff": prior_chat_handoff,
                "successor_chat_process_handoff": successor_chat_handoff,
                "chat_process_handoff_lineage_posture": handoff_lineage_posture,
                "recovery_phase_lineage": self._phase_lineage(request_id),
                "successor_serving_receipt_id": (
                    readiness_phase_record.get("successor_serving_receipt_id")
                    if readiness_phase_record else None),
                "successor_serving_receipt_semantic_digest": (
                    readiness_phase_record.get("successor_serving_receipt_semantic_digest")
                    if readiness_phase_record else None),
                "successor_serving_session_id": (
                    readiness_phase_record.get("successor_serving_session_id")
                    if readiness_phase_record else None),
                "model_serving_granted_by_recovery": False,
                "inference_performed": False, "local_model_inference_authority_granted": False,
                "terminal_status": status, "terminal_reason": reason}
            receipt["receipt_semantic_digest"] = semantic_digest(receipt)
            self._handle.durable_create(self._receipts.child(request_id + ".json"), _canonical(receipt))
            return receipt

def inspect_chat_recovery_phase_custody(handle: Any, *, max_records: int = MAX_PHASE_RECORDS
        ) -> tuple[dict[str, Any], ...]:
    """Read bounded recovery phase custody without restarting or reauthorizing."""
    if type(max_records) is not int or not 1 <= max_records <= MAX_PHASE_RECORDS:
        raise LocalModelChatRecoveryError("recovery_phase_observation_bound_invalid")
    total_bytes = 0

    def names(relative: str) -> tuple[str, ...]:
        try:
            value = tuple(handle.list_regular_names(relative, max_entries=max_records))
        except InstallationStateError as exc:
            if exc.code in {"state_directory_missing", "state_parent_missing"}:
                return ()
            raise LocalModelChatRecoveryError("recovery_phase_observation_directory_invalid") from exc
        if len(value) > max_records or any(not isinstance(item, str) or not item.endswith(".json")
                or len(item) > 180 or "/" in item for item in value):
            raise LocalModelChatRecoveryError("recovery_phase_observation_names_invalid")
        return value

    def read(relative: str, maximum: int = MAX_PHASE_RECORD_BYTES) -> dict[str, Any]:
        nonlocal total_bytes
        try:
            raw = handle.read_regular_bounded(relative, max_bytes=maximum)
        except InstallationStateError as exc:
            raise LocalModelChatRecoveryError("recovery_phase_observation_read_failed") from exc
        total_bytes += len(raw)
        if len(raw) > maximum or total_bytes > 16 * 1024 * 1024:
            raise LocalModelChatRecoveryError("recovery_phase_observation_retention_limit")
        try:
            value = json.loads(raw)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise LocalModelChatRecoveryError("recovery_phase_observation_json_invalid") from exc
        if not isinstance(value, dict) or raw != _canonical(value):
            raise LocalModelChatRecoveryError("recovery_phase_observation_canonical_invalid")
        return value

    phase_names = {phase: names("local-model/recovery/phases/" + phase)
        for phase in ("attempts", "readiness", "completed")}
    phases: dict[str, dict[str, dict[str, Any]]] = {phase: {} for phase in phase_names}
    for phase, entries in phase_names.items():
        for name in entries:
            request_id = name[:-5]
            value = read("local-model/recovery/phases/" + phase + "/" + name)
            if (value.get("schema_version") != PHASE_SCHEMA or value.get("phase") != phase
                    or value.get("request_id") != request_id
                    or value.get("installation_identity") != handle.identity.value
                    or value.get("phase_semantic_digest")
                        != semantic_digest(_without(value, "phase_semantic_digest"))):
                raise LocalModelChatRecoveryError("recovery_phase_observation_phase_invalid")
            phases[phase][request_id] = value
    attempts, readiness_rows, completion_rows = (
        phases["attempts"], phases["readiness"], phases["completed"])
    if (set(readiness_rows) - set(attempts) or set(completion_rows) - set(attempts)):
        raise LocalModelChatRecoveryError("recovery_phase_observation_predecessor_missing")
    request_names = set(names("local-model/recovery/requests"))
    receipt_names = set(names("local-model/recovery/receipts"))
    serving_receipt_names = set(names("local-model/serving/receipts"))
    rows = []

    for request_id in sorted(attempts)[-max_records:]:
        attempt = attempts[request_id]
        readiness = readiness_rows.get(request_id)
        completed = completion_rows.get(request_id)
        filename = request_id + ".json"
        if filename not in request_names:
            raise LocalModelChatRecoveryError("recovery_phase_observation_request_missing")
        request = read("local-model/recovery/requests/" + filename)
        if (request.get("schema_version") != REQUEST_SCHEMA or request.get("request_id") != request_id
                or request.get("request_semantic_digest")
                    != semantic_digest(_without(request, "request_semantic_digest"))):
            raise LocalModelChatRecoveryError("recovery_phase_observation_request_invalid")
        intent, approval = request.get("intent"), request.get("approval")
        if (not isinstance(intent, Mapping) or not isinstance(approval, Mapping)
                or intent.get("intent_semantic_digest")
                    != semantic_digest(_without(intent, "intent_semantic_digest"))):
            raise LocalModelChatRecoveryError("recovery_phase_observation_binding_invalid")
        bound = (("request_id", request_id), ("intent_id", intent.get("intent_id")),
            ("intent_semantic_digest", intent.get("intent_semantic_digest")),
            ("approval_id", approval.get("evidence_id")),
            ("approval_semantic_digest", approval.get("approval_semantic_digest")),
            ("runtime_supervisor_generation", intent.get("runtime_supervisor_generation")),
            ("prior_serving_receipt_id", intent.get("prior_serving_receipt_id")),
            ("prior_serving_receipt_semantic_digest", intent.get("prior_serving_receipt_semantic_digest")))
        for phase in (attempt, readiness, completed):
            if phase is not None and any(phase.get(key) != expected for key, expected in bound):
                raise LocalModelChatRecoveryError("recovery_phase_observation_binding_mismatch")
        try:
            checked = attempt.get("approval_checked_at")
            if type(checked) not in (int, float):
                raise ValueError("approval_check_time_missing")
            verify_approval(approval, intent, now=float(checked),
                allow_synthetic_evidence_for_tests=False)
            for event_time in (attempt.get("phase_observed_at"),
                    readiness.get("readiness_observed_at") if readiness else None,
                    completed.get("snapshot_advanced_at") if completed else None):
                if event_time is None:
                    continue
                parsed = datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError("phase_time_naive")
        except Exception as exc:
            raise LocalModelChatRecoveryError("recovery_phase_observation_approval_or_time_invalid") from exc
        if (attempt.get("decision_outcome") != AdmissionOutcome.ALLOW.value
                or not isinstance(attempt.get("daemon_restart_decision_ref"), str)
                or not attempt["daemon_restart_decision_ref"]):
            raise LocalModelChatRecoveryError("recovery_phase_observation_admission_claim_invalid")
        if readiness is not None and (
                readiness.get("attempt_phase_digest") != attempt.get("phase_semantic_digest")
                or readiness.get("post_restart_semantic_readiness") != "serving_current"
                or not isinstance(readiness.get("successor_chat_process_handoff"), Mapping)):
            raise LocalModelChatRecoveryError("recovery_phase_observation_readiness_invalid")
        if completed is not None and (
                readiness is None
                or completed.get("attempt_phase_digest") != attempt.get("phase_semantic_digest")
                or completed.get("readiness_phase_digest") != readiness.get("phase_semantic_digest")
                or not isinstance(completed.get("advanced_snapshot_digest"), str)):
            raise LocalModelChatRecoveryError("recovery_phase_observation_completion_invalid")

        successor_serving_id = readiness.get("successor_serving_receipt_id") if readiness else None
        successor_serving_digest = (
            readiness.get("successor_serving_receipt_semantic_digest") if readiness else None)
        successor_serving_session_id = readiness.get("successor_serving_session_id") if readiness else None
        if any(value is not None for value in (
                successor_serving_id, successor_serving_digest, successor_serving_session_id)):
            if not all(isinstance(value, str) and value for value in (
                    successor_serving_id, successor_serving_digest, successor_serving_session_id)):
                raise LocalModelChatRecoveryError("recovery_phase_observation_serving_binding_invalid")
            serving_name = str(successor_serving_id) + ".json"
            if serving_name not in serving_receipt_names:
                raise LocalModelChatRecoveryError("recovery_phase_observation_serving_receipt_missing")
            serving_receipt = read("local-model/serving/receipts/" + serving_name)
            serving_binding = serving_receipt.get("binding")
            if (serving_receipt.get("schema_version") != "sentientos.local_model_serving_session_receipt:v1"
                    or serving_receipt.get("receipt_id") != successor_serving_id
                    or serving_receipt.get("receipt_semantic_digest") != successor_serving_digest
                    or successor_serving_digest != semantic_digest(
                        _without(serving_receipt, "receipt_semantic_digest"))
                    or serving_receipt.get("session_id") != successor_serving_session_id
                    or serving_receipt.get("control_plane_authority_class") != AuthorityClass.MODEL_SERVING.value
                    or serving_receipt.get("admission_outcome") != AdmissionOutcome.ALLOW.value
                    or serving_receipt.get("model_loaded") is not True
                    or serving_receipt.get("serving_session_bound") is not True
                    or serving_receipt.get("inference_performed") is not False
                    or not isinstance(serving_binding, Mapping)
                    or serving_binding.get("installation_identity") != handle.identity.value
                    or serving_binding.get("serving_operation_id")
                        != intent.get("replacement_serving_operation_id")):
                raise LocalModelChatRecoveryError("recovery_phase_observation_serving_receipt_invalid")

        predecessor_value = attempt.get("predecessor_chat_process_handoff")
        if predecessor_value != intent.get("prior_chat_process_handoff"):
            raise LocalModelChatRecoveryError("recovery_phase_observation_predecessor_handoff_mismatch")

        def verify_handoff(value: object, required: bool) -> dict[str, Any] | None:
            if value is None and not required:
                return None
            if not isinstance(value, Mapping):
                raise LocalModelChatRecoveryError("recovery_phase_observation_handoff_missing")
            try:
                verified = verify_stored_chat_process_handoff(handle=handle,
                    handoff_id=str(value.get("handoff_id", "")),
                    expected_digest=str(value.get("handoff_digest", "")))
            except Exception as exc:
                raise LocalModelChatRecoveryError("recovery_phase_observation_handoff_invalid") from exc
            fields = ("handoff_id", "handoff_digest", "process_instance_id",
                "software_generation_digest", "process_id", "parent_process_id",
                "startup_timestamp", "source_generation_scope")
            if any(value.get(key) != verified.get(key) for key in fields):
                raise LocalModelChatRecoveryError("recovery_phase_observation_handoff_mismatch")
            return dict(value)

        predecessor = verify_handoff(predecessor_value, False)
        successor_value = readiness.get("successor_chat_process_handoff") if readiness else None
        successor = verify_handoff(successor_value, readiness is not None)
        predecessor_operation = (
            predecessor.get("configured_serving_operation_id") if predecessor is not None else None)
        successor_operation = (
            successor.get("configured_serving_operation_id") if successor is not None else None)
        if (predecessor_operation is not None
                and predecessor_operation != intent.get("prior_serving_operation_id")):
            raise LocalModelChatRecoveryError("recovery_phase_observation_predecessor_serving_operation_mismatch")
        if (successor_operation is not None
                and successor_operation != intent.get("replacement_serving_operation_id")):
            raise LocalModelChatRecoveryError("recovery_phase_observation_successor_serving_operation_mismatch")
        predecessor_operation_posture = (
            "handoff_unavailable" if predecessor is None else
            "exact_handoff_launch_operation_binding" if predecessor_operation is not None else
            "legacy_handoff_operation_unknown")
        successor_operation_posture = (
            "handoff_unavailable" if successor is None else
            "exact_handoff_launch_operation_binding" if successor_operation is not None else
            "legacy_handoff_operation_unknown")
        if predecessor is not None and successor is not None:
            prior_snapshot = successor.get("prior_snapshot_generation")
            if not isinstance(prior_snapshot, Mapping) or prior_snapshot.get("handoff") != predecessor:
                raise LocalModelChatRecoveryError("recovery_phase_observation_successor_predecessor_mismatch")

        receipt = None
        if filename in receipt_names:
            receipt = read("local-model/recovery/receipts/" + filename)
            if (receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("request_id") != request_id
                    or receipt.get("installation_identity") != handle.identity.value
                    or receipt.get("receipt_semantic_digest")
                        != semantic_digest(_without(receipt, "receipt_semantic_digest"))):
                raise LocalModelChatRecoveryError("recovery_phase_observation_terminal_receipt_invalid")
            expected_lineage: dict[str, Any] = {
                "attempt_phase_digest": attempt["phase_semantic_digest"],
                "attempt_started_at": attempt.get("phase_observed_at")}
            if readiness is not None:
                expected_lineage.update({"readiness_phase_digest": readiness["phase_semantic_digest"],
                    "readiness_observed_at": readiness.get("readiness_observed_at")})
                if isinstance(readiness.get("successor_serving_receipt_id"), str):
                    expected_lineage.update({
                        "successor_serving_receipt_id": readiness["successor_serving_receipt_id"],
                        "successor_serving_receipt_semantic_digest":
                            readiness["successor_serving_receipt_semantic_digest"],
                        "successor_serving_session_id": readiness["successor_serving_session_id"]})
            if completed is not None:
                expected_lineage.update({"completion_phase_digest": completed["phase_semantic_digest"],
                    "snapshot_advanced_at": completed.get("snapshot_advanced_at"),
                    "advanced_snapshot_digest": completed.get("advanced_snapshot_digest")})
            if receipt.get("recovery_phase_lineage") != expected_lineage:
                raise LocalModelChatRecoveryError("recovery_phase_observation_terminal_lineage_mismatch")
            if any(receipt.get(key) != expected for key, expected in bound):
                raise LocalModelChatRecoveryError("recovery_phase_observation_terminal_binding_mismatch")
            if (receipt.get("predecessor_chat_process_handoff") != predecessor
                    or receipt.get("successor_chat_process_handoff") != successor
                    or receipt.get("inference_performed") is not False
                    or receipt.get("local_model_inference_authority_granted") is not False
                    or receipt.get("successor_serving_receipt_id") != successor_serving_id
                    or receipt.get("successor_serving_receipt_semantic_digest") != successor_serving_digest
                    or receipt.get("successor_serving_session_id") != successor_serving_session_id):
                raise LocalModelChatRecoveryError("recovery_phase_observation_terminal_claim_mismatch")

        if completed is not None:
            posture = "completion_phase_terminal_receipt_present" if receipt else "completion_phase_terminal_receipt_missing"
        elif readiness is not None:
            posture = "readiness_phase_terminal_receipt_present" if receipt else "readiness_phase_without_completion"
        else:
            posture = "attempt_phase_terminal_receipt_present" if receipt else "attempt_phase_without_readiness"
        rows.append({
            "request_id": request_id, "request_semantic_digest": request.get("request_semantic_digest"),
            "intent_id": intent.get("intent_id"), "intent_semantic_digest": intent.get("intent_semantic_digest"),
            "approval_id": approval.get("evidence_id"), "approval_semantic_digest": approval.get("approval_semantic_digest"),
            "installation_identity": handle.identity.value,
            "runtime_supervisor_generation": attempt.get("runtime_supervisor_generation"),
            "prior_serving_operation_id": intent.get("prior_serving_operation_id"),
            "replacement_serving_operation_id": intent.get("replacement_serving_operation_id"),
            "prior_serving_receipt_id": attempt.get("prior_serving_receipt_id"),
            "prior_serving_receipt_semantic_digest": attempt.get("prior_serving_receipt_semantic_digest"),
            "successor_serving_receipt_id": successor_serving_id,
            "successor_serving_receipt_semantic_digest": successor_serving_digest,
            "successor_serving_session_id": successor_serving_session_id,
            "attempt_phase_digest": attempt.get("phase_semantic_digest"),
            "readiness_phase_digest": readiness.get("phase_semantic_digest") if readiness else None,
            "completion_phase_digest": completed.get("phase_semantic_digest") if completed else None,
            "attempt_started_at": attempt.get("phase_observed_at"),
            "readiness_observed_at": readiness.get("readiness_observed_at") if readiness else None,
            "snapshot_advanced_at": completed.get("snapshot_advanced_at") if completed else None,
            "advanced_snapshot_digest": completed.get("advanced_snapshot_digest") if completed else None,
            "decision_outcome_claimed": attempt.get("decision_outcome"),
            "decision_reference_claimed": attempt.get("daemon_restart_decision_ref"),
            "decision_posture": "phase_claim_not_reauthorized",
            "predecessor_chat_process_handoff": predecessor,
            "successor_chat_process_handoff": successor,
            "handoff_lineage_posture": readiness.get("chat_process_handoff_lineage_posture", "unavailable")
                if readiness else "unavailable",
            "terminal_receipt_digest": receipt.get("receipt_semantic_digest") if receipt else None,
            "terminal_status": receipt.get("terminal_status") if receipt else None,
            "successor_serving_receipt_posture": (
                "verified_historical_custody_and_operation_binding"
                    if successor_serving_id is not None
                    and successor_operation_posture == "exact_handoff_launch_operation_binding" else
                "verified_receipt_legacy_handoff_operation_unknown"
                    if successor_serving_id is not None else "legacy_or_missing"),
            "predecessor_serving_operation_binding_posture": predecessor_operation_posture,
            "successor_serving_operation_binding_posture": successor_operation_posture,
            "successor_configured_serving_operation_id": successor_operation,
            "phase_posture": posture,
            "phase_evidence_posture": "canonical_installation_custody_and_digest_chain_checked_not_independently_signed",
            "runtime_currentness": "historical_process_identity_not_reobserved_during_recovery",
            "effect_authority": False, "inference_performed": False,
        })
    return tuple(rows)
