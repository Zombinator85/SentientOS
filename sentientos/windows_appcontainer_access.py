"""Narrow AppContainer DACL grants for durable-learning worker directories.

The helpers apply an inheritable package-SID ACE to one already-existing,
identity-pinned directory. They do not prove the process can use the grant or
is denied access elsewhere; that requires a live worker access matrix.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any, Iterator, Mapping

from .windows_handle_custody import (observe_directory_identity,
    observe_private_directory_identity)
from .local_model_authority import digest_payload


class WindowsAppContainerAccessError(ValueError):
    """The explicit AppContainer directory ACL operation failed closed."""

    def __init__(self, code: str, winerror: int | None = None, *,
            mutation_state: str = "not_attempted") -> None:
        self.code = code
        self.winerror = winerror
        self.mutation_state = mutation_state
        super().__init__(code if winerror is None else f"{code}:{winerror}")


_ACTIVE_ACCESS_PROBE_PROTOCOLS: set[str] = set()
_ABANDONED_ACCESS_PROBE_MUTEXES: dict[str, Any] = {}
_QUARANTINED_ACCESS_PROBE_PROTOCOLS: set[str] = set()


def quarantine_active_condition_worker_access_probe(protocol_id: str) -> None:
    """Keep the current protocol mutex held when durable evidence cannot be saved."""
    if protocol_id in _ACTIVE_ACCESS_PROBE_PROTOCOLS:
        _QUARANTINED_ACCESS_PROBE_PROTOCOLS.add(protocol_id)


@contextmanager
def condition_worker_access_probe_mutex(protocol_id: str) -> Iterator[None]:
    """Serialize the full supervised probe lifecycle per protocol on Windows."""
    if (os.name != "nt" or not isinstance(protocol_id, str)
            or re.fullmatch(r"devexp-durable-learning-protocol-[0-9a-f]{24}",
                protocol_id) is None):
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_mutex_arguments_invalid")
    if protocol_id in _ABANDONED_ACCESS_PROBE_MUTEXES:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_mutex_abandoned")
    if protocol_id in _ACTIVE_ACCESS_PROBE_PROTOCOLS:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_already_running")
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_mutex_unavailable")
    kernel32 = loader("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
        wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    mutex_name = "Local\\SentientOS-DurableLearningAccessProbe-" + \
        protocol_id[-24:]
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        raise _winerror("appcontainer_access_probe_mutex_create_failed")
    wait_result = kernel32.WaitForSingleObject(handle, 0)
    if wait_result == 0x00000080:  # WAIT_ABANDONED: prior owner exited mid-run
        # Retain ownership and the handle so this protocol stays quarantined.
        _ABANDONED_ACCESS_PROBE_MUTEXES[protocol_id] = handle
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_mutex_abandoned")
    if wait_result == 0x00000102:  # WAIT_TIMEOUT: another process owns it
        kernel32.CloseHandle(handle)
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_already_running")
    if wait_result != 0:
        error = int(ctypes.get_last_error())
        kernel32.CloseHandle(handle)
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_mutex_wait_failed", error)
    _ACTIVE_ACCESS_PROBE_PROTOCOLS.add(protocol_id)
    try:
        yield
    finally:
        _ACTIVE_ACCESS_PROBE_PROTOCOLS.discard(protocol_id)
        if protocol_id in _QUARANTINED_ACCESS_PROBE_PROTOCOLS:
            _ABANDONED_ACCESS_PROBE_MUTEXES[protocol_id] = handle
        else:
            release_ok = bool(kernel32.ReleaseMutex(handle))
            if not release_ok:
                error = int(ctypes.get_last_error())
                _ABANDONED_ACCESS_PROBE_MUTEXES[protocol_id] = handle
                raise WindowsAppContainerAccessError(
                    "appcontainer_access_probe_mutex_release_failed", error)
            close_ok = bool(kernel32.CloseHandle(handle))
            if not close_ok:
                error = int(ctypes.get_last_error())
                raise WindowsAppContainerAccessError(
                    "appcontainer_access_probe_mutex_close_failed", error)


class _FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
    _fields_ = [("FileAttributes", wintypes.DWORD), ("ReparseTag", wintypes.DWORD)]


class _FILE_ID_INFO(ctypes.Structure):
    _fields_ = [("VolumeSerialNumber", ctypes.c_ulonglong),
        ("FileId", ctypes.c_ubyte * 16)]


def probe_condition_worker_baseline_branch_roots(
        manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Measure owner-root access and peer-root denial without writing branch data."""
    if os.name != "nt":
        raise WindowsAppContainerAccessError(
            "appcontainer_baseline_branch_probe_windows_only")
    root_names = {"state", "history", "session", "journal"}
    if (not isinstance(manifest, Mapping)
            or manifest.get("schema_version") !=
                "sentientos.durable_learning_worker_baseline_runtime_manifest:v2"
            or not isinstance(manifest.get("roots"), Mapping)
            or set(manifest["roots"]) != root_names
            or not isinstance(manifest.get("peer_roots"), Mapping)
            or set(manifest["peer_roots"]) != root_names):
        raise WindowsAppContainerAccessError(
            "appcontainer_baseline_branch_probe_manifest_invalid")
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise WindowsAppContainerAccessError(
            "appcontainer_baseline_branch_probe_api_unavailable")
    kernel32 = loader("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE,
        ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value

    def open_directory(row: Mapping[str, Any]) -> tuple[int | None, int | None]:
        handle = kernel32.CreateFileW(row["path"], 0x00000001 | 0x00000080,
            0x1 | 0x2 | 0x4, None, 3, 0x02000000, None)
        if not handle or handle == invalid:
            return None, int(ctypes.get_last_error())
        return int(handle), None

    results: dict[str, dict[str, Any]] = {}
    for name in sorted(root_names):
        own = manifest["roots"][name]
        peer = manifest["peer_roots"][name]
        own_handle, own_error = open_directory(own)
        own_identity_matched = False
        own_directory_confirmed = False
        observed_identity: dict[str, Any] | None = None
        own_close_succeeded: bool | None = None
        if own_handle is not None:
            handle = ctypes.c_void_p(own_handle)
            tag = _FILE_ATTRIBUTE_TAG_INFO()
            file_id = _FILE_ID_INFO()
            if (kernel32.GetFileInformationByHandleEx(handle, 9,
                    ctypes.byref(tag), ctypes.sizeof(tag))
                    and kernel32.GetFileInformationByHandleEx(handle, 18,
                        ctypes.byref(file_id), ctypes.sizeof(file_id))):
                own_directory_confirmed = bool(
                    tag.FileAttributes & 0x10
                    and not tag.FileAttributes & 0x400)
                observed_identity = {"volume_serial": int(
                    file_id.VolumeSerialNumber),
                    "file_id_hex": bytes(file_id.FileId).hex()}
                own_identity_matched = (own_directory_confirmed
                    and observed_identity == own["identity"])
            own_close_succeeded = bool(kernel32.CloseHandle(handle))

        peer_handle, peer_error = open_directory(peer)
        peer_denied = peer_handle is None and peer_error == 5
        peer_close_succeeded: bool | None = None
        if peer_handle is not None:
            peer_close_succeeded = bool(kernel32.CloseHandle(
                ctypes.c_void_p(peer_handle)))
        results[name] = {"own_expected_identity": dict(own["identity"]),
            "own_observed_identity": observed_identity,
            "peer_expected_identity": dict(peer["identity"]),
            "own_root_opened": own_handle is not None,
            "own_root_identity_matched": own_identity_matched,
            "own_root_is_directory": own_directory_confirmed,
            "own_root_close_succeeded": own_close_succeeded,
            "own_root_winerror": own_error,
            "peer_root_open_denied": peer_denied,
            "peer_root_handle_closed": peer_close_succeeded,
            "peer_root_winerror": peer_error}
    matrix_verified = all(row["own_root_opened"]
        and row["own_root_identity_matched"]
        and row["own_root_is_directory"]
        and row["own_root_close_succeeded"] is True
        and row["peer_root_open_denied"]
        and row["peer_root_winerror"] == 5
        for row in results.values())
    semantic = {"schema_version":
            "sentientos.windows_appcontainer_baseline_branch_root_access:v1",
        "protocol_id": manifest.get("protocol_id"),
        "condition": manifest.get("condition"),
        "manifest_digest": manifest.get("manifest_digest"),
        "peer_condition": manifest.get("peer_condition"),
        "own_branch_id": manifest.get("branch_id"),
        "peer_branch_id": manifest.get("peer_branch_id"),
        "root_results": results,
        "branch_root_access_matrix_verified": matrix_verified,
        "authority": False}
    return {**semantic, "probe_result_digest": digest_payload(semantic)}


def verify_condition_worker_baseline_branch_root_access_result(value: Any, *,
        manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Check the worker's non-mutating directory open/deny matrix and digest."""
    root_names = {"state", "history", "session", "journal"}
    conditions = {"relevant_experience_available",
        "relevant_experience_withheld"}
    fields = {"schema_version", "protocol_id", "condition",
        "manifest_digest", "peer_condition", "own_branch_id",
        "peer_branch_id", "root_results",
        "branch_root_access_matrix_verified", "authority",
        "probe_result_digest"}
    manifest_roots = (manifest.get("roots")
        if isinstance(manifest, Mapping) else None)
    manifest_peer_roots = (manifest.get("peer_roots")
        if isinstance(manifest, Mapping) else None)
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema_version") !=
                "sentientos.windows_appcontainer_baseline_branch_root_access:v1"
            or not isinstance(manifest, Mapping)
            or manifest.get("schema_version") !=
                "sentientos.durable_learning_worker_baseline_runtime_manifest:v2"
            or not isinstance(manifest_roots, Mapping)
            or set(manifest_roots) != root_names
            or any(not isinstance(manifest_roots[name], Mapping)
                or "identity" not in manifest_roots[name]
                for name in root_names)
            or not isinstance(manifest_peer_roots, Mapping)
            or set(manifest_peer_roots) != root_names
            or any(not isinstance(manifest_peer_roots[name], Mapping)
                or "identity" not in manifest_peer_roots[name]
                for name in root_names)
            or any(value.get(field) != manifest.get(manifest_field)
                for field, manifest_field in (
                    ("protocol_id", "protocol_id"),
                    ("condition", "condition"),
                    ("manifest_digest", "manifest_digest"),
                    ("peer_condition", "peer_condition"),
                    ("own_branch_id", "branch_id"),
                    ("peer_branch_id", "peer_branch_id")))
            or value.get("condition") not in conditions
            or value.get("peer_condition") not in conditions
            or value.get("condition") == value.get("peer_condition")
            or not isinstance(value.get("own_branch_id"), str)
            or not isinstance(value.get("peer_branch_id"), str)
            or value.get("authority") is not False
            or not isinstance(value.get("root_results"), Mapping)
            or set(value["root_results"]) != root_names):
        raise WindowsAppContainerAccessError(
            "appcontainer_baseline_branch_probe_result_invalid")
    verified = True
    for name in root_names:
        row = value["root_results"][name]
        own_expected = manifest_roots[name]["identity"]
        peer_expected = manifest_peer_roots[name]["identity"]
        for expected_identity in (own_expected, peer_expected):
            if (not isinstance(expected_identity, Mapping)
                    or set(expected_identity) != {"volume_serial", "file_id_hex"}
                    or type(expected_identity.get("volume_serial")) is not int
                    or not 0 <= expected_identity["volume_serial"] <=
                        0xFFFFFFFFFFFFFFFF
                    or not isinstance(expected_identity.get("file_id_hex"), str)
                    or re.fullmatch(r"[0-9a-f]{32}",
                        expected_identity["file_id_hex"]) is None):
                raise WindowsAppContainerAccessError(
                    "appcontainer_baseline_branch_probe_identity_invalid")
        if (not isinstance(row, Mapping)
                or set(row) != {"own_expected_identity",
                    "own_observed_identity", "peer_expected_identity",
                    "own_root_opened", "own_root_identity_matched",
                    "own_root_is_directory", "own_root_close_succeeded",
                    "own_root_winerror", "peer_root_open_denied",
                    "peer_root_handle_closed", "peer_root_winerror"}
                or row.get("own_expected_identity") != own_expected
                or row.get("peer_expected_identity") != peer_expected
                or type(row.get("own_root_opened")) is not bool
                or type(row.get("own_root_identity_matched")) is not bool
                or type(row.get("own_root_is_directory")) is not bool
                or (row.get("own_root_close_succeeded") is not None
                    and type(row.get("own_root_close_succeeded")) is not bool)
                or row.get("own_observed_identity") is not None
                    and (not isinstance(row["own_observed_identity"], Mapping)
                        or set(row["own_observed_identity"]) !=
                            {"volume_serial", "file_id_hex"}
                        or type(row["own_observed_identity"].get(
                            "volume_serial")) is not int
                        or not 0 <= row["own_observed_identity"][
                            "volume_serial"] <= 0xFFFFFFFFFFFFFFFF
                        or not isinstance(row["own_observed_identity"].get(
                            "file_id_hex"), str)
                        or re.fullmatch(r"[0-9a-f]{32}",
                            row["own_observed_identity"]["file_id_hex"]) is None)
                or row.get("own_root_winerror") is not None
                    and (type(row.get("own_root_winerror")) is not int
                        or not 0 <= row["own_root_winerror"] <= 0xFFFFFFFF)
                or type(row.get("peer_root_open_denied")) is not bool
                or (row.get("peer_root_handle_closed") is not None
                    and type(row.get("peer_root_handle_closed")) is not bool)
                or row.get("peer_root_winerror") is not None
                    and (type(row.get("peer_root_winerror")) is not int
                        or not 0 <= row["peer_root_winerror"] <= 0xFFFFFFFF)):
            raise WindowsAppContainerAccessError(
                "appcontainer_baseline_branch_probe_root_result_invalid")
        if (row["own_root_opened"]
                and (row["own_root_winerror"] is not None
                    or row["own_root_close_succeeded"] is None)):
            raise WindowsAppContainerAccessError(
                "appcontainer_baseline_branch_probe_own_open_state_invalid")
        if (not row["own_root_opened"]
                and (row["own_root_winerror"] is None
                    or row["own_root_close_succeeded"] is not None
                    or row["own_observed_identity"] is not None
                    or row["own_root_identity_matched"]
                    or row["own_root_is_directory"])):
            raise WindowsAppContainerAccessError(
                "appcontainer_baseline_branch_probe_own_open_state_invalid")
        if (row["own_root_identity_matched"]
                and (not row["own_root_opened"]
                    or not row["own_root_is_directory"])):
            raise WindowsAppContainerAccessError(
                "appcontainer_baseline_branch_probe_own_identity_state_invalid")
        if row["own_root_is_directory"] and not row["own_root_opened"]:
            raise WindowsAppContainerAccessError(
                "appcontainer_baseline_branch_probe_own_directory_state_invalid")
        if row["peer_root_open_denied"]:
            if (row["peer_root_winerror"] != 5
                    or row["peer_root_handle_closed"] is not None):
                raise WindowsAppContainerAccessError(
                    "appcontainer_baseline_branch_probe_peer_deny_state_invalid")
        elif row["peer_root_winerror"] is None:
            if type(row["peer_root_handle_closed"]) is not bool:
                raise WindowsAppContainerAccessError(
                    "appcontainer_baseline_branch_probe_peer_open_state_invalid")
        elif (row["peer_root_winerror"] == 5
                or row["peer_root_handle_closed"] is not None):
            raise WindowsAppContainerAccessError(
                "appcontainer_baseline_branch_probe_peer_open_state_invalid")
        if row["own_root_identity_matched"]:
            observed = row.get("own_observed_identity")
            if observed != own_expected:
                raise WindowsAppContainerAccessError(
                    "appcontainer_baseline_branch_probe_identity_mismatch")
        verified = (verified and row["own_root_opened"]
            and row["own_root_identity_matched"]
            and row["own_root_is_directory"]
            and row["own_root_close_succeeded"] is True
            and row["peer_root_open_denied"]
            and row["peer_root_winerror"] == 5)
    if (value.get("branch_root_access_matrix_verified") is not verified
            or value.get("probe_result_digest") != digest_payload({
                key: item for key, item in value.items()
                if key != "probe_result_digest"})):
        raise WindowsAppContainerAccessError(
            "appcontainer_baseline_branch_probe_digest_invalid")
    return dict(value)


_ACCESS_PROBE_SCHEMA = "sentientos.windows_appcontainer_access_probe:v1"
_ACCESS_PROBE_PROTOCOL_ID = re.compile(
    r"devexp-durable-learning-protocol-[0-9a-f]{24}")
_ACCESS_PROBE_TARGET_FIELDS = {"path", "volume_serial", "file_id_hex",
    "content_sha256", "content_size"}


def _verify_access_probe_target(value: Any) -> dict[str, Any]:
    if (not isinstance(value, Mapping)
            or set(value) != _ACCESS_PROBE_TARGET_FIELDS
            or not isinstance(value.get("path"), str)
            or not Path(value["path"]).is_absolute()
            or "\0" in value["path"] or len(value["path"]) > 2048
            or type(value.get("volume_serial")) is not int
            or not 0 <= value["volume_serial"] <= 0xFFFFFFFFFFFFFFFF
            or not isinstance(value.get("file_id_hex"), str)
            or re.fullmatch(r"[0-9a-f]{32}", value["file_id_hex"]) is None
            or not isinstance(value.get("content_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}",
                value["content_sha256"]) is None
            or type(value.get("content_size")) is not int
            or not 1 <= value["content_size"] <= 4096):
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_target_invalid")
    return dict(value)


def verify_condition_worker_access_probe_manifest(value: Any, *,
        protocol_id: str, condition: str,
        appcontainer_sid: str) -> dict[str, Any]:
    """Verify a closed startup manifest naming this worker's three sentinels."""
    conditions = {"relevant_experience_available",
        "relevant_experience_withheld"}
    fields = {"schema_version", "protocol_id", "condition",
        "appcontainer_sid", "own_condition", "own_sentinel",
        "peer_condition", "peer_sentinel", "scorer_sentinel",
        "authority", "manifest_digest"}
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema_version") != _ACCESS_PROBE_SCHEMA
            or not isinstance(protocol_id, str)
            or _ACCESS_PROBE_PROTOCOL_ID.fullmatch(protocol_id) is None
            or value.get("protocol_id") != protocol_id
            or condition not in conditions
            or value.get("condition") != condition
            or not isinstance(appcontainer_sid, str)
            or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+",
                appcontainer_sid) is None
            or not isinstance(value.get("appcontainer_sid"), str)
            or value["appcontainer_sid"].casefold() !=
                appcontainer_sid.casefold()
            or value.get("authority") is not False):
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_manifest_invalid")
    own_condition = value.get("own_condition")
    peer_condition = value.get("peer_condition")
    if (own_condition != condition
            or peer_condition not in conditions
            or peer_condition == condition):
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_condition_binding_invalid")
    own = _verify_access_probe_target(value.get("own_sentinel"))
    peer = _verify_access_probe_target(value.get("peer_sentinel"))
    scorer = _verify_access_probe_target(value.get("scorer_sentinel"))
    paths = [target["path"].casefold() for target in (own, peer, scorer)]
    object_ids = {(target["volume_serial"], target["file_id_hex"])
        for target in (own, peer, scorer)}
    if len(set(paths)) != 3 or len(object_ids) != 3:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_target_collision")
    semantic = {key: item for key, item in value.items()
        if key != "manifest_digest"}
    if value.get("manifest_digest") != digest_payload(semantic):
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_manifest_digest_invalid")
    return {**semantic, "own_sentinel": own, "peer_sentinel": peer,
        "scorer_sentinel": scorer,
        "manifest_digest": value["manifest_digest"]}


