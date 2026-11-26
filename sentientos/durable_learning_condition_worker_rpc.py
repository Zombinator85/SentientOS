"""Closed RPC envelope validation for durable-learning condition workers.

This module validates message shape and request correlation only. The caller
must obtain ``transport_process_start_nonce`` from its supervisor-owned process
and IPC observer; worker self-report is not process or filesystem attestation.
"""
from __future__ import annotations

import json
import hashlib
import re
from collections.abc import Mapping
from typing import Any


RPC_SCHEMA = "sentientos.durable_learning_condition_worker_rpc:v1"
CONDITIONS = frozenset({"relevant_experience_available",
    "relevant_experience_withheld"})
OPERATIONS = frozenset({"inspect_baseline",
    "probe_access_matrix",
    "inventory_profile_registry",
    "recover_acquisition_receipts", "prepare_consolidation_snapshot",
    "consolidate_branch",
    "reconstruct_strategy_projection", "inspect_delayed_probe_gate"})
# Protocol, task, and artifact digests in the durable-learning experiment are
# the bare lowercase hex returned by digest_payload().
_DIGEST = re.compile(r"[0-9a-f]{64}")
_PROTOCOL_ID = re.compile(r"devexp-durable-learning-protocol-[0-9a-f]{24}")
_NONCE = re.compile(r"[0-9a-f]{32}")
_MAX_WIRE_BYTES = 1_048_576

_REQUEST_FIELDS = frozenset({"schema_version", "message_type", "protocol_id",
    "protocol_digest", "condition", "request_id", "operation", "payload",
    "authority"})
_RESPONSE_FIELDS = frozenset({"schema_version", "message_type", "protocol_id",
    "protocol_digest", "condition", "request_id", "operation", "status",
    "result_digest", "result", "process_start_nonce", "authority"})
_PAYLOAD_FIELDS = {
    "inspect_baseline": frozenset({"expected_baseline_inventory_digest"}),
    "probe_access_matrix": frozenset({"probe_manifest_digest"}),
    "inventory_profile_registry": frozenset({"probe_manifest_digest",
        "expected_appcontainer_sid"}),
    "recover_acquisition_receipts": frozenset({"task_digests"}),
    "prepare_consolidation_snapshot": frozenset({
        "acquisition_receipt_digests"}),
    "consolidate_branch": frozenset({"acquisition_receipt_digests",
        "consolidation_policy_digest", "snapshot_digest",
        "baseline_history_state_digest", "baseline_record_refs",
        "source_fact_ids", "allowed_history_record_refs",
        "withhold_developmental_history"}),
    "reconstruct_strategy_projection": frozenset({
        "consolidation_receipt_digest", "answer_exclusion_audit_digest",
        "strategy_projection_policy_digest"}),
    "inspect_delayed_probe_gate": frozenset({"probe_task_digest",
        "strategy_projection_digest"}),
}


class ConditionWorkerRPCError(ValueError):
    """An RPC envelope failed its closed protocol check."""


