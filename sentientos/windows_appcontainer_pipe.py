"""Bounded local named-pipe transport for condition-worker RPC.

This transport restricts one pipe instance to the current owner and one
AppContainer package SID, rejects remote clients, and binds connected process
identity to supervisor-observed PID and creation time. It does not prove
filesystem isolation or developmental learning.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import secrets
from ctypes import wintypes
from pathlib import Path
from typing import Any, Mapping


_PROTOCOL = re.compile(r"devexp-durable-learning-protocol-([0-9a-f]{24})")
_PACKAGE_SID = re.compile(r"S-1-15-2-(?:[0-9]+-)*[0-9]+")
_PIPE_NAME = re.compile(
    r"\\\\\.\\pipe\\LOCAL\\SentientOS\.DL\.[0-9a-f]{24}\.(?:Available|Withheld)\.[0-9a-f]{32}")
MAX_PIPE_MESSAGE_BYTES = 1_048_576


class WindowsAppContainerPipeError(ValueError):
    """The restricted condition-worker pipe failed closed."""

    def __init__(self, code: str, winerror: int | None = None) -> None:
        self.code = code
        self.winerror = winerror
        super().__init__(code if winerror is None else f"{code}:{winerror}")


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t), ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]


def _winerror(code: str) -> WindowsAppContainerPipeError:
    return WindowsAppContainerPipeError(code, int(ctypes.get_last_error()))


def _windows_apis() -> tuple[Any, Any]:
    if os.name != "nt":
        raise WindowsAppContainerPipeError("appcontainer_pipe_windows_only")
    try:
        kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
        advapi32 = getattr(ctypes, "WinDLL")("advapi32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_api_unavailable") from exc
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
        wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcessId.argtypes = []
    kernel32.GetCurrentProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
        wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel32.WaitNamedPipeW.restype = wintypes.BOOL
    kernel32.SetNamedPipeHandleState.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p, ctypes.c_void_p]
    kernel32.SetNamedPipeHandleState.restype = wintypes.BOOL
    kernel32.GetNamedPipeClientProcessId.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(wintypes.ULONG)]
    kernel32.GetNamedPipeClientProcessId.restype = wintypes.BOOL
    kernel32.GetNamedPipeServerProcessId.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(wintypes.ULONG)]
    kernel32.GetNamedPipeServerProcessId.restype = wintypes.BOOL
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, ctypes.c_void_p]
    kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CancelIoEx.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(_OVERLAPPED)]
    kernel32.CancelIoEx.restype = wintypes.BOOL
    kernel32.GetOverlappedResult.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(_OVERLAPPED), ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL]
    kernel32.GetOverlappedResult.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(_OVERLAPPED)]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(_OVERLAPPED)]
    kernel32.WriteFile.restype = wintypes.BOOL
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD)]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    return kernel32, advapi32


def observe_current_pipe_supervisor() -> dict[str, Any]:
    """Return the current process ID and creation time for worker bootstrap."""
    kernel32, _ = _windows_apis()
    handle = kernel32.GetCurrentProcess()
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel_time = wintypes.FILETIME()
    user_time = wintypes.FILETIME()
    if not kernel32.GetProcessTimes(handle, ctypes.byref(creation),
            ctypes.byref(exit_time), ctypes.byref(kernel_time),
            ctypes.byref(user_time)):
        raise _winerror("appcontainer_pipe_supervisor_start_unavailable")
    process_id = int(kernel32.GetCurrentProcessId())
    creation_time = (int(creation.dwHighDateTime) << 32) | int(
        creation.dwLowDateTime)
    if process_id <= 0 or creation_time <= 0:
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_supervisor_identity_invalid")
    return {"process_id": process_id,
        "process_creation_time_100ns": creation_time,
        "authority": False}


def _overlapped_wait(handle: int, operation: Any,
        kernel32: Any, *, timeout_ms: int) -> int:
    event = kernel32.CreateEventW(None, True, False, None)
    if not event:
        raise _winerror("appcontainer_pipe_event_create_failed")
    pending = False
    overlapped = _OVERLAPPED()
    overlapped.hEvent = event
    try:
        immediate, count = operation(ctypes.byref(overlapped))
        if immediate:
            return count
        error = int(ctypes.get_last_error())
        if error == 234:  # ERROR_MORE_DATA
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_message_over_bound", error)
        if error != 997:  # ERROR_IO_PENDING
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_io_failed", error)
        pending = True
        wait_result = kernel32.WaitForSingleObject(event, timeout_ms)
        if wait_result == 0x00000102:  # WAIT_TIMEOUT
            kernel32.CancelIoEx(handle, ctypes.byref(overlapped))
            kernel32.WaitForSingleObject(event, 0xFFFFFFFF)
            raise WindowsAppContainerPipeError("appcontainer_pipe_io_timeout")
        if wait_result != 0:
            kernel32.CancelIoEx(handle, ctypes.byref(overlapped))
            kernel32.WaitForSingleObject(event, 0xFFFFFFFF)
            raise _winerror("appcontainer_pipe_io_wait_failed")
        transferred = wintypes.DWORD()
        if not kernel32.GetOverlappedResult(handle, ctypes.byref(overlapped),
                ctypes.byref(transferred), False):
            raise _winerror("appcontainer_pipe_io_result_failed")
        return int(transferred.value)
    finally:
        if pending:
            # Completion was observed before freeing the OVERLAPPED event.
            pass
        if not kernel32.CloseHandle(event):
            raise _winerror("appcontainer_pipe_event_close_failed")


class WindowsAppContainerPipeConnection:
    """One connected message-mode pipe endpoint with bounded I/O."""

    def __init__(self, handle: int, kernel32: Any, *,
            peer_observation: Mapping[str, Any], role: str) -> None:
        self._handle = handle
        self._kernel32 = kernel32
        self.peer_observation = dict(peer_observation)
        self.role = role

    def write_message(self, raw: bytes, *, timeout_ms: int = 30_000) -> None:
        if (not self._handle or type(raw) is not bytes or not raw
                or len(raw) > MAX_PIPE_MESSAGE_BYTES
                or type(timeout_ms) is not int
                or not 0 <= timeout_ms <= 0xFFFFFFFE):
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_write_arguments_invalid")
        buffer = ctypes.create_string_buffer(raw, len(raw))

        def operation(overlapped: Any) -> tuple[bool, int]:
            transferred = wintypes.DWORD()
            ok = self._kernel32.WriteFile(self._handle, buffer, len(raw),
                ctypes.byref(transferred), overlapped)
            return bool(ok), int(transferred.value)

        transferred = _overlapped_wait(self._handle, operation,
            self._kernel32, timeout_ms=timeout_ms)
        if transferred != len(raw):
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_short_write")

    def read_message(self, *, max_bytes: int = MAX_PIPE_MESSAGE_BYTES,
            timeout_ms: int = 30_000) -> bytes:
        if (not self._handle or type(max_bytes) is not int
                or not 1 <= max_bytes <= MAX_PIPE_MESSAGE_BYTES
                or type(timeout_ms) is not int
                or not 0 <= timeout_ms <= 0xFFFFFFFE):
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_read_arguments_invalid")
        buffer = ctypes.create_string_buffer(max_bytes)

        def operation(overlapped: Any) -> tuple[bool, int]:
            transferred = wintypes.DWORD()
            ok = self._kernel32.ReadFile(self._handle, buffer, max_bytes,
                ctypes.byref(transferred), overlapped)
            return bool(ok), int(transferred.value)

        transferred = _overlapped_wait(self._handle, operation,
            self._kernel32, timeout_ms=timeout_ms)
        if transferred == 0:
            raise WindowsAppContainerPipeError("appcontainer_pipe_empty_message")
        return bytes(buffer.raw[:transferred])

    def close(self) -> None:
        if self._handle:
            handle = self._handle
            self._handle = 0
            if not self._kernel32.CloseHandle(handle):
                raise _winerror("appcontainer_pipe_handle_close_failed")


def exchange_condition_worker_rpc(connection: WindowsAppContainerPipeConnection,
        request: Mapping[str, Any], *,
        worker_observation: Mapping[str, Any],
        timeout_ms: int = 30_000) -> dict[str, Any]:
    """Exchange one validated request with the exact launched worker peer.

    This binds the transport peer to supervisor launch evidence and validates
    the response against the launch nonce. It does not attest filesystem
    isolation or make any experiment eligible for inference.
    """
    if (not isinstance(connection, WindowsAppContainerPipeConnection)
            or connection.role != "supervisor"
            or not isinstance(worker_observation, Mapping)
            or type(timeout_ms) is not int
            or not 0 <= timeout_ms <= 0xFFFFFFFE):
        raise WindowsAppContainerPipeError("appcontainer_pipe_rpc_arguments_invalid")
    expected_pid = worker_observation.get("process_id")
    expected_start = worker_observation.get("process_creation_time_100ns")
    nonce = worker_observation.get("process_start_nonce")
    expected_sid = worker_observation.get("appcontainer_sid")
    peer = connection.peer_observation
    if (type(expected_pid) is not int or type(expected_start) is not int
            or type(nonce) is not str
            or not isinstance(expected_sid, str)
            or peer.get("process_id") != expected_pid
            or peer.get("process_creation_time_100ns") != expected_start
            or not isinstance(peer.get("package_sid"), str)
            or peer["package_sid"].casefold() != expected_sid.casefold()
            or peer.get("pid_start_time_matched") is not True
            or peer.get("authority") is not False):
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_rpc_peer_binding_invalid")
    from .durable_learning_condition_worker_rpc import (
        decode_condition_worker_rpc, encode_condition_worker_rpc,
        verify_condition_worker_rpc_request)

    try:
        checked_request = verify_condition_worker_rpc_request(dict(request))
        raw_request = encode_condition_worker_rpc(checked_request)
        connection.write_message(raw_request, timeout_ms=timeout_ms)
        raw_response = connection.read_message(timeout_ms=timeout_ms)
        response = decode_condition_worker_rpc(raw_response,
            request=checked_request, transport_process_start_nonce=nonce)
    except (TypeError, ValueError) as exc:
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_rpc_exchange_invalid") from exc
    exchange = {"schema_version":
            "sentientos.windows_appcontainer_pipe_rpc_exchange:v1",
        "request_id": response["request_id"],
        "condition": response["condition"],
        "operation": response["operation"],
        "response_status": response["status"],
        "response_result_digest": response["result_digest"],
        "peer_process_id": expected_pid,
        "peer_process_creation_time_100ns": expected_start,
        "request_response_bound": True,
        "process_start_nonce_matched": True,
        "process_isolation_verified": False,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}
    if request.get("operation") in {
            "inspect_baseline", "inventory_profile_registry",
            "prepare_consolidation_snapshot",
            "reconstruct_strategy_projection_v2"}:
        exchange["response_result"] = response["result"]
    return exchange


def verify_condition_worker_access_probe_exchange(*, exchange: Mapping[str, Any],
        manifest: Mapping[str, Any],
        expected_worker_observation: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the worker's digest-only probe response to the exact expected matrix.

    Even a matching response is not sufficient to set isolation verified; the
    supervisor must recheck sentinel identities and contents independently.
    """
    from .windows_appcontainer_access import (
        expected_condition_worker_access_probe_rpc_digest,
    )

    if (not isinstance(exchange, Mapping)
            or not isinstance(manifest, Mapping)
            or not isinstance(expected_worker_observation, Mapping)):
        return {"schema_version":
                "sentientos.windows_appcontainer_access_probe_supervisor_check:v1",
            "worker_report_matches_expected_matrix": False,
            "process_identity_binding_verified": False,
            "independent_sentinel_recheck_required": True,
            "filesystem_isolation_verified": False,
            "retention_contrast_eligible": False,
            "authority": False}
    expected_pid = expected_worker_observation.get("process_id")
    expected_start = expected_worker_observation.get(
        "process_creation_time_100ns")
    expected_nonce = expected_worker_observation.get("process_start_nonce")
    if (type(expected_pid) is not int or expected_pid <= 0
            or type(expected_start) is not int or expected_start <= 0
            or exchange.get("schema_version") !=
                "sentientos.windows_appcontainer_pipe_rpc_exchange:v1"
            or exchange.get("operation") != "probe_access_matrix"
            or exchange.get("response_status") != "completed"
            or exchange.get("peer_process_id") != expected_pid
            or exchange.get("peer_process_creation_time_100ns") != expected_start
            or exchange.get("process_start_nonce_matched") is not True
            or not isinstance(expected_nonce, str)
            or re.fullmatch(r"[0-9a-f]{32}", expected_nonce) is None):
        return {"schema_version":
                "sentientos.windows_appcontainer_access_probe_supervisor_check:v1",
            "worker_report_matches_expected_matrix": False,
            "process_identity_binding_verified": False,
            "independent_sentinel_recheck_required": True,
            "filesystem_isolation_verified": False,
            "retention_contrast_eligible": False,
            "authority": False}
    expected_digest = expected_condition_worker_access_probe_rpc_digest(manifest)
    matches = exchange.get("response_result_digest") == expected_digest
    return {"schema_version":
            "sentientos.windows_appcontainer_access_probe_supervisor_check:v1",
        "protocol_id": manifest.get("protocol_id"),
        "condition": manifest.get("condition"),
        "manifest_digest": manifest.get("manifest_digest"),
        "response_result_digest": exchange.get("response_result_digest"),
        "expected_result_digest": expected_digest,
        "worker_report_matches_expected_matrix": matches,
        "process_identity_binding_verified": True,
        "independent_sentinel_recheck_required": True,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}