def build_condition_worker_access_probe_manifest(*, protocol_id: str,
        condition: str, appcontainer_sid: str,
        own_sentinel: Mapping[str, Any],
        peer_sentinel: Mapping[str, Any],
        scorer_sentinel: Mapping[str, Any]) -> dict[str, Any]:
    """Create a digest-bound worker startup manifest from pinned sentinels."""
    conditions = ("relevant_experience_available",
        "relevant_experience_withheld")
    if condition not in conditions:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_condition_invalid")
    peer_condition = next(value for value in conditions if value != condition)
    semantic = {"schema_version": _ACCESS_PROBE_SCHEMA,
        "protocol_id": protocol_id, "condition": condition,
        "appcontainer_sid": appcontainer_sid,
        "own_condition": condition,
        "own_sentinel": _verify_access_probe_target(own_sentinel),
        "peer_condition": peer_condition,
        "peer_sentinel": _verify_access_probe_target(peer_sentinel),
        "scorer_sentinel": _verify_access_probe_target(scorer_sentinel),
        "authority": False}
    manifest = {**semantic, "manifest_digest": digest_payload(semantic)}
    return verify_condition_worker_access_probe_manifest(manifest,
        protocol_id=protocol_id, condition=condition,
        appcontainer_sid=appcontainer_sid)