class ConditionWorkerRPCDispatcher:
    """Dispatch only the registered operations to a worker-owned backend.

    Backend methods receive the validated request, including its stable request
    ID. Any method that can write state must journal that ID before effects and
    recover it idempotently after restart. The dispatcher never retries a call.
    """

    _METHODS = {
        "inspect_baseline": "inspect_baseline",
        "probe_access_matrix": "probe_access_matrix",
        "inventory_profile_registry": "inventory_profile_registry",
        "recover_acquisition_receipts": "recover_acquisition_receipts",
        "prepare_consolidation_snapshot": "prepare_consolidation_snapshot",
        "consolidate_branch": "consolidate_branch",
        "reconstruct_strategy_projection": "reconstruct_strategy_projection",
        "inspect_delayed_probe_gate": "inspect_delayed_probe_gate",
    }

    def __init__(self, *, protocol_id: str, protocol_digest: str,
            condition: str, process_start_nonce: str, backend: Any,
            allowed_operations: set[str] | frozenset[str]
            ) -> None:
        operations = (frozenset(allowed_operations)
            if isinstance(allowed_operations, (set, frozenset))
            else frozenset())
        if (not isinstance(protocol_id, str)
                or _PROTOCOL_ID.fullmatch(protocol_id) is None
                or not _require_digest(protocol_digest)
                or condition not in CONDITIONS
                or not isinstance(process_start_nonce, str)
                or _NONCE.fullmatch(process_start_nonce) is None
                or backend is None
                or not operations or not operations <= OPERATIONS
                or any(not callable(getattr(backend, self._METHODS[operation], None))
                    for operation in operations)):
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_dispatcher_binding_invalid")
        self._protocol_id = protocol_id
        self._protocol_digest = protocol_digest
        self._condition = condition
        self._process_start_nonce = process_start_nonce
        self._backend = backend
        self._allowed_operations = operations
        self._poisoned = False

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def allowed_operations(self) -> frozenset[str]:
        return self._allowed_operations

    @staticmethod
    def _result_digest(value: Any) -> str:
        if not isinstance(value, Mapping):
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_backend_result_invalid")
        try:
            raw = json.dumps(dict(value), ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":")).encode(
                    "utf-8", errors="strict")
        except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_backend_result_invalid") from exc
        if not raw or len(raw) > _MAX_WIRE_BYTES:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_backend_result_over_bound")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _failure_digest(code: str) -> str:
        return hashlib.sha256(
            ("sentientos.worker.failure:v1:" + code).encode("ascii")).hexdigest()

    def dispatch(self, raw_request: bytes) -> bytes:
        """Validate and dispatch one request with a bounded optional result."""
        if self._poisoned:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_dispatcher_poisoned")
        request = decode_condition_worker_rpc(raw_request)
        binding_matches = (request["protocol_id"] == self._protocol_id
            and request["protocol_digest"] == self._protocol_digest
            and request["condition"] == self._condition)
        status = "rejected"
        result_digest = self._failure_digest("request_binding_mismatch")
        result_payload = None
        operation_allowed = request["operation"] in self._allowed_operations
        if binding_matches and operation_allowed:
            method = getattr(self._backend,
                self._METHODS[request["operation"]])
            try:
                outcome = method(request)
                if (not isinstance(outcome, Mapping)
                        or set(outcome) != {"status", "result"}
                        or outcome.get("status") not in {"completed", "rejected"}
                        or not isinstance(outcome.get("result"), Mapping)):
                    raise ConditionWorkerRPCError(
                        "durable_learning_worker_rpc_backend_outcome_invalid")
                status = outcome["status"]
                result_digest = self._result_digest(outcome["result"])
                if ((request["operation"] == "inspect_baseline"
                        and status in {"completed", "rejected"})
                        or (request["operation"] ==
                            "inventory_profile_registry"
                            and status == "completed")
                    or (request["operation"] ==
                            "prepare_consolidation_snapshot"
                            and status == "completed")
                    or (request["operation"] ==
                            "recover_acquisition_receipts"
                            and status == "completed")):
                    result_payload = dict(outcome["result"])
            except Exception:
                # The operation may have durably started before the error.
                # Do not accept another request until recovery in a new worker.
                self._poisoned = True
                status = "failed"
                result_digest = self._failure_digest(
                    "backend_outcome_ambiguous")
        elif binding_matches and not operation_allowed:
            result_digest = self._failure_digest("request_operation_not_allowed")
        response = {"schema_version": RPC_SCHEMA,
            "message_type": "response",
            "protocol_id": request["protocol_id"],
            "protocol_digest": request["protocol_digest"],
            "condition": request["condition"],
            "request_id": request["request_id"],
            "operation": request["operation"],
            "status": status,
            "result_digest": result_digest,
            "result": result_payload,
            "process_start_nonce": self._process_start_nonce,
            "authority": False}
        return encode_condition_worker_rpc(response, request=request,
            transport_process_start_nonce=self._process_start_nonce)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ConditionWorkerRPCError(
        "durable_learning_worker_rpc_non_json_constant")


def _wire_limit(max_bytes: int) -> None:
    if type(max_bytes) is not int or not 1 <= max_bytes <= _MAX_WIRE_BYTES:
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_wire_limit_invalid")