def verify_condition_worker_access_probe_after_exit(*, exchange: Mapping[str, Any],
        manifest: Mapping[str, Any], worker_process: Any) -> dict[str, Any]:
    """Bind probe exchange and sentinel readback to an exited worker handle."""
    from .windows_appcontainer_access import (
        expected_condition_worker_access_probe_rpc_digest,
        verify_condition_worker_access_probe_sentinels)
    from .windows_appcontainer_process import WindowsAppContainerProcess
    from .local_model_authority import digest_payload

    if not isinstance(worker_process, WindowsAppContainerProcess):
        raise WindowsAppContainerPipeError(
            "appcontainer_access_probe_process_handle_invalid")
    if not isinstance(manifest, Mapping):
        raise WindowsAppContainerPipeError(
            "appcontainer_access_probe_manifest_invalid")
    try:
        exit_code = worker_process.wait(0)
        identity = worker_process.observe_identity()
    except (OSError, TypeError, ValueError) as exc:
        raise WindowsAppContainerPipeError(
            "appcontainer_access_probe_exit_observation_failed") from exc
    worker_exited = exit_code is not None
    launch_raw = worker_process.observation
    launch_fields = (
        "process_id", "process_creation_time_100ns", "token_is_appcontainer",
        "appcontainer_sid", "enabled_capability_count",
        "inherited_handles_requested", "process_start_nonce",
        "environment_block_sha256", "requested_executable_sha256",
        "requested_capability_count", "job_object_bound",
        "job_active_process_limit", "isolation_verified", "authority")
    launch_observation = ({field: launch_raw.get(field)
        for field in launch_fields} if isinstance(launch_raw, Mapping) else None)
    if (not isinstance(launch_observation, Mapping)
            or launch_observation.get("process_id") != identity.get("process_id")
            or launch_observation.get("process_creation_time_100ns") !=
                identity.get("process_creation_time_100ns")
            or launch_observation.get("appcontainer_sid") !=
                manifest.get("appcontainer_sid")
            or launch_observation.get("process_start_nonce") !=
                worker_process.process_start_nonce):
        raise WindowsAppContainerPipeError(
            "appcontainer_access_probe_launch_observation_mismatch")
    exchange_check: dict[str, Any] = {
        "worker_report_matches_expected_matrix": False,
        "process_identity_binding_verified": False}
    sentinel_check: dict[str, Any] | None = None
    if worker_exited:
        expected_observation = {**identity,
            "process_start_nonce": worker_process.process_start_nonce}
        exchange_check = verify_condition_worker_access_probe_exchange(
            exchange=exchange, manifest=manifest,
            expected_worker_observation=expected_observation)
        sentinel_check = verify_condition_worker_access_probe_sentinels(
            manifest, worker_exit_confirmed=True)
    sentinels_match = bool(sentinel_check and
        sentinel_check.get("all_sentinel_identities_and_contents_match") is True)
    expected_result_digest = expected_condition_worker_access_probe_rpc_digest(
        manifest)
    semantic = {"schema_version":
            "sentientos.windows_appcontainer_access_probe_completion:v3",
        "protocol_id": manifest.get("protocol_id"),
        "condition": manifest.get("condition"),
        "manifest_digest": manifest.get("manifest_digest"),
        "worker_process_id": identity["process_id"],
        "worker_process_creation_time_100ns":
            identity["process_creation_time_100ns"],
        "worker_exit_confirmed_by_process_handle": worker_exited,
        "worker_exit_code": exit_code,
        "worker_report_matches_expected_matrix": exchange_check.get(
            "worker_report_matches_expected_matrix") is True,
        "worker_response_result_digest": exchange_check.get(
            "response_result_digest"),
        "expected_result_digest": expected_result_digest,
        "worker_launch_observation": launch_observation,
        "process_identity_binding_verified": exchange_check.get(
            "process_identity_binding_verified") is True,
        "sentinel_readback": sentinel_check,
        "all_probe_checks_match": (worker_exited
            and exit_code == 0
            and exchange_check.get("worker_report_matches_expected_matrix") is True
            and exchange_check.get("process_identity_binding_verified") is True
            and sentinels_match),
        "process_isolation_verified": False,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}
    return {**semantic, "completion_digest": digest_payload(semantic)}