def probe_condition_worker_file_access(manifest: Mapping[str, Any]
        ) -> dict[str, Any]:
    """Open own/peer/scorer sentinels under this process's actual token.

    The worker report is not independent isolation proof. A supervisor must
    bind its digest to the observed process and independently recheck sentinel
    identities and post-probe contents before promoting any gate.
    """
    if os.name != "nt":
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_windows_only")
    package_sid = manifest.get("appcontainer_sid") if isinstance(
        manifest, Mapping) else None
    checked = verify_condition_worker_access_probe_manifest(manifest,
        protocol_id=(manifest.get("protocol_id") if isinstance(
            manifest, Mapping) else ""),
        condition=(manifest.get("condition") if isinstance(
            manifest, Mapping) else ""), appcontainer_sid=package_sid)
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_api_unavailable")
    kernel32 = loader("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE,
        ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong,
        ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD]
    kernel32.SetFilePointerEx.restype = wintypes.BOOL
    kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel32.FlushFileBuffers.restype = wintypes.BOOL

    invalid = ctypes.c_void_p(-1).value
    def open_target(target: Mapping[str, Any]) -> tuple[int | None, int | None]:
        handle = kernel32.CreateFileW(target["path"], 0x80000000 | 0x40000000,
            0x1 | 0x2 | 0x4, None, 3, 0x00200000, None)
        if not handle or handle == invalid:
            return None, int(ctypes.get_last_error())
        return int(handle), None

    own = checked["own_sentinel"]
    own_handle, own_error = open_target(own)
    own_report: dict[str, Any] = {"opened_read_write": own_handle is not None,
        "expected_identity_matched": False, "read_digest_matched": False,
        "end_of_file_verified": False,
        "write_same_bytes_succeeded": False, "flush_succeeded": False,
        "winerror": own_error}
    if own_handle is not None:
        try:
            handle = ctypes.c_void_p(own_handle)
            tag = _FILE_ATTRIBUTE_TAG_INFO()
            file_id = _FILE_ID_INFO()
            if (kernel32.GetFileInformationByHandleEx(handle, 9,
                    ctypes.byref(tag), ctypes.sizeof(tag))
                    and kernel32.GetFileInformationByHandleEx(handle, 18,
                        ctypes.byref(file_id), ctypes.sizeof(file_id))):
                own_report["expected_identity_matched"] = (
                    int(file_id.VolumeSerialNumber) == own["volume_serial"]
                    and bytes(file_id.FileId).hex() == own["file_id_hex"]
                    and not tag.FileAttributes & (0x10 | 0x400))
            length = own["content_size"]
            buffer = ctypes.create_string_buffer(length)
            count = wintypes.DWORD()
            read_ok = kernel32.ReadFile(handle, buffer, length,
                ctypes.byref(count), None) and count.value == length
            read_bytes = buffer.raw[:count.value] if read_ok else b""
            own_report["read_digest_matched"] = (read_ok and
                hashlib.sha256(read_bytes).hexdigest() == own["content_sha256"])
            if read_ok:
                trailing = ctypes.create_string_buffer(1)
                trailing_count = wintypes.DWORD()
                own_report["end_of_file_verified"] = bool(
                    kernel32.ReadFile(handle, trailing, 1,
                        ctypes.byref(trailing_count), None)
                    and trailing_count.value == 0)
            if (kernel32.SetFilePointerEx(handle, 0, None, 0) and read_ok
                    and own_report["expected_identity_matched"]
                    and own_report["read_digest_matched"]
                    and own_report["end_of_file_verified"]):
                written = wintypes.DWORD()
                own_report["write_same_bytes_succeeded"] = bool(
                    kernel32.WriteFile(handle, buffer, length,
                        ctypes.byref(written), None)
                    and written.value == length)
                own_report["flush_succeeded"] = bool(
                    own_report["write_same_bytes_succeeded"]
                    and kernel32.FlushFileBuffers(handle))
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(own_handle))

    def denied(target: Mapping[str, Any]) -> dict[str, Any]:
        handle, error = open_target(target)
        if handle is not None:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        return {"open_denied": handle is None and error == 5,
            "winerror": error}

    peer_report = denied(checked["peer_sentinel"])
    scorer_report = denied(checked["scorer_sentinel"])
    semantic = {"schema_version":
            "sentientos.windows_appcontainer_access_probe_result:v1",
        "protocol_id": checked["protocol_id"],
        "condition": checked["condition"],
        "appcontainer_sid": checked["appcontainer_sid"],
        "manifest_digest": checked["manifest_digest"],
        "own_sentinel": own_report, "peer_sentinel": peer_report,
        "scorer_sentinel": scorer_report,
        "worker_reported_probe_complete": (
            own_report["opened_read_write"]
            and own_report["expected_identity_matched"]
            and own_report["read_digest_matched"]
            and own_report["end_of_file_verified"]
            and own_report["write_same_bytes_succeeded"]
            and own_report["flush_succeeded"]
            and peer_report["open_denied"]
            and scorer_report["open_denied"]),
        "supervisor_verification_required": True,
        "authority": False}
    return {**semantic, "probe_result_digest": digest_payload(semantic)}


