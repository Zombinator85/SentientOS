"""Bounded worker-side inventory of an AppContainer's registry storage.

This module must run in the AppContainer profile whose registry state is being
observed. It uses GetAppContainerRegistryLocation instead of an undocumented
HKCU mapping path. It reports typed value digests, never raw value contents,
and does not claim an atomic snapshot or complete profile-state accounting.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import re
from ctypes import wintypes
from typing import Any

if os.name == "nt":
    import winreg
else:
    winreg = None  # type: ignore[assignment]


_PACKAGE_SID = re.compile(r"S-1-15-2-(?:[0-9]+-)*[0-9]+")
_MAX_KEYS = 1024
_MAX_VALUES = 2048
_MAX_DEPTH = 32
_MAX_INVENTORY_BYTES = 524_288
_MAX_SINGLE_VALUE_BYTES = 65_536
_MAX_VALUE_NAME_CHARS = 16384


class WindowsAppContainerRegistryError(ValueError):
    """Registry inventory failed or exceeded its explicit bounds."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":")).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_value_not_canonical") from exc


def _is_canonical_package_sid(value: Any) -> bool:
    if not isinstance(value, str) or _PACKAGE_SID.fullmatch(value) is None:
        return False
    parts = value.split("-")[1:]
    try:
        numbers = [int(part, 10) for part in parts]
    except ValueError:
        return False
    return (all(str(number) == part for number, part in zip(numbers, parts))
        and all(number <= 0xFFFFFFFF for number in numbers[2:]))


def _check_current_package_sid(expected_sid: str) -> tuple[int, int]:
    if os.name != "nt" or not _is_canonical_package_sid(expected_sid):
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_worker_binding_invalid")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    process = kernel32.GetCurrentProcess()
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(process, 0x0008, ctypes.byref(token)):
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_worker_token_unavailable")
    try:
        is_container = wintypes.DWORD()
        returned = wintypes.DWORD()
        if (not advapi32.GetTokenInformation(token, 29,
                ctypes.byref(is_container), ctypes.sizeof(is_container),
                ctypes.byref(returned)) or is_container.value != 1):
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_worker_not_appcontainer")
        sid_size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 31, None, 0,
            ctypes.byref(sid_size))
        if sid_size.value < ctypes.sizeof(ctypes.c_void_p) or sid_size.value > 65_536:
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_worker_sid_size_invalid")
        sid_buffer = ctypes.create_string_buffer(sid_size.value)
        if not advapi32.GetTokenInformation(token, 31, sid_buffer,
                sid_size.value, ctypes.byref(sid_size)):
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_worker_sid_unavailable",
                ctypes.get_last_error())
        sid_pointer = ctypes.cast(sid_buffer,
            ctypes.POINTER(ctypes.c_void_p)).contents.value
        sid_text = wintypes.LPWSTR()
        if (not sid_pointer or not advapi32.ConvertSidToStringSidW(
                ctypes.c_void_p(sid_pointer), ctypes.byref(sid_text))):
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_worker_sid_format_failed",
                ctypes.get_last_error())
        try:
            observed_sid = sid_text.value
        finally:
            kernel32.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        if (not isinstance(observed_sid, str)
                or observed_sid.casefold() != expected_sid.casefold()):
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_worker_sid_mismatch")
        creation, exit_time, kernel_time, user_time = (wintypes.FILETIME()
            for _ in range(4))
        if not kernel32.GetProcessTimes(process, ctypes.byref(creation),
                ctypes.byref(exit_time), ctypes.byref(kernel_time),
                ctypes.byref(user_time)):
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_worker_creation_time_unavailable",
                ctypes.get_last_error())
        process_id = int(kernel32.GetProcessId(process))
        if process_id <= 0:
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_worker_process_id_unavailable")
        created = (int(creation.dwHighDateTime) << 32) | int(
            creation.dwLowDateTime)
        return process_id, created
    finally:
        if not kernel32.CloseHandle(token):
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_worker_token_close_failed",
                ctypes.get_last_error())