def serve_condition_worker_rpc(connection: WindowsAppContainerPipeConnection,
        dispatcher: Any, *, max_requests: int = 1024,
        timeout_ms: int = 30_000) -> dict[str, Any]:
    """Serve a bounded sequence of requests on a worker-side pipe connection."""
    from .durable_learning_condition_worker_rpc import (
        ConditionWorkerRPCDispatcher)

    if (not isinstance(connection, WindowsAppContainerPipeConnection)
            or connection.role != "worker"
            or not isinstance(dispatcher, ConditionWorkerRPCDispatcher)
            or type(max_requests) is not int or not 1 <= max_requests <= 10_000
            or type(timeout_ms) is not int
            or not 0 <= timeout_ms <= 0xFFFFFFFE):
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_worker_server_arguments_invalid")
    processed = 0
    failed_closed = False
    while processed < max_requests:
        raw_request = connection.read_message(timeout_ms=timeout_ms)
        raw_response = dispatcher.dispatch(raw_request)
        connection.write_message(raw_response, timeout_ms=timeout_ms)
        processed += 1
        if dispatcher.poisoned:
            failed_closed = True
            break
    return {"schema_version":
            "sentientos.windows_appcontainer_pipe_worker_server:v1",
        "requests_processed": processed,
        "stopped_after_ambiguous_backend_result": failed_closed,
        "request_limit_reached": processed == max_requests,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}