def verify_condition_worker_access_probe_sentinels(manifest: Mapping[str, Any],
        *, worker_exit_confirmed: bool) -> dict[str, Any]:
    """Read back all pinned sentinels after the worker has exited.

    This is supervisor-side content and identity evidence. The caller must
    establish worker termination before invoking it; the report deliberately
    does not promote process or filesystem isolation gates.
    """
    if os.name != "nt":
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_windows_only")
    if worker_exit_confirmed is not True:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_worker_exit_unconfirmed")
    package_sid = manifest.get("appcontainer_sid") if isinstance(
        manifest, Mapping) else None
    checked = verify_condition_worker_access_probe_manifest(manifest,
        protocol_id=(manifest.get("protocol_id") if isinstance(
            manifest, Mapping) else ""),
        condition=(manifest.get("condition") if isinstance(
            manifest, Mapping) else ""), appcontainer_sid=package_sid)
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_probe_api_unavailable")
    kernel32 = loader("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE,
        ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.ReadFile.restype = wintypes.BOOL

    invalid = ctypes.c_void_p(-1).value
    def inspect(target: Mapping[str, Any]) -> dict[str, Any]:
        handle = kernel32.CreateFileW(target["path"], 0x80000000, 0x1,
            None, 3, 0x00200000, None)
        if not handle or handle == invalid:
            return {"opened_read_only": False,
                "identity_matched": False, "content_digest_matched": False,
                "end_of_file_verified": False,
                "winerror": int(ctypes.get_last_error())}
        try:
            tag = _FILE_ATTRIBUTE_TAG_INFO()
            file_id = _FILE_ID_INFO()
            identity_ok = bool(
                kernel32.GetFileInformationByHandleEx(handle, 9,
                    ctypes.byref(tag), ctypes.sizeof(tag))
                and kernel32.GetFileInformationByHandleEx(handle, 18,
                    ctypes.byref(file_id), ctypes.sizeof(file_id))
                and int(file_id.VolumeSerialNumber) == target["volume_serial"]
                and bytes(file_id.FileId).hex() == target["file_id_hex"]
                and not tag.FileAttributes & (0x10 | 0x400))
            length = target["content_size"]
            buffer = ctypes.create_string_buffer(length)
            count = wintypes.DWORD()
            read_ok = bool(kernel32.ReadFile(handle, buffer, length,
                ctypes.byref(count), None) and count.value == length)
            content_ok = bool(read_ok and hashlib.sha256(
                buffer.raw[:count.value]).hexdigest() == target["content_sha256"])
            trailing = ctypes.create_string_buffer(1)
            trailing_count = wintypes.DWORD()
            eof_ok = bool(read_ok and kernel32.ReadFile(handle, trailing, 1,
                ctypes.byref(trailing_count), None)
                and trailing_count.value == 0)
            return {"opened_read_only": True,
                "identity_matched": identity_ok,
                "content_digest_matched": content_ok,
                "end_of_file_verified": eof_ok, "winerror": None}
        finally:
            kernel32.CloseHandle(handle)

    results = {name: inspect(checked[field]) for name, field in (
        ("own_sentinel", "own_sentinel"),
        ("peer_sentinel", "peer_sentinel"),
        ("scorer_sentinel", "scorer_sentinel"))}
    semantic = {"schema_version":
            "sentientos.windows_appcontainer_access_probe_supervisor_check:v1",
        "protocol_id": checked["protocol_id"],
        "condition": checked["condition"],
        "manifest_digest": checked["manifest_digest"],
        "sentinels": results,
        "all_sentinel_identities_and_contents_match": all(
            result["opened_read_only"] and result["identity_matched"]
            and result["content_digest_matched"]
            and result["end_of_file_verified"]
            for result in results.values()),
        "worker_exit_confirmed_by_caller": True,
        "process_isolation_verified": False,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}
    return {**semantic, "check_digest": digest_payload(semantic)}


def expected_condition_worker_access_probe_rpc_digest(
        manifest: Mapping[str, Any]) -> str:
    """Compute the RPC result digest for the complete expected allow/deny matrix."""
    package_sid = manifest.get("appcontainer_sid") if isinstance(
        manifest, Mapping) else None
    checked = verify_condition_worker_access_probe_manifest(manifest,
        protocol_id=(manifest.get("protocol_id") if isinstance(
            manifest, Mapping) else ""),
        condition=(manifest.get("condition") if isinstance(
            manifest, Mapping) else ""), appcontainer_sid=package_sid)
    semantic = {"schema_version":
            "sentientos.windows_appcontainer_access_probe_result:v1",
        "protocol_id": checked["protocol_id"],
        "condition": checked["condition"],
        "appcontainer_sid": checked["appcontainer_sid"],
        "manifest_digest": checked["manifest_digest"],
        "own_sentinel": {"opened_read_write": True,
            "expected_identity_matched": True,
            "read_digest_matched": True,
            "end_of_file_verified": True,
            "write_same_bytes_succeeded": True,
            "flush_succeeded": True, "winerror": None},
        "peer_sentinel": {"open_denied": True, "winerror": 5},
        "scorer_sentinel": {"open_denied": True, "winerror": 5},
        "worker_reported_probe_complete": True,
        "supervisor_verification_required": True,
        "authority": False}
    report = {**semantic, "probe_result_digest": digest_payload(semantic)}
    raw = json.dumps(report, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")
    return hashlib.sha256(raw).hexdigest()


class _TRUSTEE_W(ctypes.Structure):
    _fields_ = [("pMultipleTrustee", ctypes.c_void_p),
        ("MultipleTrusteeOperation", ctypes.c_int), ("TrusteeForm", ctypes.c_int),
        ("TrusteeType", ctypes.c_int), ("ptstrName", ctypes.c_void_p)]


class _EXPLICIT_ACCESS_W(ctypes.Structure):
    _fields_ = [("grfAccessPermissions", wintypes.DWORD),
        ("grfAccessMode", ctypes.c_int), ("grfInheritance", wintypes.DWORD),
        ("Trustee", _TRUSTEE_W)]


class _ACL_SIZE_INFORMATION(ctypes.Structure):
    _fields_ = [("AceCount", wintypes.DWORD),
        ("AclBytesInUse", wintypes.DWORD), ("AclBytesFree", wintypes.DWORD)]


def _winerror(code: str) -> WindowsAppContainerAccessError:
    return WindowsAppContainerAccessError(code, int(ctypes.get_last_error()))


def _rights(policy: str) -> tuple[int, int]:
    read_control_sync = 0x00020000 | 0x00100000
    read_attributes_ea = 0x00000080 | 0x00000008
    if policy == "condition_receipt_read":
        directory_mask = (0x00000001 | 0x00000020 | read_attributes_ea
            | read_control_sync)
        file_mask = 0x00000001 | read_attributes_ea | read_control_sync
        return directory_mask, file_mask
    if policy == "runtime_read_execute":
        directory_mask = (0x00000001 | 0x00000020 | read_attributes_ea
            | read_control_sync)
        file_mask = (0x00000001 | 0x00000020 | read_attributes_ea
            | read_control_sync)
        return directory_mask, file_mask
    if policy == "branch_state_modify":
        directory_mask = (0x00000001 | 0x00000002 | 0x00000004 | 0x00000008
            | 0x00000010 | 0x00000020 | 0x00000040 | 0x00000080
            | 0x00000100 | 0x00010000 | read_control_sync)
        file_mask = (0x00000001 | 0x00000002 | 0x00000004 | 0x00000008
            | 0x00000010 | 0x00000080 | 0x00000100 | 0x00010000
            | read_control_sync)
        return directory_mask, file_mask
    raise WindowsAppContainerAccessError("appcontainer_access_policy_invalid")


def _verify_package_aces(dacl: int, package_sid: int, *,
        directory_mask: int, file_mask: int, advapi32: Any) -> dict[str, bool]:
    get_acl_info = advapi32.GetAclInformation
    get_acl_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.c_int]
    get_acl_info.restype = wintypes.BOOL
    get_ace = advapi32.GetAce
    get_ace.argtypes = [ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p)]
    get_ace.restype = wintypes.BOOL
    equal_sid = advapi32.EqualSid
    equal_sid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    equal_sid.restype = wintypes.BOOL
    is_valid_sid = advapi32.IsValidSid
    is_valid_sid.argtypes = [ctypes.c_void_p]
    is_valid_sid.restype = wintypes.BOOL
    sid_length = advapi32.GetLengthSid
    sid_length.argtypes = [ctypes.c_void_p]
    sid_length.restype = wintypes.DWORD

    info = _ACL_SIZE_INFORMATION()
    if not get_acl_info(dacl, ctypes.byref(info), ctypes.sizeof(info), 2):
        raise _winerror("appcontainer_access_acl_structure_invalid")
    if info.AceCount > 4096:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_acl_ace_bound_exceeded")
    directory_allow = False
    file_allow = False
    package_deny = False
    for index in range(info.AceCount):
        ace = ctypes.c_void_p()
        if not get_ace(dacl, index, ctypes.byref(ace)) or not ace.value:
            raise _winerror("appcontainer_access_acl_ace_unavailable")
        header = ctypes.string_at(ace, 4)
        ace_type, ace_flags = header[0], header[1]
        ace_size = int.from_bytes(header[2:4], "little")
        if ace_size < 16:
            raise WindowsAppContainerAccessError(
                "appcontainer_access_acl_ace_size_invalid")
        if ace_type not in {0, 1}:  # allow or deny only; object/conditional ACEs fail closed
            raise WindowsAppContainerAccessError(
                "appcontainer_access_acl_ace_form_unsupported")
        mask = int.from_bytes(ctypes.string_at(ace, 8)[4:8], "little")
        sid_ptr = ctypes.c_void_p(ace.value + 8)
        if (not is_valid_sid(sid_ptr)
                or sid_length(sid_ptr) > ace_size - 8):
            raise WindowsAppContainerAccessError(
                "appcontainer_access_acl_sid_invalid")
        if not equal_sid(sid_ptr, package_sid):
            continue
        if ace_type == 1 and mask & (directory_mask | file_mask):
            package_deny = True
        if ace_type == 0:
            if mask & ~(directory_mask | file_mask):
                raise WindowsAppContainerAccessError(
                    "appcontainer_access_package_rights_exceeded")
            if (mask & directory_mask) == directory_mask and not ace_flags & 0x08:
                directory_allow = True
            if ((mask & file_mask) == file_mask
                    and ace_flags & (0x01 | 0x08) == (0x01 | 0x08)):
                file_allow = True
    return {"directory_allow_ace_present": directory_allow,
        "file_inherit_allow_ace_present": file_allow,
        "package_sid_deny_ace_present": package_deny}