def inventory_current_appcontainer_registry(*, expected_appcontainer_sid: str,
        max_depth: int = _MAX_DEPTH, max_keys: int = _MAX_KEYS,
        max_values: int = _MAX_VALUES,
        max_inventory_bytes: int = _MAX_INVENTORY_BYTES) -> dict[str, Any]:
    """Inventory typed registry value digests for the current AppContainer.

    The API yields the current AppContainer profile's registry root. This
    routine verifies the process token SID first, recursively enumerates that
    root with explicit limits, and hashes typed values without exporting raw
    contents. It cannot guarantee a quiescent or atomic registry snapshot.
    """
    if (type(max_depth) is not int or not 0 <= max_depth <= _MAX_DEPTH
            or type(max_keys) is not int or not 1 <= max_keys <= _MAX_KEYS
            or type(max_values) is not int or not 0 <= max_values <= _MAX_VALUES
            or type(max_inventory_bytes) is not int
            or not 1 <= max_inventory_bytes <= _MAX_INVENTORY_BYTES):
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_limits_invalid")
    process_id, process_creation = _check_current_package_sid(
        expected_appcontainer_sid)
    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    get_location = userenv.GetAppContainerRegistryLocation
    get_location.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    get_location.restype = ctypes.c_long
    root_handle = wintypes.HANDLE()
    hresult = int(get_location(0x00020019, ctypes.byref(root_handle)))
    if hresult != 0 or not root_handle.value:
        if root_handle.value:
            winreg.HKEYType(int(root_handle.value)).Close()
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_location_unavailable",
            hresult & 0xFFFFFFFF)
    root = winreg.HKEYType(int(root_handle.value))
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    reg_enum_value = advapi32.RegEnumValueW
    reg_enum_value.argtypes = [wintypes.HANDLE, wintypes.DWORD,
        wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    reg_enum_value.restype = wintypes.LONG
    value_name_buffer = ctypes.create_unicode_buffer(_MAX_VALUE_NAME_CHARS + 1)
    value_data_buffer = ctypes.create_string_buffer(_MAX_SINGLE_VALUE_BYTES)
    keys: list[dict[str, Any]] = []
    total_values = 0
    total_bytes = 0

    def walk(key_handle: Any, relative_path: str, depth: int) -> None:
        nonlocal total_values, total_bytes
        index = 0
        child_names: list[str] = []
        while True:
            try:
                name = winreg.EnumKey(key_handle, index)
            except OSError as exc:
                if getattr(exc, "winerror", None) == 259:
                    break
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_key_enumeration_failed",
                    getattr(exc, "winerror", None)) from exc
            if (not isinstance(name, str) or not name or len(name) > 255
                    or name in {".", ".."}
                    or "/" in name or "\\" in name):
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_key_name_invalid")
            child_names.append(name)
            index += 1
            if len(keys) + len(child_names) > max_keys:
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_key_count_over_bound")
        index = 0
        value_records: list[dict[str, Any]] = []
        seen_value_names: set[str] = set()
        while True:
            name_chars = wintypes.DWORD(_MAX_VALUE_NAME_CHARS + 1)
            data_bytes = wintypes.DWORD(_MAX_SINGLE_VALUE_BYTES)
            value_type = wintypes.DWORD()
            status = int(reg_enum_value(wintypes.HANDLE(int(key_handle)), index,
                value_name_buffer, ctypes.byref(name_chars), None,
                ctypes.byref(value_type), value_data_buffer,
                ctypes.byref(data_bytes)))
            if status == 259:  # ERROR_NO_MORE_ITEMS
                break
            if status == 234:  # ERROR_MORE_DATA; never retry with larger buffers
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_value_over_bound")
            if status != 0:
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_value_enumeration_failed",
                    status)
            if name_chars.value > _MAX_VALUE_NAME_CHARS:
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_value_name_invalid")
            value_name = value_name_buffer[:name_chars.value]
            folded_name = value_name.casefold()
            if folded_name in seen_value_names:
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_value_name_ambiguous")
            seen_value_names.add(folded_name)
            data_size = int(data_bytes.value)
            typed_payload = {"type": int(value_type.value),
                "data_base64": base64.b64encode(
                    value_data_buffer.raw[:data_size]).decode("ascii")}
            value_digest = hashlib.sha256(_canonical_json(
                typed_payload)).hexdigest()
            total_values += 1
            total_bytes += data_size
            if total_values > max_values or total_bytes > max_inventory_bytes:
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_inventory_over_bound")
            value_records.append({"name": value_name,
                "value_type": int(value_type.value),
                "data_size_bytes": data_size,
                "typed_data_sha256": value_digest})
            index += 1
        value_records.sort(key=lambda item: item["name"].casefold())
        keys.append({"relative_path": relative_path,
            "value_count": len(value_records),
            "subkey_count": len(child_names), "values": value_records})
        if len(keys) > max_keys:
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_key_count_over_bound")
        if child_names and depth >= max_depth:
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_depth_over_bound")
        child_names.sort(key=str.casefold)
        for name in child_names:
            path = f"{relative_path}\\{name}" if relative_path else name
            if len(path) > 2048:
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_key_path_over_bound")
            try:
                child = winreg.OpenKey(key_handle, name, 0, winreg.KEY_READ)
            except OSError as exc:
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_subkey_open_failed",
                    getattr(exc, "winerror", None)) from exc
            with child:
                walk(child, path, depth + 1)

    with root:
        walk(root, "", 0)
        keys.sort(key=lambda item: item["relative_path"].casefold())
        registry_contents = {"key_count": len(keys),
            "value_count": total_values, "total_value_bytes": total_bytes,
            "keys": keys}
        semantic = {"schema_version":
                "sentientos.windows_appcontainer_registry_inventory:v1",
            "appcontainer_sid": expected_appcontainer_sid,
            "worker_process_id": process_id,
            "worker_process_creation_time_100ns": process_creation,
            "key_count": len(keys), "value_count": total_values,
            "total_value_bytes": total_bytes, "keys": keys,
            "registry_contents_digest": hashlib.sha256(
                _canonical_json(registry_contents)).hexdigest(),
            "snapshot_atomicity_verified": False,
            "writer_quiescence_verified": False,
            "security_metadata_verified": False,
            "registry_state_accounted": False,
            "profile_state_accounted": False,
            "retention_contrast_eligible": False, "authority": False}
        if len(_canonical_json(semantic)) > max_inventory_bytes:
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_inventory_over_bound")
        return {**semantic, "inventory_digest": hashlib.sha256(
            _canonical_json(semantic)).hexdigest()}