def serve_condition_worker_access_probe_once(
        connection: WindowsAppContainerPipeConnection, dispatcher: Any, *,
        process_start_nonce: str, timeout_ms: int = 30_000) -> dict[str, Any]:
    """Serve the ordered access probe and registry inventory, then exit."""
    from .durable_learning_condition_worker_rpc import (
        ConditionWorkerRPCDispatcher, decode_condition_worker_rpc)

    if (not isinstance(connection, WindowsAppContainerPipeConnection)
            or connection.role != "worker"
            or not isinstance(dispatcher, ConditionWorkerRPCDispatcher)
            or dispatcher.allowed_operations not in {
                frozenset({"probe_access_matrix"}),
                frozenset({"probe_access_matrix",
                    "inventory_profile_registry"})}
            or not isinstance(process_start_nonce, str)
            or re.fullmatch(r"[0-9a-f]{32}", process_start_nonce) is None
            or type(timeout_ms) is not int
            or not 0 <= timeout_ms <= 0xFFFFFFFE):
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_access_probe_worker_arguments_invalid")
    try:
        if dispatcher.allowed_operations == frozenset({"probe_access_matrix"}):
            raw_request = connection.read_message(timeout_ms=timeout_ms)
            request = decode_condition_worker_rpc(raw_request)
            if request.get("operation") != "probe_access_matrix":
                raise WindowsAppContainerPipeError(
                    "appcontainer_pipe_access_probe_operation_required")
            raw_response = dispatcher.dispatch(raw_request)
            connection.write_message(raw_response, timeout_ms=timeout_ms)
            response = decode_condition_worker_rpc(raw_response, request=request,
                transport_process_start_nonce=process_start_nonce)
            return {"schema_version":
                    "sentientos.windows_appcontainer_access_probe_worker_once:v1",
                "requests_processed": 1,
                "operation": response["operation"],
                "response_status": response["status"],
                "response_result_digest": response["result_digest"],
                "dispatcher_poisoned": dispatcher.poisoned,
                "process_isolation_verified": False,
                "filesystem_isolation_verified": False,
                "retention_contrast_eligible": False,
                "authority": False}
        responses: dict[str, Mapping[str, Any]] = {}
        for expected_operation in ("probe_access_matrix",
                "inventory_profile_registry"):
            raw_request = connection.read_message(timeout_ms=timeout_ms)
            request = decode_condition_worker_rpc(raw_request)
            if request.get("operation") != expected_operation:
                raise WindowsAppContainerPipeError(
                    "appcontainer_pipe_worker_operation_order_invalid")
            raw_response = dispatcher.dispatch(raw_request)
            connection.write_message(raw_response, timeout_ms=timeout_ms)
            responses[expected_operation] = decode_condition_worker_rpc(
                raw_response, request=request,
                transport_process_start_nonce=process_start_nonce)
        registry_result = responses["inventory_profile_registry"]["result"]
        if (responses["inventory_profile_registry"]["status"] == "completed"
                and not isinstance(registry_result, Mapping)):
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_registry_inventory_response_invalid")
        return {"schema_version":
                "sentientos.windows_appcontainer_profile_state_worker_once:v1",
            "requests_processed": 2,
            "operation": "profile_state_preflight",
            "response_status": ("completed" if all(response["status"] ==
                "completed" for response in responses.values()) else
                "failed" if any(response["status"] == "failed"
                    for response in responses.values()) else "rejected"),
            "response_result_digest": responses["probe_access_matrix"][
                "result_digest"],
            "registry_inventory_digest": (registry_result.get("inventory_digest")
                if isinstance(registry_result, Mapping) else None),
            "dispatcher_poisoned": dispatcher.poisoned,
            "process_isolation_verified": False,
            "filesystem_isolation_verified": False,
            "retention_contrast_eligible": False,
            "authority": False}
    finally:
        connection.close()