def grant_appcontainer_directory_access(*, root: Path,
        expected_directory_identity: tuple[int, bytes], appcontainer_sid: str,
        access_policy: str) -> dict[str, Any]:
    """Merge one package-SID grant into an identity-pinned private directory.

    ``runtime_read_execute`` grants only read/traverse/execute rights.
    ``condition_receipt_read`` grants receipt-file read and directory traversal
    without file execute rights. ``branch_state_modify`` grants data and
    directory modification rights but excludes execute, WRITE_DAC, and WRITE_OWNER. Inheritable ACEs are applied
    by Windows to existing descendants as well as future descendants. A live
    worker must still prove expected allow and deny outcomes before this grant
    can count as isolation evidence.
    """
    if (os.name != "nt"
            or not isinstance(appcontainer_sid, str)
            or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+", appcontainer_sid) is None
            or not isinstance(expected_directory_identity, tuple)
            or len(expected_directory_identity) != 2
            or type(expected_directory_identity[0]) is not int
            or not 0 <= expected_directory_identity[0] <= 0xFFFFFFFFFFFFFFFF
            or not isinstance(expected_directory_identity[1], bytes)
            or len(expected_directory_identity[1]) != 16):
        raise WindowsAppContainerAccessError(
            "appcontainer_access_arguments_invalid")
    directory_mask, file_mask = _rights(access_policy)
    root = Path(root)
    mutation_state = "not_attempted"
    try:
        observed_identity = (
            observe_directory_identity(root)
            if access_policy == "runtime_read_execute" else
            observe_private_directory_identity(root,
                permitted_appcontainer_sid=appcontainer_sid))
        if observed_identity != expected_directory_identity:
            raise WindowsAppContainerAccessError(
                "appcontainer_access_directory_identity_mismatch")
    except WindowsAppContainerAccessError:
        raise
    except (OSError, ValueError) as exc:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_directory_unavailable") from exc

    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise WindowsAppContainerAccessError(
            "appcontainer_access_win32_api_unavailable")
    kernel32 = loader("kernel32", use_last_error=True)
    advapi32 = loader("advapi32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE,
        ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p)]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    advapi32.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int,
        wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
    advapi32.GetSecurityInfo.restype = wintypes.DWORD
    advapi32.SetEntriesInAclW.argtypes = [wintypes.ULONG, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.SetEntriesInAclW.restype = wintypes.DWORD
    advapi32.SetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int,
        wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p]
    advapi32.SetSecurityInfo.restype = wintypes.DWORD

    invalid_handle = ctypes.c_void_p(-1).value
    handle = kernel32.CreateFileW(str(root),
        0x00000080 | 0x00020000 | 0x00040000,
        0x00000001, None, 3, 0x02000000 | 0x00200000, None)
    if not handle or handle == invalid_handle:
        raise _winerror("appcontainer_access_directory_open_failed")
    package_sid = ctypes.c_void_p()
    security_descriptor = ctypes.c_void_p()
    old_dacl = ctypes.c_void_p()
    new_dacl = ctypes.c_void_p()
    try:
        tag = _FILE_ATTRIBUTE_TAG_INFO()
        file_id = _FILE_ID_INFO()
        if (not kernel32.GetFileInformationByHandleEx(handle, 9,
                ctypes.byref(tag), ctypes.sizeof(tag))
                or not kernel32.GetFileInformationByHandleEx(handle, 18,
                    ctypes.byref(file_id), ctypes.sizeof(file_id))):
            raise _winerror("appcontainer_access_directory_metadata_unavailable")
        if not tag.FileAttributes & 0x10 or tag.FileAttributes & 0x400:
            raise WindowsAppContainerAccessError(
                "appcontainer_access_directory_target_invalid")
        identity = (int(file_id.VolumeSerialNumber), bytes(file_id.FileId))
        if identity != expected_directory_identity:
            raise WindowsAppContainerAccessError(
                "appcontainer_access_directory_identity_changed")
        if not advapi32.ConvertStringSidToSidW(appcontainer_sid,
                ctypes.byref(package_sid)):
            raise _winerror("appcontainer_access_package_sid_invalid")
        status = advapi32.GetSecurityInfo(handle, 1, 0x4, None, None,
            ctypes.byref(old_dacl), None, ctypes.byref(security_descriptor))
        if status != 0 or not old_dacl.value or not security_descriptor.value:
            raise WindowsAppContainerAccessError(
                "appcontainer_access_existing_dacl_unavailable", int(status))

        trustee = _TRUSTEE_W(None, 0, 0, 0, package_sid.value)
        entries = (_EXPLICIT_ACCESS_W * 2)(
            _EXPLICIT_ACCESS_W(directory_mask, 1, 0x02, trustee),
            _EXPLICIT_ACCESS_W(file_mask, 1, 0x01 | 0x08, trustee))
        status = advapi32.SetEntriesInAclW(2, ctypes.byref(entries), old_dacl,
            ctypes.byref(new_dacl))
        if status != 0 or not new_dacl.value:
            raise WindowsAppContainerAccessError(
                "appcontainer_access_acl_merge_failed", int(status))
        mutation_state = "api_call_outcome_unknown"
        status = advapi32.SetSecurityInfo(handle, 1, 0x4, None, None,
            new_dacl, None)
        if status != 0:
            mutation_state = "api_reported_failure"
            raise WindowsAppContainerAccessError(
                "appcontainer_access_acl_update_failed", int(status),
                mutation_state=mutation_state)
        mutation_state = "api_succeeded_unverified"

        verify_descriptor = ctypes.c_void_p()
        verify_dacl = ctypes.c_void_p()
        try:
            status = advapi32.GetSecurityInfo(handle, 1, 0x4, None, None,
                ctypes.byref(verify_dacl), None,
                ctypes.byref(verify_descriptor))
            if status != 0 or not verify_dacl.value:
                raise WindowsAppContainerAccessError(
                    "appcontainer_access_acl_reload_failed", int(status))
            ace_status = _verify_package_aces(verify_dacl, package_sid,
                directory_mask=directory_mask, file_mask=file_mask,
                advapi32=advapi32)
            if (not ace_status["directory_allow_ace_present"]
                    or not ace_status["file_inherit_allow_ace_present"]
                    or ace_status["package_sid_deny_ace_present"]):
                raise WindowsAppContainerAccessError(
                    "appcontainer_access_acl_postcondition_failed")
            mutation_state = "acl_verified"
        finally:
            if verify_descriptor.value:
                kernel32.LocalFree(verify_descriptor)
        return {"schema_version": "sentientos.windows_appcontainer_directory_acl:v1",
            "directory_identity": {"volume_serial": identity[0],
                "file_id_hex": identity[1].hex()},
            "package_sid": appcontainer_sid,
            "access_policy": access_policy,
            "directory_allow_ace_present": True,
            "file_inherit_allow_ace_present": True,
            "package_sid_deny_ace_present": False,
            "effective_access_verified": False,
            "peer_denial_verified": False,
            "retention_contrast_eligible": False,
            "authority": False}
    except Exception as exc:
        if isinstance(exc, WindowsAppContainerAccessError):
            exc.mutation_state = mutation_state
            raise
        raise WindowsAppContainerAccessError(
            "appcontainer_access_runtime_operation_failed",
            getattr(exc, "winerror", None),
            mutation_state=mutation_state) from exc
    finally:
        if new_dacl.value:
            kernel32.LocalFree(new_dacl)
        if security_descriptor.value:
            kernel32.LocalFree(security_descriptor)
        if package_sid.value:
            kernel32.LocalFree(package_sid)
        if not kernel32.CloseHandle(handle):
            raise WindowsAppContainerAccessError(
                "appcontainer_access_directory_close_failed",
                int(ctypes.get_last_error()), mutation_state=mutation_state)