def decode_condition_worker_rpc(raw: bytes, *,
        request: Mapping[str, Any] | None = None,
        transport_process_start_nonce: str | None = None,
        max_bytes: int = _MAX_WIRE_BYTES) -> dict[str, Any]:
    """Decode one bounded UTF-8 JSON message and validate its RPC envelope.

    Response decoding requires the corresponding request and the supervisor's
    observed process-start nonce. This function provides framing hygiene only;
    it does not authenticate the source process or IPC channel.
    """
    _wire_limit(max_bytes)
    if type(raw) is not bytes or not raw or len(raw) > max_bytes:
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_wire_size_invalid")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant)
    except ConditionWorkerRPCError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError,
            TypeError, ValueError) as exc:
        raise ConditionWorkerRPCError(
            "durable_learning_worker_rpc_wire_json_invalid") from exc
    if type(value) is not dict:
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_envelope_invalid")
    if value.get("message_type") == "request":
        if request is not None or transport_process_start_nonce is not None:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_request_context_unexpected")
        return verify_condition_worker_rpc_request(value)
    if value.get("message_type") == "response":
        if request is None or transport_process_start_nonce is None:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_response_context_required")
        verify_condition_worker_rpc_response(value, request=request,
            transport_process_start_nonce=transport_process_start_nonce)
        return dict(value)
    raise ConditionWorkerRPCError("durable_learning_worker_rpc_envelope_invalid")


def encode_condition_worker_rpc(value: Any, *,
        request: Mapping[str, Any] | None = None,
        transport_process_start_nonce: str | None = None,
        max_bytes: int = _MAX_WIRE_BYTES) -> bytes:
    """Encode one validated envelope as bounded compact UTF-8 JSON."""
    _wire_limit(max_bytes)
    if type(value) is not dict:
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_envelope_invalid")
    # All v1 envelope values outside the request payload are scalars. Detach
    # them before validation so serialization uses the validated snapshot.
    value = dict(value)
    if value.get("message_type") == "request":
        if request is not None or transport_process_start_nonce is not None:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_request_context_unexpected")
        value = verify_condition_worker_rpc_request(value)
    elif value.get("message_type") == "response":
        if request is None or transport_process_start_nonce is None:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_response_context_required")
        verify_condition_worker_rpc_response(value, request=request,
            transport_process_start_nonce=transport_process_start_nonce)
    else:
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_envelope_invalid")
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
            separators=(",", ":")).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ConditionWorkerRPCError(
            "durable_learning_worker_rpc_wire_encode_invalid") from exc
    if len(raw) > max_bytes:
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_wire_size_invalid")
    return raw