def serve_condition_worker_baseline_once(
        connection: WindowsAppContainerPipeConnection, dispatcher: Any, *,
        process_start_nonce: str, timeout_ms: int = 30_000) -> dict[str, Any]:
    """Serve one baseline inspection request, then close the worker pipe.

    The dispatcher must expose only ``inspect_baseline``. This bounded path
    prevents a baseline process from accepting follow-up mutation or scoring
    requests after returning its initial inventory.
    """
    from .durable_learning_condition_worker_rpc import (
        ConditionWorkerRPCDispatcher, decode_condition_worker_rpc)

    if (not isinstance(connection, WindowsAppContainerPipeConnection)
            or connection.role != "worker"
            or not isinstance(dispatcher, ConditionWorkerRPCDispatcher)
            or dispatcher.allowed_operations != frozenset({"inspect_baseline"})
            or not isinstance(process_start_nonce, str)
            or re.fullmatch(r"[0-9a-f]{32}", process_start_nonce) is None
            or type(timeout_ms) is not int
            or not 0 <= timeout_ms <= 0xFFFFFFFE):
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_baseline_worker_arguments_invalid")
    try:
        raw_request = connection.read_message(timeout_ms=timeout_ms)
        request = decode_condition_worker_rpc(raw_request)
        if request.get("operation") != "inspect_baseline":
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_baseline_operation_required")
        raw_response = dispatcher.dispatch(raw_request)
        connection.write_message(raw_response, timeout_ms=timeout_ms)
        response = decode_condition_worker_rpc(raw_response, request=request,
            transport_process_start_nonce=process_start_nonce)
        if (response.get("status") == "completed"
                and not isinstance(response.get("result"), Mapping)):
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_baseline_response_invalid")
        return {"schema_version":
                "sentientos.windows_appcontainer_baseline_worker_once:v1",
            "requests_processed": 1,
            "operation": response["operation"],
            "response_status": response["status"],
            "response_result_digest": response["result_digest"],
            "baseline_inventory_digest": (
                response["result"].get("inventory_digest")
                if isinstance(response.get("result"), Mapping) else None),
            "dispatcher_poisoned": dispatcher.poisoned,
            "process_isolation_verified": False,
            "filesystem_isolation_verified": False,
            "retention_contrast_eligible": False,
            "authority": False}
    finally:
        connection.close()


