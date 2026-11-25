"""Per-protocol AppContainer profile provisioning for condition workers.

Profiles are scoped to the current Windows user and persist after this helper
returns. Cleanup is intentionally separate so a worker crash cannot delete a
profile that may still contain evidence or be in use.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import ntpath
import os
import re
from pathlib import Path
from ctypes import wintypes
from typing import Any


_PROTOCOL_ID = re.compile(r"devexp-durable-learning-protocol-([0-9a-f]{24})")
_CONDITIONS = {
    "relevant_experience_available": "Available",
    "relevant_experience_withheld": "Withheld",
}
_PROFILE_FIELDS = frozenset({"schema_version", "profile_name", "protocol_id",
    "condition", "appcontainer_sid", "profile_local_data_path",
    "profile_local_data_root_identity", "profile_local_data_is_branch_state",
    "unaccounted_persistent_profile_state", "profile_created_by_call",
    "profile_persisted", "registry_state_inventory_verified", "authority"})
_PAIR_FIELDS = frozenset({"schema_version", "protocol_id",
    "condition_profiles", "profile_sid_bindings_distinct",
    "profile_data_roots_distinct", "profile_data_is_branch_state",
    "profile_state_accounted", "registry_state_accounted",
    "profile_pair_digest", "retention_contrast_eligible", "authority"})
_PAIR_IDENTITY_FIELDS = frozenset({"profile_name", "appcontainer_sid",
    "profile_local_data_path", "profile_local_data_root_identity"})


def _canonical_package_sid(value: Any) -> tuple[int, ...] | None:
    if not isinstance(value, str) or len(value) > 184:
        return None
    parts = value.split("-")
    if (len(parts) < 5 or parts[:4] != ["S", "1", "15", "2"]
            or len(parts[4:]) > 15
            or any(re.fullmatch(r"[0-9]+", part) is None for part in parts[1:])):
        return None
    try:
        numeric = tuple(int(part, 10) for part in parts[1:])
    except ValueError:
        return None
    if (any(part > 0xFFFFFFFF for part in numeric[2:])
            or tuple(str(part) for part in numeric) != tuple(parts[1:])):
        return None
    return numeric


class WindowsAppContainerProfileError(ValueError):
    """AppContainer profile provisioning failed closed."""

    def __init__(self, code: str, hresult: int | None = None) -> None:
        self.code = code
        self.hresult = hresult
        super().__init__(code if hresult is None else f"{code}:{hresult:#010x}")


def _profile_data_inventory_binding(profile: Any, *,
        protocol_id: str | None = None, condition: str | None = None
        ) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_inventory_binding_invalid")
    full_profile = set(profile) == _PROFILE_FIELDS
    projected_identity = set(profile) == _PAIR_IDENTITY_FIELDS
    if not full_profile and not projected_identity:
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_inventory_binding_invalid")
    if full_profile:
        if (profile.get("schema_version") !=
                    "sentientos.windows_appcontainer_profile:v1"
                or not isinstance(profile.get("protocol_id"), str)
                or _PROTOCOL_ID.fullmatch(profile["protocol_id"]) is None
                or not isinstance(profile.get("condition"), str)
                or profile["condition"] not in _CONDITIONS
                or profile.get("profile_local_data_is_branch_state") is not False
                or profile.get("unaccounted_persistent_profile_state") is not True
                or type(profile.get("profile_created_by_call")) is not bool
                or profile.get("profile_persisted") is not True
                or profile.get("registry_state_inventory_verified") is not False
                or profile.get("authority") is not False):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_inventory_binding_invalid")
        bound_protocol_id = profile["protocol_id"]
        bound_condition = profile["condition"]
        if ((protocol_id is not None and protocol_id != bound_protocol_id)
                or (condition is not None and condition != bound_condition)):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_inventory_binding_mismatch")
    else:
        if (not isinstance(protocol_id, str)
                or _PROTOCOL_ID.fullmatch(protocol_id) is None
                or not isinstance(condition, str)
                or condition not in _CONDITIONS):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_inventory_binding_invalid")
        bound_protocol_id = protocol_id
        bound_condition = condition
    if (not isinstance(bound_condition, str)
            or bound_condition not in _CONDITIONS
            or _canonical_package_sid(profile.get("appcontainer_sid")) is None
            or profile.get("profile_name") != (
                f"SentientOS.DL.{bound_protocol_id.rsplit('-', 1)[1]}."
                f"{_CONDITIONS[bound_condition]}")):
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_inventory_binding_invalid")
    path = profile.get("profile_local_data_path")
    identity = profile.get("profile_local_data_root_identity")
    if (not isinstance(path, str) or not path
            or not isinstance(identity, dict)
            or set(identity) != {"volume_serial", "file_id_hex"}
            or type(identity.get("volume_serial")) is not int
            or not 0 <= identity["volume_serial"] <= 0xFFFFFFFFFFFFFFFF
            or not isinstance(identity.get("file_id_hex"), str)
            or re.fullmatch(r"[0-9a-f]{32}", identity["file_id_hex"]) is None):
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_inventory_identity_invalid")
    return {"protocol_id": bound_protocol_id, "condition": bound_condition,
        "appcontainer_sid": profile["appcontainer_sid"],
        "profile_local_data_path": path,
        "profile_local_data_root_identity": dict(identity)}


def inventory_condition_appcontainer_profile_data(profile: Any, *,
        protocol_id: str | None = None, condition: str | None = None,
        max_depth: int = 16, max_entries: int = 4096,
        max_file_bytes: int = 4_194_304,
        max_total_bytes: int = 16_777_216) -> dict[str, Any]:
    """Bind one observed profile-data tree without claiming retention authority.

    Accepts either the full provisioning record or the condition profile
    identity from a verified profile pair. Callers must establish quiescence.
    The inventory does not inspect registry state or prove atomicity.
    """
    binding = _profile_data_inventory_binding(profile,
        protocol_id=protocol_id, condition=condition)
    from .windows_handle_custody import inventory_regular_tree
    identity = binding["profile_local_data_root_identity"]
    try:
        inventory = inventory_regular_tree(
            Path(binding["profile_local_data_path"]),
            expected_root_identity=(identity["volume_serial"],
                bytes.fromhex(identity["file_id_hex"])),
            max_depth=max_depth, max_entries=max_entries,
            max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes)
    except (OSError, TypeError, ValueError) as exc:
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_inventory_unavailable") from exc
    semantic = {"schema_version":
            "sentientos.windows_appcontainer_profile_data_inventory:v1",
        "protocol_id": binding["protocol_id"],
        "condition": binding["condition"],
        "appcontainer_sid": binding["appcontainer_sid"],
        "profile_local_data_root_identity": identity,
        "tree_inventory": inventory,
        "profile_state_accounted": False,
        "registry_state_accounted": False,
        "retention_contrast_eligible": False,
        "authority": False}
    digest = hashlib.sha256(json.dumps(semantic, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()
    return verify_condition_appcontainer_profile_data_inventory(
        {**semantic, "inventory_digest": digest}, profile=profile,
        protocol_id=protocol_id, condition=condition)


def verify_condition_appcontainer_profile_data_inventory(value: Any, *,
        profile: Any, protocol_id: str | None = None,
        condition: str | None = None) -> dict[str, Any]:
    """Verify a detached profile-tree inventory against its profile identity."""
    binding = _profile_data_inventory_binding(profile,
        protocol_id=protocol_id, condition=condition)
    fields = {"schema_version", "protocol_id", "condition", "appcontainer_sid",
        "profile_local_data_root_identity", "tree_inventory",
        "profile_state_accounted", "registry_state_accounted",
        "retention_contrast_eligible", "authority", "inventory_digest"}
    if (not isinstance(value, dict) or set(value) != fields
            or value.get("schema_version") !=
                "sentientos.windows_appcontainer_profile_data_inventory:v1"
            or value.get("protocol_id") != binding["protocol_id"]
            or value.get("condition") != binding["condition"]
            or value.get("appcontainer_sid") != binding["appcontainer_sid"]
            or value.get("profile_local_data_root_identity") !=
                binding["profile_local_data_root_identity"]
            or value.get("profile_state_accounted") is not False
            or value.get("registry_state_accounted") is not False
            or value.get("retention_contrast_eligible") is not False
            or value.get("authority") is not False
            or not isinstance(value.get("inventory_digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}", value["inventory_digest"]) is None):
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_inventory_artifact_invalid")
    identity = binding["profile_local_data_root_identity"]
    from .windows_handle_custody import verify_regular_tree_inventory
    try:
        verify_regular_tree_inventory(value["tree_inventory"],
            expected_root_identity=(identity["volume_serial"],
                bytes.fromhex(identity["file_id_hex"])))
    except (TypeError, ValueError) as exc:
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_tree_inventory_invalid") from exc
    semantic = {key: item for key, item in value.items()
        if key != "inventory_digest"}
    digest = hashlib.sha256(json.dumps(semantic, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()
    if digest != value["inventory_digest"]:
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_inventory_digest_mismatch")
    return value


def verify_condition_appcontainer_profile_pair(*, protocol_id: str,
        profiles: Any) -> dict[str, Any]:
    """Bind distinct profile identities to the two frozen conditions.

    This validates profile-provisioning records, not the live process token or
    effective ACLs. Profile-local data and registry state remain explicitly
    unaccounted, so this pair can never qualify retention by itself.
    """
    if (not isinstance(protocol_id, str)
            or _PROTOCOL_ID.fullmatch(protocol_id) is None
            or not isinstance(profiles, dict)
            or set(profiles) != set(_CONDITIONS)):
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_pair_invalid")
    identities: dict[str, dict[str, Any]] = {}
    sid_values: set[tuple[int, ...]] = set()
    path_values: dict[str, tuple[str, ...]] = {}
    for condition in _CONDITIONS:
        artifact = profiles[condition]
        expected_name = f"SentientOS.DL.{protocol_id.rsplit('-', 1)[1]}.{_CONDITIONS[condition]}"
        if (not isinstance(artifact, dict)
                or set(artifact) != _PROFILE_FIELDS
                or artifact.get("schema_version") !=
                    "sentientos.windows_appcontainer_profile:v1"
                or artifact.get("protocol_id") != protocol_id
                or artifact.get("condition") != condition
                or artifact.get("profile_name") != expected_name
                or _canonical_package_sid(artifact.get("appcontainer_sid")) is None
                or artifact.get("profile_local_data_is_branch_state") is not False
                or artifact.get("unaccounted_persistent_profile_state") is not True
                or type(artifact.get("profile_created_by_call")) is not bool
                or artifact.get("profile_persisted") is not True
                or artifact.get("registry_state_inventory_verified") is not False
                or artifact.get("authority") is not False):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_pair_binding_invalid")
        path = artifact.get("profile_local_data_path")
        root_identity = artifact.get("profile_local_data_root_identity")
        if (not isinstance(path, str) or not path
                or not isinstance(root_identity, dict)
                or set(root_identity) != {"volume_serial", "file_id_hex"}
                or type(root_identity.get("volume_serial")) is not int
                or not 0 <= root_identity["volume_serial"] <= 0xFFFFFFFFFFFFFFFF
                or not isinstance(root_identity.get("file_id_hex"), str)
                or re.fullmatch(r"[0-9a-f]{32}",
                    root_identity.get("file_id_hex", "")) is None):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_pair_identity_invalid")
        drive, tail = ntpath.splitdrive(path)
        path_parts = tuple(part.casefold() for part in
            ntpath.normpath(path).replace("/", "\\").split("\\") if part)
        if (not drive or drive.startswith("\\") or not tail.startswith("\\")
                or not path_parts or not path_parts[0].endswith(":")):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_pair_path_invalid")
        sid = artifact["appcontainer_sid"]
        canonical_sid = _canonical_package_sid(sid)
        if canonical_sid in sid_values:
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_pair_sid_collision")
        sid_values.add(canonical_sid)
        path_values[condition] = path_parts
        identities[condition] = {"profile_name": expected_name,
            "appcontainer_sid": sid,
            "profile_local_data_path": ntpath.normcase(ntpath.normpath(path)),
            "profile_local_data_root_identity": dict(root_identity)}
    first, second = (_CONDITIONS[0], _CONDITIONS[1])
    first_path, second_path = path_values[first], path_values[second]
    if (identities[first]["profile_local_data_root_identity"] ==
            identities[second]["profile_local_data_root_identity"]
            or first_path == second_path
            or first_path == second_path[:len(first_path)]
            or second_path == first_path[:len(second_path)]):
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_pair_storage_overlap")
    digest_input = {"protocol_id": protocol_id,
        "condition_profiles": identities}
    digest = hashlib.sha256(json.dumps(digest_input, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
            "ascii")).hexdigest()
    result = {"schema_version": "sentientos.windows_appcontainer_profile_pair:v1",
        "protocol_id": protocol_id,
        "condition_profiles": identities,
        "profile_sid_bindings_distinct": True,
        "profile_data_roots_distinct": True,
        "profile_data_is_branch_state": False,
        "profile_state_accounted": False,
        "registry_state_accounted": False,
        "profile_pair_digest": f"sha256:{digest}",
        "retention_contrast_eligible": False,
        "authority": False}
    return verify_condition_appcontainer_profile_pair_result(
        result, protocol_id=protocol_id)


def verify_condition_appcontainer_profile_pair_result(value: Any, *,
        protocol_id: str) -> dict[str, Any]:
    """Recheck a persisted profile-pair binding and its explicit false gates."""
    if (not isinstance(protocol_id, str)
            or _PROTOCOL_ID.fullmatch(protocol_id) is None
            or not isinstance(value, dict) or set(value) != _PAIR_FIELDS
            or value.get("schema_version") !=
                "sentientos.windows_appcontainer_profile_pair:v1"
            or value.get("protocol_id") != protocol_id
            or not isinstance(value.get("condition_profiles"), dict)
            or set(value["condition_profiles"]) != set(_CONDITIONS)
            or value.get("profile_sid_bindings_distinct") is not True
            or value.get("profile_data_roots_distinct") is not True
            or value.get("profile_data_is_branch_state") is not False
            or value.get("profile_state_accounted") is not False
            or value.get("registry_state_accounted") is not False
            or value.get("retention_contrast_eligible") is not False
            or value.get("authority") is not False):
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_pair_result_invalid")
    identities = value["condition_profiles"]
    sid_values: set[tuple[int, ...]] = set()
    path_values: dict[str, tuple[str, ...]] = {}
    root_ids: set[tuple[int, str]] = set()
    for condition in _CONDITIONS:
        identity = identities[condition]
        expected_name = (f"SentientOS.DL.{protocol_id.rsplit('-', 1)[1]}."
            f"{_CONDITIONS[condition]}")
        if (not isinstance(identity, dict)
                or set(identity) != _PAIR_IDENTITY_FIELDS
                or identity.get("profile_name") != expected_name
                or _canonical_package_sid(identity.get("appcontainer_sid")) is None
                or not isinstance(identity.get("profile_local_data_path"), str)
                or not isinstance(identity.get("profile_local_data_root_identity"), dict)):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_pair_identity_invalid")
        sid = identity["appcontainer_sid"]
        canonical_sid = _canonical_package_sid(sid)
        if canonical_sid in sid_values:
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_pair_sid_collision")
        sid_values.add(canonical_sid)
        root_identity = identity["profile_local_data_root_identity"]
        if (set(root_identity) != {"volume_serial", "file_id_hex"}
                or type(root_identity.get("volume_serial")) is not int
                or not 0 <= root_identity["volume_serial"] <= 0xFFFFFFFFFFFFFFFF
                or not isinstance(root_identity.get("file_id_hex"), str)
                or re.fullmatch(r"[0-9a-f]{32}",
                    root_identity.get("file_id_hex", "")) is None):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_pair_identity_invalid")
        root_ids.add((root_identity["volume_serial"],
            root_identity["file_id_hex"]))
        path = identity["profile_local_data_path"]
        drive, tail = ntpath.splitdrive(path)
        parts = tuple(part.casefold() for part in
            ntpath.normpath(path).replace("/", "\\").split("\\") if part)
        if not drive or drive.startswith("\\") or not tail.startswith("\\") or not parts:
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_pair_path_invalid")
        path_values[condition] = parts
    first, second = (_CONDITIONS[0], _CONDITIONS[1])
    first_path, second_path = path_values[first], path_values[second]
    if (len(root_ids) != 2 or first_path == second_path
            or first_path == second_path[:len(first_path)]
            or second_path == first_path[:len(second_path)]):
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_pair_storage_overlap")
    digest_input = {"protocol_id": protocol_id,
        "condition_profiles": identities}
    digest = hashlib.sha256(json.dumps(digest_input, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
            "ascii")).hexdigest()
    if value.get("profile_pair_digest") != f"sha256:{digest}":
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_pair_digest_mismatch")
    detached_profiles = {
        condition: {
            "profile_name": identities[condition]["profile_name"],
            "appcontainer_sid": identities[condition]["appcontainer_sid"],
            "profile_local_data_path": identities[condition][
                "profile_local_data_path"],
            "profile_local_data_root_identity": dict(
                identities[condition]["profile_local_data_root_identity"]),
        }
        for condition in _CONDITIONS
    }
    return {**value, "condition_profiles": detached_profiles}


def provision_condition_appcontainer_profile(*, protocol_id: str,
        condition: str) -> dict[str, Any]:
    """Create or reopen the stable profile for one protocol condition.

    The generated profile name is deterministic for the protocol and
    condition, unique across protocol runs, and within Windows' documented
    64-character AppContainer-name limit. This mutates the current user's
    Windows profile store on first use. Existing profiles are reopened by
    deriving their SID; the helper never deletes profile state.
    """
    match = _PROTOCOL_ID.fullmatch(protocol_id) if isinstance(protocol_id, str) else None
    if (os.name != "nt" or match is None
            or not isinstance(condition, str) or condition not in _CONDITIONS):
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_arguments_invalid")
    profile_name = f"SentientOS.DL.{match.group(1)}.{_CONDITIONS[condition]}"
    if len(profile_name) > 64:
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_name_invalid")

    try:
        userenv = getattr(ctypes, "WinDLL")("userenv", use_last_error=True)
        advapi32 = getattr(ctypes, "WinDLL")("advapi32", use_last_error=True)
        kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_api_unavailable") from exc

    create_profile = userenv.CreateAppContainerProfile
    create_profile.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p)]
    create_profile.restype = ctypes.c_long
    derive_sid = userenv.DeriveAppContainerSidFromAppContainerName
    derive_sid.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    derive_sid.restype = ctypes.c_long
    free_sid = advapi32.FreeSid
    free_sid.argtypes = [ctypes.c_void_p]
    free_sid.restype = ctypes.c_void_p
    convert_sid = advapi32.ConvertSidToStringSidW
    convert_sid.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    convert_sid.restype = wintypes.BOOL
    is_valid_sid = advapi32.IsValidSid
    is_valid_sid.argtypes = [ctypes.c_void_p]
    is_valid_sid.restype = wintypes.BOOL
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p
    get_profile_folder = userenv.GetAppContainerFolderPath
    get_profile_folder.argtypes = [wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.LPWSTR)]
    get_profile_folder.restype = ctypes.c_long
    co_task_mem_free = getattr(ctypes, "WinDLL")("ole32",
        use_last_error=True).CoTaskMemFree
    co_task_mem_free.argtypes = [ctypes.c_void_p]
    co_task_mem_free.restype = None

    profile_sid = ctypes.c_void_p()
    created = False
    hr = create_profile(profile_name,
        f"SentientOS durable learning {condition}",
        f"Condition worker profile for {protocol_id}.",
        None, 0, ctypes.byref(profile_sid))
    if (hr & 0xFFFFFFFF) == 0:
        created = True
    elif (hr & 0xFFFFFFFF) == 0x800700B7:  # HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS)
        hr = derive_sid(profile_name, ctypes.byref(profile_sid))
        if (hr & 0xFFFFFFFF) != 0:
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_existing_sid_unavailable", hr & 0xFFFFFFFF)
    else:
        raise WindowsAppContainerProfileError(
            "appcontainer_profile_create_failed", hr & 0xFFFFFFFF)

    sid_text = wintypes.LPWSTR()
    folder_text = wintypes.LPWSTR()
    try:
        if not profile_sid.value or not is_valid_sid(profile_sid):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_sid_invalid")
        if not convert_sid(profile_sid, ctypes.byref(sid_text)) or not sid_text:
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_sid_format_failed", ctypes.get_last_error())
        sid = sid_text.value
        if re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+", sid) is None:
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_sid_not_package_sid")
        hr = get_profile_folder(sid, ctypes.byref(folder_text))
        if (hr & 0xFFFFFFFF) != 0 or not folder_text or not folder_text.value:
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_data_path_unavailable", hr & 0xFFFFFFFF)
        data_root = Path(folder_text.value)
        from .windows_handle_custody import read_regular_files
        observed = read_regular_files(data_root, max_entries=1,
            max_file_bytes=1, max_total_bytes=1, selected_names=(),
            require_private_acl=False, return_root_identity=True)
        if (not isinstance(observed, tuple) or observed[0]
                or not isinstance(observed[1], tuple)):
            raise WindowsAppContainerProfileError(
                "appcontainer_profile_data_identity_unavailable")
        data_identity = observed[1]
        return {"schema_version": "sentientos.windows_appcontainer_profile:v1",
            "profile_name": profile_name,
            "protocol_id": protocol_id,
            "condition": condition,
            "appcontainer_sid": sid,
            "profile_local_data_path": str(data_root),
            "profile_local_data_root_identity": {
                "volume_serial": data_identity[0],
                "file_id_hex": data_identity[1].hex()},
            "profile_local_data_is_branch_state": False,
            "unaccounted_persistent_profile_state": True,
            "profile_created_by_call": created,
            "profile_persisted": True,
            "registry_state_inventory_verified": False,
            "authority": False}
    finally:
        if folder_text:
            co_task_mem_free(ctypes.cast(folder_text, ctypes.c_void_p))
        if sid_text:
            local_free(ctypes.cast(sid_text, ctypes.c_void_p))
        if profile_sid.value:
            free_sid(profile_sid)
