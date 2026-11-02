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


@dataclass(frozen=True, slots=True)
class ForegroundGameObservation:
    status: str
    game_foreground: bool | None
    process_name_digest: str | None
    observed_at: str
    transport_provenance: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": "sentientos.foreground_game_observation:v1",
            "status": self.status,
            "game_foreground": self.game_foreground,
            "process_name_digest": self.process_name_digest,
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
                 system_provider: Callable[[], str] | None = None,
                 clock: Callable[[], str] | None = None) -> None:
        self._process_name_provider = process_name_provider or _windows_foreground_process_basename
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
        return ForegroundGameObservation(
            "available", normalized in allowed, digest, observed_at)