class WindowsAppContainerPipeEndpoint:
    """Supervisor-owned one-client pipe restricted to one package SID."""

    def __init__(self, handle: int, kernel32: Any, *, name: str,
            package_sid: str) -> None:
        self._handle = handle
        self._kernel32 = kernel32
        self.name = name
        self.package_sid = package_sid
        self._accepted = False

    def accept(self, *, expected_worker_observation: Mapping[str, Any],
            timeout_ms: int = 30_000) -> WindowsAppContainerPipeConnection:
        if (not self._handle or self._accepted
                or not isinstance(expected_worker_observation, Mapping)
                or type(timeout_ms) is not int
                or not 0 <= timeout_ms <= 0xFFFFFFFE):
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_accept_arguments_invalid")
        expected_pid = expected_worker_observation.get("process_id")
        expected_start = expected_worker_observation.get(
            "process_creation_time_100ns")
        if (type(expected_pid) is not int or expected_pid <= 0
                or type(expected_start) is not int or expected_start <= 0):
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_expected_process_invalid")
        connect = self._kernel32.ConnectNamedPipe
        connect.argtypes = [wintypes.HANDLE, ctypes.POINTER(_OVERLAPPED)]
        connect.restype = wintypes.BOOL

        def operation(overlapped: Any) -> tuple[bool, int]:
            ok = connect(self._handle, overlapped)
            if not ok and int(ctypes.get_last_error()) == 535:
                return True, 0  # ERROR_PIPE_CONNECTED
            return bool(ok), 0

        _overlapped_wait(self._handle, operation, self._kernel32,
            timeout_ms=timeout_ms)
        try:
            client_pid = wintypes.ULONG()
            get_client_pid = self._kernel32.GetNamedPipeClientProcessId
            get_client_pid.argtypes = [wintypes.HANDLE,
                ctypes.POINTER(wintypes.ULONG)]
            get_client_pid.restype = wintypes.BOOL
            if not get_client_pid(self._handle, ctypes.byref(client_pid)):
                raise _winerror("appcontainer_pipe_client_pid_unavailable")
            client_handle = self._kernel32.OpenProcess(0x1000, False,
                client_pid.value)
            if not client_handle:
                raise _winerror("appcontainer_pipe_client_process_unavailable")
            try:
                creation = wintypes.FILETIME()
                exit_time = wintypes.FILETIME()
                kernel_time = wintypes.FILETIME()
                user_time = wintypes.FILETIME()
                if not self._kernel32.GetProcessTimes(client_handle,
                        ctypes.byref(creation), ctypes.byref(exit_time),
                        ctypes.byref(kernel_time), ctypes.byref(user_time)):
                    raise _winerror("appcontainer_pipe_client_start_unavailable")
                client_start = (int(creation.dwHighDateTime) << 32) | int(
                    creation.dwLowDateTime)
            finally:
                self._kernel32.CloseHandle(client_handle)
            if (int(client_pid.value) != expected_pid
                    or client_start != expected_start):
                raise WindowsAppContainerPipeError(
                    "appcontainer_pipe_client_process_mismatch")
            self._accepted = True
            handle = self._handle
            self._handle = 0
            return WindowsAppContainerPipeConnection(handle,
                self._kernel32, peer_observation={"process_id": int(client_pid.value),
                "process_creation_time_100ns": client_start,
                "package_sid": self.package_sid,
                "pid_start_time_matched": True,
                "authority": False}, role="supervisor")
        except Exception:
            handle = self._handle
            self._handle = 0
            if handle:
                self._kernel32.CloseHandle(handle)
            raise

    def close(self) -> None:
        if self._handle:
            handle = self._handle
            self._handle = 0
            if not self._kernel32.CloseHandle(handle):
                raise _winerror("appcontainer_pipe_endpoint_close_failed")


def create_condition_worker_pipe_endpoint(*, protocol_id: str,
        condition: str, package_sid: str) -> WindowsAppContainerPipeEndpoint:
    """Create a unique local message pipe with a narrow package-SID DACL."""
    match = _PROTOCOL.fullmatch(protocol_id) if isinstance(protocol_id, str) else None
    condition_names = {"relevant_experience_available": "Available",
        "relevant_experience_withheld": "Withheld"}
    if (match is None or not isinstance(condition, str)
            or condition not in condition_names
            or not isinstance(package_sid, str)
            or _PACKAGE_SID.fullmatch(package_sid) is None):
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_endpoint_arguments_invalid")
    kernel32, advapi32 = _windows_apis()
    pipe_name = (r"\\.\pipe\LOCAL\SentientOS.DL." + match.group(1) + "."
        + condition_names[condition] + "." + secrets.token_hex(16))
    # FILE_CREATE_PIPE_INSTANCE is granted to OWNER RIGHTS only. The worker
    # receives data/read-control rights without permission to add pipe servers.
    sddl = ("D:P(A;;0x00120187;;;OW)(A;;0x00120183;;;" +
        package_sid + ")")
    security_descriptor = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(security_descriptor), None):
        raise _winerror("appcontainer_pipe_security_descriptor_invalid")

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL)]

    security_attributes = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES),
        security_descriptor, False)
    create_pipe = kernel32.CreateNamedPipeW
    create_pipe.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(SECURITY_ATTRIBUTES)]
    create_pipe.restype = wintypes.HANDLE
    handle = create_pipe(pipe_name, 0x00000003 | 0x00080000 | 0x40000000,
        0x00000004 | 0x00000002 | 0x00000008, 1,
        MAX_PIPE_MESSAGE_BYTES, MAX_PIPE_MESSAGE_BYTES, 0,
        ctypes.byref(security_attributes))
    error = int(ctypes.get_last_error()) if not handle or handle == ctypes.c_void_p(-1).value else None
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.LocalFree(security_descriptor)
    if error is not None:
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_create_failed", error)
    return WindowsAppContainerPipeEndpoint(int(handle), kernel32,
        name=pipe_name, package_sid=package_sid)