def grant_condition_worker_runtime_read_execute(*, protocol_id: str,
        profile_pair: Mapping[str, Any],
        runtime_roots: Mapping[str, Path]) -> dict[str, Any]:
    """Grant both condition SIDs read/execute on an explicit runtime root set.

    All roots are resolved and identity-pinned before any ACL is changed.
    Grants are directory-scoped and inheritable; a partial failure is returned
    as evidence and must prevent worker launch. This does not prove effective
    access or peer denial.
    """
    from .windows_appcontainer_profile import (
        verify_condition_appcontainer_profile_pair_result)

    if (os.name != "nt" or not isinstance(profile_pair, Mapping)
            or not isinstance(runtime_roots, Mapping)
            or not runtime_roots or len(runtime_roots) > 64):
        raise WindowsAppContainerAccessError(
            "appcontainer_runtime_access_arguments_invalid")
    try:
        checked_pair = verify_condition_appcontainer_profile_pair_result(
            dict(profile_pair), protocol_id=protocol_id)
    except (TypeError, ValueError) as exc:
        raise WindowsAppContainerAccessError(
            "appcontainer_runtime_profile_pair_invalid") from exc

    normalized: dict[str, tuple[Path, tuple[int, bytes]]] = {}
    name_keys: set[str] = set()
    for name, value in runtime_roots.items():
        if (not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name) is None
                or name.casefold() in name_keys
                or not isinstance(value, Path)
                or not value.is_absolute()):
            raise WindowsAppContainerAccessError(
                "appcontainer_runtime_root_entry_invalid")
        name_keys.add(name.casefold())
        try:
            root = value.resolve(strict=True)
            if not root.is_dir():
                raise ValueError("runtime_root_not_directory")
            identity = observe_directory_identity(root)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise WindowsAppContainerAccessError(
                "appcontainer_runtime_root_unavailable") from exc
        normalized[name] = (root, identity)

    path_components = {name: tuple(part.casefold()
        for part in root.parts) for name, (root, _) in normalized.items()}
    names = tuple(normalized)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1:]:
            left = path_components[left_name]
            right = path_components[right_name]
            if (left == right or left == right[:len(left)]
                    or right == left[:len(right)]):
                raise WindowsAppContainerAccessError(
                    "appcontainer_runtime_roots_overlap")

    conditions = ("relevant_experience_available",
        "relevant_experience_withheld")
    grants: dict[str, dict[str, Any]] = {}
    for condition, profile in checked_pair["condition_profiles"].items():
        sid = profile["appcontainer_sid"]
        condition_grants: dict[str, Any] = {}
        for name, (root, identity) in normalized.items():
            try:
                grant = grant_appcontainer_directory_access(root=root,
                    expected_directory_identity=identity,
                    appcontainer_sid=sid,
                    access_policy="runtime_read_execute")
                condition_grants[name] = {"status": "applied",
                    "grant": grant}
            except (OSError, TypeError, ValueError) as exc:
                condition_grants[name] = {"status": "failed",
                    "reason_code": getattr(exc, "code", "runtime_acl_grant_failed"),
                    "mutation_state": getattr(exc, "mutation_state",
                        "api_call_outcome_unknown" if getattr(exc, "winerror", None)
                            is not None else "not_attempted"),
                    "authority": False}
        grants[condition] = condition_grants
    all_applied = (set(grants) == set(conditions)
        and all(set(grants[condition]) == set(normalized)
            and all(item.get("status") == "applied"
                for item in grants[condition].values())
            for condition in conditions))
    semantic = {"schema_version":
            "sentientos.windows_appcontainer_runtime_access_setup:v1",
        "protocol_id": protocol_id,
        "profile_pair_digest": checked_pair["profile_pair_digest"],
        "runtime_roots": {name: {"path": str(root),
            "volume_serial": identity[0], "file_id_hex": identity[1].hex()}
            for name, (root, identity) in normalized.items()},
        "grants_by_condition": grants,
        "all_requested_grants_applied": all_applied,
        "effective_access_verified": False,
        "peer_denial_verified": False,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}
    return {**semantic, "setup_digest": digest_payload(semantic)}