def verify_appcontainer_registry_inventory(value: Any, *,
        expected_appcontainer_sid: str) -> dict[str, Any]:
    """Verify detached registry inventory structure and content digest."""
    fields = {"schema_version", "appcontainer_sid", "worker_process_id",
        "worker_process_creation_time_100ns", "key_count", "value_count",
        "total_value_bytes", "keys", "registry_contents_digest",
        "snapshot_atomicity_verified",
        "writer_quiescence_verified", "security_metadata_verified",
        "registry_state_accounted", "profile_state_accounted",
        "retention_contrast_eligible", "authority", "inventory_digest"}
    if (not isinstance(value, dict) or set(value) != fields
            or value.get("schema_version") !=
                "sentientos.windows_appcontainer_registry_inventory:v1"
            or not _is_canonical_package_sid(expected_appcontainer_sid)
            or value.get("appcontainer_sid") != expected_appcontainer_sid
            or type(value.get("worker_process_id")) is not int
            or value["worker_process_id"] <= 0
            or type(value.get("worker_process_creation_time_100ns")) is not int
            or value["worker_process_creation_time_100ns"] <= 0
            or type(value.get("key_count")) is not int
            or type(value.get("value_count")) is not int
            or type(value.get("total_value_bytes")) is not int
            or not isinstance(value.get("keys"), list)
            or value.get("snapshot_atomicity_verified") is not False
            or value.get("writer_quiescence_verified") is not False
            or value.get("security_metadata_verified") is not False
            or value.get("registry_state_accounted") is not False
            or value.get("profile_state_accounted") is not False
            or value.get("retention_contrast_eligible") is not False
            or value.get("authority") is not False
            or not isinstance(value.get("inventory_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}",
                value.get("inventory_digest", "")) is None):
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_inventory_invalid")
    if (len(value["keys"]) != value["key_count"]
            or value["key_count"] < 1
            or value["key_count"] > _MAX_KEYS
            or value["value_count"] > _MAX_VALUES
            or value["total_value_bytes"] > _MAX_INVENTORY_BYTES):
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_inventory_count_invalid")
    path_set: set[str] = set()
    counted_values = 0
    counted_bytes = 0
    previous_path = ""
    known_paths = {""}
    subkey_counts: dict[str, int] = {}
    for key in value["keys"]:
        if (not isinstance(key, dict)
                or set(key) != {"relative_path", "value_count",
                    "subkey_count", "values"}
                or not isinstance(key.get("relative_path"), str)
                or type(key.get("value_count")) is not int
                or type(key.get("subkey_count")) is not int
                or key["subkey_count"] < 0
                or key["subkey_count"] > _MAX_KEYS
                or not isinstance(key.get("values"), list)
                or key["value_count"] != len(key["values"])):
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_key_invalid")
        path = key["relative_path"]
        parts = path.split("\\") if path else []
        if (len(path) > 2048 or len(parts) > _MAX_DEPTH
                or any(not part or part in {".", ".."}
                or "/" in part for part in parts)
                or path.casefold() in path_set
                or (parts and "\\".join(parts[:-1]).casefold() not in known_paths)
                or (previous_path and path.casefold() < previous_path)):
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_key_topology_invalid")
        path_set.add(path.casefold())
        known_paths.add(path.casefold())
        subkey_counts[path.casefold()] = key["subkey_count"]
        previous_path = path.casefold()
        previous_value = ""
        names: set[str] = set()
        for item in key["values"]:
            if (not isinstance(item, dict)
                    or set(item) != {"name", "value_type", "data_size_bytes",
                        "typed_data_sha256"}
                    or not isinstance(item.get("name"), str)
                    or len(item["name"]) > _MAX_VALUE_NAME_CHARS
                    or type(item.get("value_type")) is not int
                    or not 0 <= item["value_type"] <= 0xFFFFFFFF
                    or type(item.get("data_size_bytes")) is not int
                    or not 0 <= item["data_size_bytes"] <=
                        _MAX_SINGLE_VALUE_BYTES
                    or not isinstance(item.get("typed_data_sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}",
                        item.get("typed_data_sha256", "")) is None
                    or item["name"].casefold() in names
                    or (previous_value and item["name"].casefold() < previous_value)):
                raise WindowsAppContainerRegistryError(
                    "appcontainer_registry_value_invalid")
            names.add(item["name"].casefold())
            previous_value = item["name"].casefold()
            counted_values += 1
            counted_bytes += item["data_size_bytes"]
    for path in path_set:
        prefix = path + "\\" if path else ""
        direct_children = sum(1 for candidate in path_set
            if candidate.startswith(prefix) and candidate != path
            and "\\" not in candidate[len(prefix):])
        if subkey_counts.get(path) != direct_children:
            raise WindowsAppContainerRegistryError(
                "appcontainer_registry_subkey_count_mismatch")
    if (counted_values != value["value_count"]
            or counted_bytes != value["total_value_bytes"]):
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_inventory_count_mismatch")
    semantic = {key: item for key, item in value.items()
        if key != "inventory_digest"}
    expected_contents_digest = hashlib.sha256(_canonical_json({
        "key_count": value["key_count"],
        "value_count": value["value_count"],
        "total_value_bytes": value["total_value_bytes"],
        "keys": value["keys"]})).hexdigest()
    if (not isinstance(value.get("registry_contents_digest"), str)
            or value["registry_contents_digest"] != expected_contents_digest):
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_contents_digest_mismatch")
    if hashlib.sha256(_canonical_json(semantic)).hexdigest() != value["inventory_digest"]:
        raise WindowsAppContainerRegistryError(
            "appcontainer_registry_inventory_digest_mismatch")
    return value