def connect_condition_worker_pipe(*, pipe_name: str,
        package_sid: str, expected_supervisor_observation: Mapping[str, Any],
        timeout_ms: int = 30_000) -> WindowsAppContainerPipeConnection:
    """Connect from the worker and bind the server to supervisor PID/start time."""
    if (not isinstance(pipe_name, str) or _PIPE_NAME.fullmatch(pipe_name) is None
            or not isinstance(package_sid, str)
            or _PACKAGE_SID.fullmatch(package_sid) is None
            or not isinstance(expected_supervisor_observation, Mapping)
            or type(timeout_ms) is not int or not 0 <= timeout_ms <= 0xFFFFFFFE):
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_client_arguments_invalid")
    from .windows_appcontainer_process import _observe_process, _windows_apis as process_apis
    kernel32, advapi32 = process_apis()
    worker_identity = _observe_process(kernel32.GetCurrentProcess(),
        package_sid, kernel32=kernel32, advapi32=advapi32)
    kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel32.WaitNamedPipeW.restype = wintypes.BOOL
    if not kernel32.WaitNamedPipeW(pipe_name, timeout_ms):
        raise _winerror("appcontainer_pipe_wait_failed")
    open_pipe = kernel32.CreateFileW
    open_pipe.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    open_pipe.restype = wintypes.HANDLE
    handle = open_pipe(pipe_name, 0x00120183, 0, None, 3,
        0x40000000 | 0x00110000, None)
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise _winerror("appcontainer_pipe_open_failed")
    try:
        mode = wintypes.DWORD(0x00000002)  # PIPE_READMODE_MESSAGE
        if not kernel32.SetNamedPipeHandleState(handle, ctypes.byref(mode),
                None, None):
            raise _winerror("appcontainer_pipe_message_mode_failed")
        server_pid = wintypes.ULONG()
        get_server_pid = kernel32.GetNamedPipeServerProcessId
        get_server_pid.argtypes = [wintypes.HANDLE,
            ctypes.POINTER(wintypes.ULONG)]
        get_server_pid.restype = wintypes.BOOL
        if not get_server_pid(handle, ctypes.byref(server_pid)):
            raise _winerror("appcontainer_pipe_server_pid_unavailable")
        expected_pid = expected_supervisor_observation.get("process_id")
        expected_start = expected_supervisor_observation.get(
            "process_creation_time_100ns")
        if (type(expected_pid) is not int or type(expected_start) is not int
                or int(server_pid.value) != expected_pid):
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_server_process_mismatch")
        server_handle = kernel32.OpenProcess(0x1000, False, server_pid.value)
        if not server_handle:
            raise _winerror("appcontainer_pipe_server_process_unavailable")
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(server_handle,
                    ctypes.byref(creation), ctypes.byref(exit_time),
                    ctypes.byref(kernel_time), ctypes.byref(user_time)):
                raise _winerror("appcontainer_pipe_server_start_unavailable")
            server_start = (int(creation.dwHighDateTime) << 32) | int(
                creation.dwLowDateTime)
        finally:
            kernel32.CloseHandle(server_handle)
        if server_start != expected_start:
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_server_process_mismatch")
        return WindowsAppContainerPipeConnection(handle, kernel32,
            peer_observation={"process_id": int(server_pid.value),
                "process_creation_time_100ns": server_start,
                "worker_process_id": worker_identity["process_id"],
                "worker_appcontainer_sid": package_sid,
                "pid_start_time_matched": True,
                "authority": False}, role="worker")
    except Exception:
        kernel32.CloseHandle(handle)
        raise