def grant_condition_worker_baseline_read_access(*, protocol: Mapping[str, Any],
        profile_pair: Mapping[str, Any],
        baseline_manifests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Grant each worker read-only access to its own four baseline roots.

    Unlike the shared runtime grant, this never grants one condition SID access
    to the peer's state, history, session, or journal. Effective access and
    peer denial still require a live worker probe.
    """
    from .durable_developmental_learning_experiment import _CONDITIONS
    from .durable_learning_condition_worker_backend import (
        verify_condition_worker_baseline_runtime_manifest)
    from .windows_appcontainer_profile import (
        verify_condition_appcontainer_profile_pair_result)

    if (os.name != "nt" or not isinstance(protocol, Mapping)
            or not isinstance(profile_pair, Mapping)
            or not isinstance(baseline_manifests, Mapping)
            or set(baseline_manifests) != set(_CONDITIONS)):
        raise WindowsAppContainerAccessError(
            "appcontainer_baseline_access_arguments_invalid")
    protocol_id = protocol.get("protocol_id")
    protocol_digest = protocol.get("protocol_digest")
    try:
        checked_pair = verify_condition_appcontainer_profile_pair_result(
            dict(profile_pair), protocol_id=protocol_id)
        checked_manifests = {condition:
            verify_condition_worker_baseline_runtime_manifest(
                baseline_manifests[condition], protocol=protocol,
                protocol_id=protocol_id, protocol_digest=protocol_digest,
                condition=condition,
                appcontainer_sid=checked_pair["condition_profiles"][condition][
                    "appcontainer_sid"])
            for condition in _CONDITIONS}
    except (TypeError, ValueError, KeyError) as exc:
        raise WindowsAppContainerAccessError(
            "appcontainer_baseline_access_binding_invalid") from exc

    rows: dict[str, dict[str, tuple[Path, tuple[int, bytes]]]] = {}
    all_roots: list[Path] = []
    all_identity_keys: list[tuple[int, bytes]] = []
    for condition in _CONDITIONS:
        rows[condition] = {}
        for name, row in checked_manifests[condition]["roots"].items():
            root = Path(row["path"]).resolve(strict=True)
            identity = (row["identity"]["volume_serial"],
                bytes.fromhex(row["identity"]["file_id_hex"]))
            rows[condition][name] = (root, identity)
            all_roots.append(root)
            all_identity_keys.append(identity)
    if len(set(all_identity_keys)) != len(all_identity_keys):
        raise WindowsAppContainerAccessError(
            "appcontainer_baseline_access_root_identity_overlap")
    for index, left in enumerate(all_roots):
        for right in all_roots[index + 1:]:
            if (left == right or left in right.parents or right in left.parents):
                raise WindowsAppContainerAccessError(
                    "appcontainer_baseline_access_roots_overlap")

    grants: dict[str, dict[str, Any]] = {}
    for condition in _CONDITIONS:
        sid = checked_pair["condition_profiles"][condition]["appcontainer_sid"]
        grants[condition] = {}
        for name, (root, identity) in rows[condition].items():
            try:
                report = grant_appcontainer_directory_access(root=root,
                    expected_directory_identity=identity,
                    appcontainer_sid=sid,
                    access_policy="condition_receipt_read")
                grants[condition][name] = {"status": "applied",
                    "grant": report}
            except (OSError, TypeError, ValueError) as exc:
                grants[condition][name] = {"status": "failed",
                    "reason_code": getattr(exc, "code",
                        "baseline_read_acl_grant_failed"),
                    "mutation_state": getattr(exc, "mutation_state",
                        "api_call_outcome_unknown"
                        if getattr(exc, "winerror", None) is not None
                        else "not_attempted"),
                    "authority": False}
    all_applied = all(set(grants.get(condition, {})) ==
        {"state", "history", "session", "journal"}
        and all(item.get("status") == "applied"
            for item in grants[condition].values()) for condition in _CONDITIONS)
    semantic = {"schema_version":
            "sentientos.windows_appcontainer_baseline_read_access_setup:v1",
        "protocol_id": protocol_id,
        "protocol_digest": protocol_digest,
        "profile_pair_digest": checked_pair["profile_pair_digest"],
        "manifest_digest_by_condition": {condition:
            checked_manifests[condition]["manifest_digest"]
            for condition in _CONDITIONS},
        "grants_by_condition": grants,
        "all_requested_grants_applied": all_applied,
        "effective_access_verified": False,
        "peer_denial_verified": False,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}
    return {**semantic, "setup_digest": digest_payload(semantic)}


def grant_condition_worker_recovery_access(*, protocol: Mapping[str, Any],
        profile_pair: Mapping[str, Any],
        recovery_manifests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Grant branch reads and journal writes for bounded recovery workers.

    Each SID receives read/traverse access to its own state, history, and
    session roots. Only its own dedicated operation journal receives modify
    access; peer branch roots are never granted.
    """
    from .durable_developmental_learning_experiment import _CONDITIONS
    from .durable_learning_condition_worker_backend import (
        verify_condition_worker_baseline_runtime_manifest)
    from .windows_appcontainer_profile import (
        verify_condition_appcontainer_profile_pair_result)

    if (os.name != "nt" or not isinstance(protocol, Mapping)
            or not isinstance(profile_pair, Mapping)
            or not isinstance(recovery_manifests, Mapping)
            or set(recovery_manifests) != set(_CONDITIONS)):
        raise WindowsAppContainerAccessError(
            "appcontainer_recovery_access_arguments_invalid")
    protocol_id, protocol_digest = (protocol.get("protocol_id"),
        protocol.get("protocol_digest"))
    try:
        profiles = verify_condition_appcontainer_profile_pair_result(
            dict(profile_pair), protocol_id=protocol_id)
        manifests = {condition:
            verify_condition_worker_baseline_runtime_manifest(
                recovery_manifests[condition], protocol=protocol,
                protocol_id=protocol_id, protocol_digest=protocol_digest,
                condition=condition,
                appcontainer_sid=profiles["condition_profiles"][condition][
                    "appcontainer_sid"])
            for condition in _CONDITIONS}
    except (TypeError, ValueError, KeyError) as exc:
        raise WindowsAppContainerAccessError(
            "appcontainer_recovery_access_binding_invalid") from exc

    rows: dict[str, dict[str, tuple[Path, tuple[int, bytes]]]] = {}
    all_roots: list[Path] = []
    identities: list[tuple[int, bytes]] = []
    for condition in _CONDITIONS:
        rows[condition] = {}
        for name, row in manifests[condition]["roots"].items():
            root = Path(row["path"]).resolve(strict=True)
            identity = (row["identity"]["volume_serial"],
                bytes.fromhex(row["identity"]["file_id_hex"]))
            rows[condition][name] = (root, identity)
            all_roots.append(root)
            identities.append(identity)
    if len(set(identities)) != len(identities):
        raise WindowsAppContainerAccessError(
            "appcontainer_recovery_access_root_identity_overlap")
    for index, left in enumerate(all_roots):
        for right in all_roots[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise WindowsAppContainerAccessError(
                    "appcontainer_recovery_access_roots_overlap")

    grants: dict[str, dict[str, Any]] = {}
    for condition in _CONDITIONS:
        sid = profiles["condition_profiles"][condition]["appcontainer_sid"]
        grants[condition] = {}
        for name, (root, identity) in rows[condition].items():
            policy = "branch_state_modify" if name == "journal" else \
                "condition_receipt_read"
            try:
                report = grant_appcontainer_directory_access(root=root,
                    expected_directory_identity=identity,
                    appcontainer_sid=sid, access_policy=policy)
                grants[condition][name] = {"status": "applied",
                    "access_policy": policy, "grant": report}
            except (OSError, TypeError, ValueError) as exc:
                grants[condition][name] = {"status": "failed",
                    "access_policy": policy,
                    "reason_code": getattr(exc, "code",
                        "recovery_acl_grant_failed"),
                    "mutation_state": getattr(exc, "mutation_state",
                        "api_call_outcome_unknown"
                        if getattr(exc, "winerror", None) is not None
                        else "not_attempted"), "authority": False}
    all_applied = all(set(grants[condition]) ==
        {"state", "history", "session", "journal"}
        and all(row.get("status") == "applied"
            for row in grants[condition].values()) for condition in _CONDITIONS)
    semantic = {"schema_version":
            "sentientos.windows_appcontainer_recovery_access_setup:v1",
        "protocol_id": protocol_id, "protocol_digest": protocol_digest,
        "profile_pair_digest": profiles["profile_pair_digest"],
        "manifest_digest_by_condition": {condition:
            manifests[condition]["manifest_digest"] for condition in _CONDITIONS},
        "grants_by_condition": grants,
        "all_requested_grants_applied": all_applied,
        "effective_access_verified": False, "peer_denial_verified": False,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False, "authority": False}
    return {**semantic, "setup_digest": digest_payload(semantic)}
