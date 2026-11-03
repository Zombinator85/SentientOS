"""Read bounded Windows/WSL child-process profiles without granting authority.

Each exact command is still subject to the installed process-launch receipt
verifier before spawn. This file supplies arguments; it cannot approve them.
"""
from __future__ import annotations

import json
import os
import platform
import re
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_process_supervisor import CompanionProcessLaunchSpec

PROCESS_PROFILE_SCHEMA = "sentientos.companion_process_launch_profiles:v1"
_PROFILE_FIELDS = frozenset({"schema_version", "roles"})
_ROLE_FIELDS = frozenset({"argv", "working_directory", "environment",
    "startup_timeout_seconds", "shutdown_timeout_seconds"})
_ROLES = frozenset({"windows_edge", "wsl_core"})
_MAX_PROFILE_BYTES = 128 * 1024
_PROVIDER_REFERENCE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*\Z")


class CompanionProcessProfileError(CompanionBridgeError):
    """Invalid, unsafe, or unavailable process launch profile."""


def load_companion_process_launch_profiles(path: Path | str, *,
        system_name: str | None = None) -> dict[str, CompanionProcessLaunchSpec]:
    """Load two role command profiles; receipt verification remains separate."""
    if (system_name or platform.system()) != "Windows":
        raise CompanionProcessProfileError("companion_process_profile_windows_host_required")
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise CompanionProcessProfileError("companion_process_profile_path_invalid")
    try:
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0))
    except OSError as exc:
        raise CompanionProcessProfileError("companion_process_profile_unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_size <= 0
                or info.st_size > _MAX_PROFILE_BYTES):
            raise CompanionProcessProfileError("companion_process_profile_size_invalid")
        if (system_name or platform.system()) == "Linux" and (
                info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise CompanionProcessProfileError("companion_process_profile_custody_invalid")
        data = bytearray()
        while len(data) <= _MAX_PROFILE_BYTES:
            block = os.read(descriptor, min(8192, _MAX_PROFILE_BYTES + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > _MAX_PROFILE_BYTES:
            raise CompanionProcessProfileError("companion_process_profile_size_invalid")
    finally:
        os.close(descriptor)
    try:
        profile = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CompanionProcessProfileError("companion_process_profile_invalid_json") from exc
    if (not isinstance(profile, dict) or set(profile) != _PROFILE_FIELDS
            or profile.get("schema_version") != PROCESS_PROFILE_SCHEMA
            or not isinstance(profile.get("roles"), dict)
            or set(profile["roles"]) != _ROLES):
        raise CompanionProcessProfileError("companion_process_profile_shape_invalid")
    result: dict[str, CompanionProcessLaunchSpec] = {}
    for role, value in profile["roles"].items():
        result[role] = _build_spec(role, value)
    return result


def _build_spec(role: str, value: object) -> CompanionProcessLaunchSpec:
    if not isinstance(value, dict) or set(value) != _ROLE_FIELDS:
        raise CompanionProcessProfileError("companion_process_profile_role_shape_invalid")
    argv = value.get("argv")
    directory = value.get("working_directory")
    environment = value.get("environment")
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 64
            or any(not isinstance(item, str) or not item or "\x00" in item
                   or len(item.encode("utf-8")) > 4096 for item in argv)
            or sum(len(item.encode("utf-8")) for item in argv) > 16_384):
        raise CompanionProcessProfileError("companion_process_profile_argv_invalid")
    if not isinstance(directory, str) or not _windows_path_safe(directory):
        raise CompanionProcessProfileError("companion_process_profile_directory_invalid")
    if (not isinstance(environment, dict)
            or environment != {"SENTIENTOS_COMPANION_ROLE": role}):
        raise CompanionProcessProfileError("companion_process_profile_environment_invalid")
    startup = _timeout(value.get("startup_timeout_seconds"))
    shutdown = _timeout(value.get("shutdown_timeout_seconds"))
    _validate_command(role, argv)
    return CompanionProcessLaunchSpec(role=role, argv=tuple(argv),
        working_directory=directory, environment=dict(environment),
        startup_timeout_seconds=startup, shutdown_timeout_seconds=shutdown)


def _validate_command(role: str, argv: list[str]) -> None:
    if not _windows_path_safe(argv[0]):
        raise CompanionProcessProfileError("companion_process_profile_executable_invalid")
    start = 1
    if role == "windows_edge":
        if argv[start:start + 2] != ["-m", "sentientos.gaming_companion_role_entrypoint"]:
            raise CompanionProcessProfileError("companion_process_profile_entrypoint_invalid")
        start += 2
    else:
        if (len(argv) < 7 or argv[1] != "--distribution"
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", argv[2])
                or argv[3] != "--exec" or not _linux_path_safe(argv[4])
                or argv[5:7] != ["-m", "sentientos.gaming_companion_role_entrypoint"]):
            raise CompanionProcessProfileError("companion_process_profile_wsl_invocation_invalid")
        start = 7
    tail = argv[start:]
    expected = ["--role", role, "--manifest"]
    if len(tail) not in {8, 10} or tail[:3] != expected:
        raise CompanionProcessProfileError("companion_process_profile_role_command_invalid")
    manifest_path = tail[3]
    if not ((role == "windows_edge" and _windows_path_safe(manifest_path))
            or (role == "wsl_core" and _linux_path_safe(manifest_path))):
        raise CompanionProcessProfileError("companion_process_profile_manifest_path_invalid")
    if (tail[4] != "--provider" or _PROVIDER_REFERENCE.fullmatch(tail[5]) is None
            or tail[6] != "--launch-authorizer"
            or _PROVIDER_REFERENCE.fullmatch(tail[7]) is None):
        raise CompanionProcessProfileError("companion_process_profile_authority_binding_invalid")
    if len(tail) == 10:
        if tail[8] != "--poll-interval":
            raise CompanionProcessProfileError("companion_process_profile_poll_interval_invalid")
        try:
            poll = float(tail[9])
        except ValueError as exc:
            raise CompanionProcessProfileError(
                "companion_process_profile_poll_interval_invalid") from exc
        if not 0.05 <= poll <= 10:
            raise CompanionProcessProfileError("companion_process_profile_poll_interval_invalid")


def _windows_path_safe(value: str) -> bool:
    path = PureWindowsPath(value)
    return (path.is_absolute() and bool(path.drive) and not path.drive.startswith("\\")
            and ".." not in path.parts and not any(character in value for character in "\x00\n\r"))


def _linux_path_safe(value: str) -> bool:
    path = PurePosixPath(value)
    return (path.is_absolute() and ".." not in path.parts
            and "\\" not in value and "\x00" not in value)


def _timeout(value: object) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not 0.1 <= value <= 60):
        raise CompanionProcessProfileError("companion_process_profile_timeout_invalid")
    return float(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_field")
        result[key] = value
    return result


__all__ = ["PROCESS_PROFILE_SCHEMA", "CompanionProcessProfileError",
    "load_companion_process_launch_profiles"]