def bootstrap_condition_worker_pipe_from_environment(
        *, timeout_ms: int = 30_000,
        protocol: Mapping[str, Any] | None = None
        ) -> tuple[WindowsAppContainerPipeConnection, dict[str, Any]]:
    """Connect using only the launcher's closed worker bootstrap variables."""
    names = {
        "pipe_name": "SENTIENTOS_WORKER_PIPE_NAME",
        "package_sid": "SENTIENTOS_WORKER_APPCONTAINER_SID",
        "protocol_id": "SENTIENTOS_WORKER_PROTOCOL_ID",
        "protocol_digest": "SENTIENTOS_WORKER_PROTOCOL_DIGEST",
        "condition": "SENTIENTOS_WORKER_CONDITION",
        "process_start_nonce": "SENTIENTOS_WORKER_START_NONCE",
        "supervisor_process_id": "SENTIENTOS_SUPERVISOR_PROCESS_ID",
        "supervisor_creation_time_100ns":
            "SENTIENTOS_SUPERVISOR_CREATION_TIME_100NS",
    }
    values = {key: os.environ.get(environment_name)
        for key, environment_name in names.items()}
    if (any(not isinstance(value, str) or not value
                for value in values.values())
            or _PROTOCOL.fullmatch(values["protocol_id"]) is None
            or re.fullmatch(r"[0-9a-f]{64}",
                values["protocol_digest"]) is None
            or values["condition"] not in {
                "relevant_experience_available",
                "relevant_experience_withheld"}
            or re.fullmatch(r"[0-9a-f]{32}",
                values["process_start_nonce"]) is None):
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_worker_bootstrap_invalid")
    try:
        supervisor_pid = int(values["supervisor_process_id"], 10)
        supervisor_start = int(values[
            "supervisor_creation_time_100ns"], 10)
    except ValueError as exc:
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_worker_supervisor_identity_invalid") from exc
    if supervisor_pid <= 0 or supervisor_start <= 0:
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_worker_supervisor_identity_invalid")
    connection = connect_condition_worker_pipe(
        pipe_name=values["pipe_name"], package_sid=values["package_sid"],
        expected_supervisor_observation={"process_id": supervisor_pid,
            "process_creation_time_100ns": supervisor_start,
            "authority": False}, timeout_ms=timeout_ms)
    context: dict[str, Any] = {"protocol_id": values["protocol_id"],
        "protocol_digest": values["protocol_digest"],
        "condition": values["condition"],
        "process_start_nonce": values["process_start_nonce"],
        "appcontainer_sid": values["package_sid"],
        "authority": False}
    receipt_root = os.environ.get("SENTIENTOS_WORKER_RECEIPT_BUNDLE_ROOT")
    receipt_artifact_text = os.environ.get(
        "SENTIENTOS_WORKER_RECEIPT_STORE_ARTIFACT_JSON")
    if (receipt_root is None) != (receipt_artifact_text is None):
        connection.close()
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_worker_receipt_binding_incomplete")
    if receipt_root is not None:
        if (not isinstance(protocol, Mapping)
                or protocol.get("protocol_id") != values["protocol_id"]
                or len(receipt_artifact_text.encode("utf-8", errors="strict")) > 8192):
            connection.close()
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_worker_receipt_protocol_invalid")
        try:
            from .durable_learning_condition_receipts import (
                _reject_duplicate_json_keys,
                load_staged_condition_scoped_acquisition_receipt_bundle)
            artifact = json.loads(receipt_artifact_text,
                object_pairs_hook=_reject_duplicate_json_keys)
            if not isinstance(artifact, dict):
                raise ValueError("artifact_not_object")
            root_identity = artifact.get("root_identity")
            if (not isinstance(root_identity, Mapping)
                    or type(root_identity.get("volume_serial")) is not int
                    or not isinstance(root_identity.get("file_id_hex"), str)
                    or re.fullmatch(r"[0-9a-f]{32}",
                        root_identity["file_id_hex"]) is None):
                raise ValueError("artifact_root_identity_invalid")
            staged = load_staged_condition_scoped_acquisition_receipt_bundle(
                root=Path(receipt_root),
                expected_root_identity=(root_identity["volume_serial"],
                    bytes.fromhex(root_identity["file_id_hex"])),
                appcontainer_sid=values["package_sid"], artifact=artifact,
                protocol=protocol, condition=values["condition"])
        except Exception as exc:
            connection.close()
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_worker_receipt_bundle_invalid") from exc
        context["condition_receipt_bundle"] = staged["bundle"]
        context["condition_receipt_bundle_verification"] = staged[
            "bundle_verification"]
        context["condition_receipt_store_artifact"] = artifact
        context["condition_receipt_store_artifact_digest"] = staged[
            "store_artifact_digest"]
        context["condition_receipt_bundle_custody_authenticated"] = False
    invocation_receipt_root = os.environ.get(
        "SENTIENTOS_WORKER_INVOCATION_RECEIPT_ROOT")
    invocation_receipt_artifact_text = os.environ.get(
        "SENTIENTOS_WORKER_INVOCATION_RECEIPT_STORE_ARTIFACT_JSON")
    if ((invocation_receipt_root is None) !=
            (invocation_receipt_artifact_text is None)):
        connection.close()
        raise WindowsAppContainerPipeError(
            "appcontainer_pipe_worker_invocation_receipt_binding_incomplete")
    if invocation_receipt_root is not None:
        if (not isinstance(protocol, Mapping)
                or protocol.get("protocol_id") != values["protocol_id"]
                or protocol.get("protocol_digest") != values["protocol_digest"]
                or len(invocation_receipt_artifact_text.encode(
                    "utf-8", errors="strict")) > 131_072):
            connection.close()
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_worker_invocation_receipt_protocol_invalid")
        try:
            from .durable_learning_condition_receipts import (
                _reject_duplicate_json_keys)
            from .durable_learning_invocation_receipts import (
                ConditionInvocationReceiptVerifier,
                load_condition_invocation_receipt_store)
            artifact = json.loads(invocation_receipt_artifact_text,
                object_pairs_hook=_reject_duplicate_json_keys)
            if not isinstance(artifact, dict):
                raise ValueError("invocation_receipt_artifact_not_object")
            root_identity = artifact.get("root_identity")
            if (not isinstance(root_identity, Mapping)
                    or type(root_identity.get("volume_serial")) is not int
                    or not isinstance(root_identity.get("file_id_hex"), str)
                    or re.fullmatch(r"[0-9a-f]{32}",
                        root_identity["file_id_hex"]) is None):
                raise ValueError("invocation_receipt_root_identity_invalid")
            identity = (root_identity["volume_serial"],
                bytes.fromhex(root_identity["file_id_hex"]))
            root = Path(invocation_receipt_root).resolve(strict=True)
            staged = load_condition_invocation_receipt_store(root=root,
                expected_root_identity=identity,
                appcontainer_sid=values["package_sid"], artifact=artifact,
                protocol=protocol, condition=values["condition"])
            context["invocation_receipt_verifier"] = (
                ConditionInvocationReceiptVerifier(receipt_root=root,
                    expected_root_identity=identity,
                    appcontainer_sid=values["package_sid"],
                    allowed_receipt_digests=staged["receipt_digests"]))
            context["invocation_receipt_store_artifact"] = artifact
            context["invocation_receipt_store_artifact_digest"] = staged[
                "artifact_digest"]
        except Exception as exc:
            connection.close()
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_worker_invocation_receipt_store_invalid") from exc
    access_manifest_text = os.environ.get(
        "SENTIENTOS_WORKER_ACCESS_PROBE_MANIFEST_JSON")
    if access_manifest_text is not None:
        if len(access_manifest_text.encode("utf-8", errors="strict")) > 8192:
            connection.close()
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_worker_access_manifest_over_bound")
        try:
            from .durable_learning_condition_receipts import (
                _reject_duplicate_json_keys)
            from .windows_appcontainer_access import (
                verify_condition_worker_access_probe_manifest)
            manifest = json.loads(access_manifest_text,
                object_pairs_hook=_reject_duplicate_json_keys)
            manifest = verify_condition_worker_access_probe_manifest(
                manifest, protocol_id=values["protocol_id"],
                condition=values["condition"],
                appcontainer_sid=values["package_sid"])
        except Exception as exc:
            connection.close()
            raise WindowsAppContainerPipeError(
                "appcontainer_pipe_worker_access_manifest_invalid") from exc
        context["access_probe_manifest"] = manifest
        context["access_probe_manifest_digest"] = manifest[
            "manifest_digest"]
        context["access_probe_supervisor_verification_required"] = True
    return connection, context