def _require_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _validate_request_payload(operation: str, payload: Any) -> dict[str, Any]:
    if type(payload) is not dict:
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_payload_invalid")
    if operation == "inspect_baseline":
        if (not set(payload) <= _PAYLOAD_FIELDS[operation]
                or (payload and set(payload) != _PAYLOAD_FIELDS[operation])):
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_payload_invalid")
        if payload and not _require_digest(
                payload.get("expected_baseline_inventory_digest")):
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_payload_invalid")
        return dict(payload)
    if set(payload) != _PAYLOAD_FIELDS[operation]:
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_payload_invalid")
    if operation == "recover_acquisition_receipts":
        values = payload.get("task_digests")
        if (not isinstance(values, list) or not 1 <= len(values) <= 256
                or any(not _require_digest(value) for value in values)
                or len(set(values)) != len(values)):
            raise ConditionWorkerRPCError("durable_learning_worker_rpc_payload_invalid")
        return {"task_digests": list(values)}
    if operation == "probe_access_matrix":
        value = payload.get("probe_manifest_digest")
        if not _require_digest(value):
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_payload_invalid")
        return {"probe_manifest_digest": value}
    if operation == "inventory_profile_registry":
        value = payload.get("probe_manifest_digest")
        sid = payload.get("expected_appcontainer_sid")
        if (not _require_digest(value) or not isinstance(sid, str)
                or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+", sid) is None):
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_payload_invalid")
        return {"probe_manifest_digest": value,
            "expected_appcontainer_sid": sid}
    if operation == "prepare_consolidation_snapshot":
        values = payload.get("acquisition_receipt_digests")
        if (not isinstance(values, list) or not 1 <= len(values) <= 512
                or any(not _require_digest(value) for value in values)
                or len(set(values)) != len(values)):
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_payload_invalid")
        return {"acquisition_receipt_digests": list(values)}
    if operation == "consolidate_branch":
        values = payload.get("acquisition_receipt_digests")
        baseline_refs = payload.get("baseline_record_refs")
        allowed_refs = payload.get("allowed_history_record_refs")
        fact_ids = payload.get("source_fact_ids")
        def valid_refs(refs: Any) -> bool:
            return (isinstance(refs, list) and len(refs) <= 512
                and all(isinstance(ref, Mapping)
                    and set(ref) == {"record_id", "record_digest"}
                    and isinstance(ref.get("record_id"), str)
                    and re.fullmatch(r"devrec-[0-9a-f]{24}",
                        ref["record_id"]) is not None
                    and isinstance(ref.get("record_digest"), str)
                    and re.fullmatch(r"sha256:[0-9a-f]{64}",
                        ref["record_digest"]) is not None
                    for ref in refs)
                and len({ref["record_id"] for ref in refs}) == len(refs))
        if (not isinstance(values, list) or not 1 <= len(values) <= 512
                or any(not _require_digest(value) for value in values)
                or len(set(values)) != len(values)
                or not _require_digest(payload.get("consolidation_policy_digest"))
                or not _require_digest(payload.get("snapshot_digest"))
                or not _require_digest(payload.get(
                    "baseline_history_state_digest"))
                or not valid_refs(baseline_refs)
                or not valid_refs(allowed_refs)
                or not isinstance(fact_ids, list) or not 1 <= len(fact_ids) <= 1024
                or any(not isinstance(value, str) or not value or len(value) > 256
                    for value in fact_ids)
                or len(set(fact_ids)) != len(fact_ids)
                or type(payload.get("withhold_developmental_history")) is not bool):
            raise ConditionWorkerRPCError("durable_learning_worker_rpc_payload_invalid")
        return {"acquisition_receipt_digests": list(values),
            "consolidation_policy_digest": payload["consolidation_policy_digest"],
            "snapshot_digest": payload["snapshot_digest"],
            "baseline_history_state_digest": payload[
                "baseline_history_state_digest"],
            "baseline_record_refs": [dict(row) for row in baseline_refs],
            "source_fact_ids": list(fact_ids),
            "allowed_history_record_refs": [dict(row) for row in allowed_refs],
            "withhold_developmental_history": payload[
                "withhold_developmental_history"]}
    if any(not _require_digest(value) for value in payload.values()):
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_payload_invalid")
    return dict(payload)


def verify_condition_worker_rpc_request(value: Any) -> dict[str, Any]:
    """Validate one closed supervisor-to-worker request envelope."""
    if (type(value) is not dict or set(value) != _REQUEST_FIELDS
            or value.get("schema_version") != RPC_SCHEMA
            or value.get("message_type") != "request"
            or not isinstance(value.get("protocol_id"), str)
            or _PROTOCOL_ID.fullmatch(value["protocol_id"]) is None
            or not _require_digest(value.get("protocol_digest"))
            or not isinstance(value.get("condition"), str)
            or value["condition"] not in CONDITIONS
            or not isinstance(value.get("request_id"), str)
            or _NONCE.fullmatch(value["request_id"]) is None
            or not isinstance(value.get("operation"), str)
            or value["operation"] not in OPERATIONS
            or value.get("authority") is not False):
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_request_invalid")
    payload = _validate_request_payload(value["operation"], value["payload"])
    return {**value, "payload": payload}


def verify_condition_worker_rpc_response(value: Any, *, request: Mapping[str, Any],
        transport_process_start_nonce: str) -> dict[str, Any]:
    """Bind a worker reply to its request and supervisor-observed process nonce.

    This check does not verify that the process has an AppContainer token, that
    its ACLs deny peer access, or that the IPC transport authenticated the
    process. The caller must establish those facts independently.
    """
    checked_request = verify_condition_worker_rpc_request(request)
    if (type(value) is not dict or set(value) != _RESPONSE_FIELDS
            or value.get("schema_version") != RPC_SCHEMA
            or value.get("message_type") != "response"
            or any(value.get(key) != checked_request.get(key) for key in (
                "protocol_id", "protocol_digest", "condition", "request_id",
                "operation"))
            or not isinstance(value.get("status"), str)
            or value["status"] not in {"completed", "rejected", "failed"}
            or not _require_digest(value.get("result_digest"))
            or (checked_request["operation"] not in {
                    "inspect_baseline", "inventory_profile_registry",
                    "recover_acquisition_receipts",
                    "prepare_consolidation_snapshot"}
                and value.get("result") is not None)
            or (checked_request["operation"] == "inspect_baseline"
                and value["status"] == "failed"
                and value.get("result") is not None)
            or not isinstance(transport_process_start_nonce, str)
            or _NONCE.fullmatch(transport_process_start_nonce) is None
            or value.get("process_start_nonce") != transport_process_start_nonce
            or value.get("authority") is not False):
        raise ConditionWorkerRPCError("durable_learning_worker_rpc_response_invalid")
    if checked_request["operation"] == "inspect_baseline":
        result = value.get("result")
        if value["status"] in {"completed", "rejected"}:
            expected_fields = {"schema_version", "protocol_id",
                "protocol_digest", "condition", "branch_id",
                "history_state_digest",
                "history_snapshot_matches_retained_state",
                "history_matches_protocol_baseline",
                "active_empty_session_verified", "branch_roots_disjoint",
                "branch_root_identity_digests",
                "operation_journal_inventory",
                "operation_journal_empty_verified", "authority"}
            inventory_v3 = (type(result) is dict and result.get(
                "schema_version") ==
                    "sentientos.durable_learning_worker_baseline_inventory:v3")
            inventory_v4 = (type(result) is dict and result.get(
                "schema_version") ==
                    "sentientos.durable_learning_worker_baseline_inventory:v4")
            if inventory_v3:
                expected_fields |= {"branch_root_access_matrix",
                    "branch_root_access_matrix_verified"}
            if inventory_v4:
                expected_fields |= {"history_probe_input_inventory",
                    "history_probe_inventory_matches_protocol"}
                if "branch_root_access_matrix" in result:
                    expected_fields |= {"branch_root_access_matrix",
                        "branch_root_access_matrix_verified"}
            if (type(result) is not dict or set(result) != expected_fields
                    or result.get("schema_version") not in {
                        "sentientos.durable_learning_worker_baseline_inventory:v2",
                        "sentientos.durable_learning_worker_baseline_inventory:v3",
                        "sentientos.durable_learning_worker_baseline_inventory:v4"}
                    or result.get("protocol_id") != checked_request["protocol_id"]
                    or result.get("protocol_digest") !=
                        checked_request["protocol_digest"]
                    or result.get("condition") != checked_request["condition"]
                    or not isinstance(result.get("branch_id"), str)
                    or not _require_digest(result.get("protocol_digest"))
                    or not isinstance(result.get("history_state_digest"), str)
                    or any(type(result.get(key)) is not bool for key in (
                        "history_snapshot_matches_retained_state",
                        "history_matches_protocol_baseline",
                        "active_empty_session_verified",
                        "branch_roots_disjoint",
                        "operation_journal_empty_verified"))
                    or not isinstance(result.get("branch_root_identity_digests"), list)
                    or len(result["branch_root_identity_digests"]) < 3
                    or any(not _require_digest(item) for item in
                        result["branch_root_identity_digests"])
                    or result.get("authority") is not False
                    or ConditionWorkerRPCDispatcher._result_digest(result) !=
                        value["result_digest"]):
                raise ConditionWorkerRPCError(
                    "durable_learning_worker_rpc_baseline_inventory_invalid")
            if inventory_v4:
                from .local_model_authority import digest_payload
                inventory = result.get("history_probe_input_inventory")
                inventory_fields = {"schema_version", "history_state_digest",
                    "record_count", "record_refs_digest", "probe_inputs",
                    "probe_inputs_digest", "owner_verified", "authority",
                    "inventory_digest"}
                inventory_body = ({key: item for key, item in inventory.items()
                    if key != "inventory_digest"}
                    if isinstance(inventory, Mapping) else {})
                probe_inputs = (inventory.get("probe_inputs")
                    if isinstance(inventory, Mapping) else None)
                if (not isinstance(inventory, Mapping)
                        or set(inventory) != inventory_fields
                        or inventory.get("schema_version") !=
                            "sentientos.resident_history_probe_input_inventory:v1"
                        or not isinstance(inventory.get("history_state_digest"), str)
                        or re.fullmatch(r"sha256:[0-9a-f]{64}",
                            inventory["history_state_digest"]) is None
                        or type(inventory.get("record_count")) is not int
                        or not 0 <= inventory["record_count"] <= 4096
                        or not _require_digest(inventory.get("record_refs_digest"))
                        or not isinstance(probe_inputs, list)
                        or len(probe_inputs) > 65_536
                        or any(type(item) is not int for item in probe_inputs)
                        or probe_inputs != sorted(set(probe_inputs))
                        or inventory.get("probe_inputs_digest") !=
                            digest_payload({"probe_inputs": probe_inputs})
                        or inventory.get("owner_verified") is not True
                        or inventory.get("authority") is not False
                        or inventory.get("inventory_digest") !=
                            digest_payload(inventory_body)
                        or type(result.get(
                            "history_probe_inventory_matches_protocol")) is not bool
                        or result.get("history_state_digest") !=
                            inventory.get("history_state_digest")
                        or (value["status"] == "completed"
                            and result.get(
                                "history_probe_inventory_matches_protocol") is not True)):
                    raise ConditionWorkerRPCError(
                        "durable_learning_worker_rpc_history_probe_inventory_invalid")
            if inventory_v3 or (inventory_v4
                    and "branch_root_access_matrix" in result):
                matrix = result.get("branch_root_access_matrix")
                if not isinstance(matrix, Mapping):
                    raise ConditionWorkerRPCError(
                        "durable_learning_worker_rpc_branch_root_matrix_invalid")
                roots = matrix.get("root_results")
                if not isinstance(roots, Mapping):
                    raise ConditionWorkerRPCError(
                        "durable_learning_worker_rpc_branch_root_matrix_invalid")
                manifest_stub = {"schema_version":
                        "sentientos.durable_learning_worker_baseline_runtime_manifest:v2",
                    "protocol_id": result["protocol_id"],
                    "condition": result["condition"],
                    "manifest_digest": matrix.get("manifest_digest"),
                    "peer_condition": matrix.get("peer_condition"),
                    "branch_id": matrix.get("own_branch_id"),
                    "peer_branch_id": matrix.get("peer_branch_id"),
                    "roots": {name: {"identity": row.get(
                        "own_expected_identity")}
                        for name, row in roots.items()
                        if isinstance(row, Mapping)},
                    "peer_roots": {name: {"identity": row.get(
                        "peer_expected_identity")}
                        for name, row in roots.items()
                        if isinstance(row, Mapping)}}
                try:
                    from .windows_appcontainer_access import (
                        verify_condition_worker_baseline_branch_root_access_result)
                    checked_matrix = (
                        verify_condition_worker_baseline_branch_root_access_result(
                            matrix, manifest=manifest_stub))
                except (TypeError, ValueError) as exc:
                    raise ConditionWorkerRPCError(
                        "durable_learning_worker_rpc_branch_root_matrix_invalid") from exc
                if result.get("branch_root_access_matrix_verified") is not (
                        checked_matrix.get(
                            "branch_root_access_matrix_verified") is True):
                    raise ConditionWorkerRPCError(
                        "durable_learning_worker_rpc_branch_root_matrix_invalid")
                if (value["status"] == "completed"
                        and checked_matrix.get(
                            "branch_root_access_matrix_verified") is not True):
                    raise ConditionWorkerRPCError(
                        "durable_learning_worker_rpc_branch_root_matrix_not_verified")
            journal = result.get("operation_journal_inventory")
            if journal is not None:
                from .local_model_authority import digest_payload
                if (type(journal) is not dict or set(journal) != {
                        "schema_version", "file_count", "directory_count",
                        "entries_digest", "empty", "authority",
                        "inventory_digest"}
                        or journal.get("schema_version") !=
                            "sentientos.durable_learning_worker_journal_baseline_inventory:v1"
                        or type(journal.get("file_count")) is not int
                        or type(journal.get("directory_count")) is not int
                        or journal["file_count"] < 0
                        or journal["directory_count"] < 0
                        or not _require_digest(journal.get("entries_digest"))
                        or journal.get("empty") is not (
                            journal["file_count"] == 0
                            and journal["directory_count"] == 0)
                        or journal.get("authority") is not False
                        or not _require_digest(journal.get("inventory_digest"))
                        or journal["inventory_digest"] != digest_payload({
                            key: item for key, item in journal.items()
                            if key != "inventory_digest"})
                        or result.get("operation_journal_empty_verified") is not
                            journal["empty"]):
                    raise ConditionWorkerRPCError(
                        "durable_learning_worker_rpc_baseline_journal_inventory_invalid")
            elif result.get("operation_journal_empty_verified") is not False:
                raise ConditionWorkerRPCError(
                    "durable_learning_worker_rpc_baseline_journal_inventory_invalid")
            if (value["status"] == "completed"
                    and ((checked_request["payload"].get(
                        "expected_baseline_inventory_digest") is not None
                        and checked_request["payload"][
                            "expected_baseline_inventory_digest"] !=
                                value["result_digest"])
                        or not result[
                            "history_snapshot_matches_retained_state"]
                        or not result["history_matches_protocol_baseline"]
                        or not result["active_empty_session_verified"]
                        or not result["branch_roots_disjoint"]
                        or not result["operation_journal_empty_verified"])):
                raise ConditionWorkerRPCError(
                    "durable_learning_worker_rpc_baseline_acceptance_invalid")
        elif result is not None:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_baseline_unexpected")
    if checked_request["operation"] == "inventory_profile_registry":
        result = value.get("result")
        if value["status"] == "completed":
            from .windows_appcontainer_registry import (
                verify_appcontainer_registry_inventory)
            try:
                checked_result = verify_appcontainer_registry_inventory(result,
                    expected_appcontainer_sid=checked_request["payload"][
                        "expected_appcontainer_sid"])
            except (TypeError, ValueError) as exc:
                raise ConditionWorkerRPCError(
                    "durable_learning_worker_rpc_registry_inventory_invalid") from exc
            if dict(checked_result) != dict(result):
                raise ConditionWorkerRPCError(
                    "durable_learning_worker_rpc_registry_inventory_invalid")
            if ConditionWorkerRPCDispatcher._result_digest(checked_result) != value[
                    "result_digest"]:
                raise ConditionWorkerRPCError(
                    "durable_learning_worker_rpc_registry_inventory_digest_mismatch")
        elif result is not None:
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_registry_inventory_unexpected")
    if (checked_request["operation"] == "recover_acquisition_receipts"
            and value["status"] == "completed"):
        result = value.get("result")
        required = {"receipt_index_digest", "receipt_count", "bundle_digest",
            "store_artifact_digest", "store_artifact_digest_bound",
            "receipt_ref_count", "receipt_ref_set_digest",
            "exact_store_set_match", "store_index_reloaded",
            "verifier_allowlist_matches_store",
            "source_invocation_receipts_reverified", "peer_artifacts_opened",
            "automatic_replay_performed", "authority"}
        if (type(result) is not dict or set(result) != required
                or not _require_digest(result.get("receipt_index_digest"))
                or type(result.get("receipt_count")) is not int
                or result["receipt_count"] != len(
                    checked_request["payload"]["task_digests"])
                or not _require_digest(result.get("bundle_digest"))
                or not _require_digest(result.get("store_artifact_digest"))
                or not _require_digest(result.get("receipt_ref_set_digest"))
                or type(result.get("receipt_ref_count")) is not int
                or result["receipt_ref_count"] < result["receipt_count"]
                or any(result.get(key) is not True for key in (
                    "store_artifact_digest_bound", "exact_store_set_match",
                    "store_index_reloaded",
                    "verifier_allowlist_matches_store"))
                or any(result.get(key) is not False for key in (
                    "source_invocation_receipts_reverified",
                    "peer_artifacts_opened", "automatic_replay_performed",
                    "authority"))
                or ConditionWorkerRPCDispatcher._result_digest(result) !=
                    value["result_digest"]):
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_receipt_recovery_result_invalid")
    elif (checked_request["operation"] == "recover_acquisition_receipts"
            and value.get("result") is not None):
        raise ConditionWorkerRPCError(
            "durable_learning_worker_rpc_receipt_recovery_result_unexpected")
    if (checked_request["operation"] ==
            "prepare_consolidation_snapshot"
            and value["status"] == "completed"):
        result = value.get("result")
        required = {"protocol_id", "protocol_digest", "condition",
            "branch_id", "snapshot_id", "snapshot_digest", "source_count",
            "receipt_bundle_digest", "receipt_store_artifact_digest",
            "observed_baseline_history_state_digest", "baseline_record_refs",
            "source_fact_ids", "allowed_history_record_refs",
            "withhold_developmental_history", "baseline_state_matches_protocol",
            "score_free_snapshot_payload_readback_verified",
            "score_material_included", "source_invocation_receipts_reverified",
            "custody_authenticated", "developmental_writeback_performed",
            "authority"}
        def valid_refs(refs: Any) -> bool:
            return (isinstance(refs, list) and len(refs) <= 512
                and all(isinstance(row, Mapping)
                    and set(row) == {"record_id", "record_digest"}
                    and isinstance(row.get("record_id"), str)
                    and re.fullmatch(r"devrec-[0-9a-f]{24}",
                        row["record_id"]) is not None
                    and isinstance(row.get("record_digest"), str)
                    and re.fullmatch(r"sha256:[0-9a-f]{64}",
                        row["record_digest"]) is not None
                    for row in refs)
                and len({row["record_id"] for row in refs}) == len(refs))
        if (type(result) is not dict or set(result) != required
                or result.get("protocol_id") != checked_request["protocol_id"]
                or result.get("protocol_digest") !=
                    checked_request["protocol_digest"]
                or result.get("condition") != checked_request["condition"]
                or not isinstance(result.get("branch_id"), str)
                or not isinstance(result.get("snapshot_id"), str)
                or not _require_digest(result.get("snapshot_digest"))
                or not _require_digest(result.get("receipt_bundle_digest"))
                or not _require_digest(result.get(
                    "receipt_store_artifact_digest"))
                or not isinstance(result.get(
                    "observed_baseline_history_state_digest"), str)
                or type(result.get("source_count")) is not int
                or not 1 <= result["source_count"] <= 512
                or not valid_refs(result.get("baseline_record_refs"))
                or not valid_refs(result.get("allowed_history_record_refs"))
                or not isinstance(result.get("source_fact_ids"), list)
                or not 1 <= len(result["source_fact_ids"]) <= 1024
                or any(not isinstance(item, str) or not item or len(item) > 256
                    for item in result["source_fact_ids"])
                or len(set(result["source_fact_ids"])) !=
                    len(result["source_fact_ids"])
                or any(type(result.get(key)) is not bool for key in (
                    "withhold_developmental_history",
                    "baseline_state_matches_protocol",
                    "score_free_snapshot_payload_readback_verified",
                    "score_material_included",
                    "source_invocation_receipts_reverified",
                    "custody_authenticated",
                    "developmental_writeback_performed", "authority"))
                or result.get("baseline_state_matches_protocol") is not True
                or result.get("score_free_snapshot_payload_readback_verified")
                    is not True
                or result.get("score_material_included") is not False
                or result.get("source_invocation_receipts_reverified") is not False
                or result.get("custody_authenticated") is not False
                or result.get("developmental_writeback_performed") is not False
                or result.get("authority") is not False
                or ConditionWorkerRPCDispatcher._result_digest(result) !=
                    value["result_digest"]):
            raise ConditionWorkerRPCError(
                "durable_learning_worker_rpc_snapshot_result_invalid")
    elif (checked_request["operation"] ==
            "prepare_consolidation_snapshot"
            and value.get("result") is not None):
        raise ConditionWorkerRPCError(
            "durable_learning_worker_rpc_snapshot_result_unexpected")
    return {"schema_version": "sentientos.durable_learning_condition_worker_rpc_verification:v1",
        "request_id": checked_request["request_id"],
        "condition": checked_request["condition"],
        "operation": checked_request["operation"],
        "response_status": value["status"],
        "response_result_digest": value["result_digest"],
        "request_response_bound": True,
        "transport_nonce_matched": True,
        "process_isolation_verified": False,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}
