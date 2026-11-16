"""Read-only Windows foreground-process matching for explicit game allowlists."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import platform
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

_PROCESS_NAME = re.compile(r"[a-z0-9][a-z0-9 ._-]{0,126}\.exe\Z")

# These statuses represent the explicit compatibility signal or authenticated
# bridge failures that select conservative gaming mode. Other detector errors
# still fail closed at host-resource release admission.
CONSERVATIVE_RESOURCE_GOVERNANCE_FAILURE_STATUSES = frozenset({
    "unavailable",
    "bridge_observation_unavailable",
    "bridge_observation_invalid",
    "bridge_observation_expired",
})


@dataclass(frozen=True, slots=True)
class ForegroundGameObservation:
    status: str
    game_foreground: bool | None
    process_name_digest: str | None
    observed_at: str
    transport_provenance: Mapping[str, Any] | None = None
    game_process_running: bool | None = None
    running_process_name_digests: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": "sentientos.foreground_game_observation:v1",
            "status": self.status,
            "game_foreground": self.game_foreground,
            "process_name_digest": self.process_name_digest,
            "game_process_running": self.game_process_running,
            "running_process_name_digests": (
                list(self.running_process_name_digests)
                if self.running_process_name_digests is not None else None),
            "observed_at": self.observed_at,
        }
        if self.transport_provenance is not None:
            result["transport_provenance"] = dict(self.transport_provenance)
        return result


def normalize_game_process_names(names: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if not isinstance(names, (tuple, list)) or not names or len(names) > 32:
        raise ValueError("game_process_allowlist_required")
    normalized: set[str] = set()
    for name in names:
        if not isinstance(name, str):
            raise ValueError("game_process_name_invalid")
        value = name.strip().casefold()
        if "/" in value or "\\" in value or _PROCESS_NAME.fullmatch(value) is None:
            raise ValueError("game_process_name_invalid")
        normalized.add(value)
    if len(normalized) != len(names):
        raise ValueError("duplicate_game_process_name")
    return tuple(sorted(normalized))


def _windows_running_process_basenames() -> tuple[str, ...] | None:
    """Read executable basenames only; never paths, window titles, or command lines."""
    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    invalid_handle = ctypes.c_void_p(-1).value
    if not snapshot or snapshot == invalid_handle:
        return None
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None
        names = []
        while True:
            names.append(entry.szExeFile)
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
        return tuple(names)
    finally:
        kernel32.CloseHandle(snapshot)


def _windows_foreground_process_basename() -> str | None:
    """Read only the foreground process image name; never title, path, or command line."""
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    window = user32.GetForegroundWindow()
    if not window:
        return None
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
    if not process_id.value:
        return None
    handle = kernel32.OpenProcess(0x1000, False, process_id.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value.replace("\\", "/").rsplit("/", 1)[-1]
    finally:
        kernel32.CloseHandle(handle)


class ForegroundGameDetector:
    """Compare a Windows foreground executable with a caller-selected allowlist."""

    def __init__(self, *, process_name_provider: Callable[[], str | None] | None = None,
                 running_process_names_provider: Callable[[], tuple[str, ...] | None] | None = None,
                 system_provider: Callable[[], str] | None = None,
                 clock: Callable[[], str] | None = None) -> None:
        self._process_name_provider = process_name_provider or _windows_foreground_process_basename
        self._running_process_names_provider = running_process_names_provider or _windows_running_process_basenames
        self._system_provider = system_provider or platform.system
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def observe(self, process_names: tuple[str, ...] | list[str]) -> ForegroundGameObservation:
        allowed = normalize_game_process_names(process_names)
        observed_at = self._clock()
        if self._system_provider().casefold() != "windows":
            return ForegroundGameObservation("unsupported_platform", None, None, observed_at)
        try:
            process_name = self._process_name_provider()
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return ForegroundGameObservation("observation_failed", None, None, observed_at)
        if not isinstance(process_name, str) or not process_name:
            return ForegroundGameObservation("observation_unavailable", None, None, observed_at)
        normalized = process_name.strip().casefold()
        if "/" in normalized or "\\" in normalized or _PROCESS_NAME.fullmatch(normalized) is None:
            return ForegroundGameObservation("process_name_invalid", None, None, observed_at)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        try:
            running_names = self._running_process_names_provider()
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            running_names = None
        running_digests = None
        running = None
        if running_names is not None:
            normalized_running = {item.strip().casefold() for item in running_names
                if isinstance(item, str) and _PROCESS_NAME.fullmatch(item.strip().casefold())}
            matches = normalized_running.intersection(allowed)
            running_digests = tuple(sorted(
                hashlib.sha256(name.encode("utf-8")).hexdigest() for name in matches))
            running = bool(running_digests)
        return ForegroundGameObservation("available", normalized in allowed, digest, observed_at,
            game_process_running=running, running_process_name_digests=running_digests)
