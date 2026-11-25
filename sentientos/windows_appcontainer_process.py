"""Create and observe a no-capability Windows AppContainer worker process.

This is a process-launch primitive, not a condition-worker runtime. It does not
grant resource ACLs, provide RPC, or prove that the AppContainer cannot access
peer state. Callers must provision those boundaries and run the access matrix
before using a launched process for an experiment.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import secrets
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Any, Mapping, Sequence


class WindowsAppContainerProcessError(ValueError):
    """The requested AppContainer worker could not be launched or observed."""

    def __init__(self, code: str, winerror: int | None = None) -> None:
        self.code = code
        self.winerror = winerror
        super().__init__(code if winerror is None else f"{code}:{winerror}")


class _STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
        ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _STARTUPINFOEX(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFO),
        ("lpAttributeList", ctypes.c_void_p)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


class _SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p), ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD)]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsAppContainerProcess:
    """Owned process handle plus supervisor-observed launch identity."""

    def __init__(self, process_handle: int, job_handle: int,
            observation: Mapping[str, object], kernel32: object) -> None:
        self._handle = process_handle
        self._job_handle = job_handle
        self._kernel32 = kernel32
        self.observation = dict(observation)
        self._launch_process_start_nonce = observation.get(
            "process_start_nonce")

    def observe_identity(self) -> dict[str, int]:
        """Re-observe PID and creation time through the owned process handle."""
        if not self._handle:
            raise WindowsAppContainerProcessError(
                "appcontainer_process_handle_unavailable")
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not self._kernel32.GetProcessTimes(self._handle,
                ctypes.byref(creation), ctypes.byref(exit_time),
                ctypes.byref(kernel_time), ctypes.byref(user_time)):
            raise _winerror("appcontainer_process_identity_unavailable")
        process_id = int(self._kernel32.GetProcessId(self._handle))
        creation_time = (int(creation.dwHighDateTime) << 32) | int(
            creation.dwLowDateTime)
        if process_id <= 0 or creation_time <= 0:
            raise WindowsAppContainerProcessError(
                "appcontainer_process_identity_invalid")
        return {"process_id": process_id,
            "process_creation_time_100ns": creation_time}

    @property
    def process_start_nonce(self) -> str | None:
        return (self._launch_process_start_nonce
            if isinstance(self._launch_process_start_nonce, str) else None)

    def wait(self, timeout_ms: int) -> int | None:
        if (type(timeout_ms) is not int or not 0 <= timeout_ms <= 0xFFFFFFFE
                or not self._handle):
            raise WindowsAppContainerProcessError("appcontainer_wait_invalid")
        result = self._kernel32.WaitForSingleObject(self._handle, timeout_ms)
        if result == 0x00000102:  # WAIT_TIMEOUT
            return None
        if result != 0:
            raise _winerror("appcontainer_wait_failed")
        exit_code = wintypes.DWORD()
        if not self._kernel32.GetExitCodeProcess(self._handle,
                ctypes.byref(exit_code)):
            raise _winerror("appcontainer_exit_code_unavailable")
        return int(exit_code.value)

    def terminate(self, exit_code: int = 1) -> None:
        if (type(exit_code) is not int or not 0 <= exit_code <= 0xFFFFFFFF
                or not self._handle):
            raise WindowsAppContainerProcessError("appcontainer_terminate_invalid")
        if self.wait(0) is not None:
            return
        if not self._kernel32.TerminateJobObject(self._job_handle, exit_code):
            raise _winerror("appcontainer_job_terminate_failed")
        result = self.wait(30_000)
        if result is None:
            raise WindowsAppContainerProcessError(
                "appcontainer_termination_unconfirmed")

    def close(self) -> None:
        failures: list[str] = []
        if self._handle:
            if self.wait(0) is None:
                raise WindowsAppContainerProcessError(
                    "appcontainer_process_still_running")
            handle = self._handle
            if not self._kernel32.CloseHandle(handle):
                failures.append("appcontainer_process_handle_close_failed")
            else:
                self._handle = 0
        if self._job_handle:
            handle = self._job_handle
            if not self._kernel32.CloseHandle(handle):
                failures.append("appcontainer_job_handle_close_failed")
            else:
                self._job_handle = 0
        if failures:
            raise WindowsAppContainerProcessError(
                "+".join(failures), int(ctypes.get_last_error()))

    def __enter__(self) -> "WindowsAppContainerProcess":
        return self

    def __exit__(self, *_: object) -> None:
        if self._handle and self.wait(0) is None:
            self.terminate()
        self.close()


def _winerror(code: str) -> WindowsAppContainerProcessError:
    return WindowsAppContainerProcessError(code, int(ctypes.get_last_error()))


def _windows_apis() -> tuple[object, object]:
    if os.name != "nt":
        raise WindowsAppContainerProcessError(
            "appcontainer_windows_only")
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise WindowsAppContainerProcessError("appcontainer_win32_api_unavailable")
    kernel32 = loader("kernel32", use_last_error=True)
    advapi32 = loader("advapi32", use_last_error=True)
    kernel32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t)]
    kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p,
        wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.c_void_p, ctypes.c_void_p]
    kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel32.DeleteProcThreadAttributeList.restype = None
    kernel32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
        ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_void_p,
        ctypes.POINTER(_PROCESS_INFORMATION)]
    kernel32.CreateProcessW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,
        wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p)]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    return kernel32, advapi32


def _observe_process(process_handle: int, expected_sid: str, *,
        kernel32: object, advapi32: object) -> dict[str, object]:
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(process_handle, 0x0008,
            ctypes.byref(token)):
        raise _winerror("appcontainer_process_token_unavailable")
    try:
        is_appcontainer = wintypes.DWORD()
        returned = wintypes.DWORD()
        if not advapi32.GetTokenInformation(token, 29,
                ctypes.byref(is_appcontainer), ctypes.sizeof(is_appcontainer),
                ctypes.byref(returned)):
            raise _winerror("appcontainer_token_kind_unavailable")
        if is_appcontainer.value != 1:
            raise WindowsAppContainerProcessError(
                "appcontainer_token_not_appcontainer")

        required = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 31, None, 0,
            ctypes.byref(required))
        if required.value < ctypes.sizeof(ctypes.c_void_p) or required.value > 65_536:
            raise WindowsAppContainerProcessError(
                "appcontainer_token_sid_size_invalid")
        token_info = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(token, 31, token_info,
                required.value, ctypes.byref(required)):
            raise _winerror("appcontainer_token_sid_unavailable")
        appcontainer_sid = ctypes.cast(token_info,
            ctypes.POINTER(ctypes.c_void_p)).contents.value
        if not appcontainer_sid:
            raise WindowsAppContainerProcessError(
                "appcontainer_token_sid_missing")
        sid_text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(appcontainer_sid,
                ctypes.byref(sid_text)):
            raise _winerror("appcontainer_token_sid_format_invalid")
        try:
            observed_sid = sid_text.value
        finally:
            kernel32.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        if (not isinstance(observed_sid, str)
                or observed_sid.casefold() != expected_sid.casefold()):
            raise WindowsAppContainerProcessError(
                "appcontainer_token_sid_mismatch")

        capabilities_size = wintypes.DWORD()
        capabilities_probe_ok = advapi32.GetTokenInformation(token, 30, None,
            0, ctypes.byref(capabilities_size))
        if (not capabilities_probe_ok
                and int(ctypes.get_last_error()) != 122):
            raise _winerror("appcontainer_token_capabilities_unavailable")
        if capabilities_size.value > 65_536:
            raise WindowsAppContainerProcessError(
                "appcontainer_token_capabilities_over_bound")
        capability_count = 0
        if capabilities_size.value:
            capabilities = ctypes.create_string_buffer(capabilities_size.value)
            if not advapi32.GetTokenInformation(token, 30, capabilities,
                    capabilities_size.value, ctypes.byref(capabilities_size)):
                raise _winerror("appcontainer_token_capabilities_unavailable")
            capability_count = int(ctypes.cast(capabilities,
                ctypes.POINTER(wintypes.DWORD)).contents.value)
        if capability_count != 0:
            raise WindowsAppContainerProcessError(
                "appcontainer_unrequested_capabilities_present")

        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(process_handle, ctypes.byref(creation),
                ctypes.byref(exit_time), ctypes.byref(kernel_time),
                ctypes.byref(user_time)):
            raise _winerror("appcontainer_process_creation_time_unavailable")
        creation_time = (int(creation.dwHighDateTime) << 32) | int(
            creation.dwLowDateTime)
        process_id = int(kernel32.GetProcessId(process_handle))
        if process_id <= 0:
            raise WindowsAppContainerProcessError(
                "appcontainer_process_id_unavailable")
        return {"process_id": process_id,
            "process_creation_time_100ns": creation_time,
            "token_is_appcontainer": True,
            "appcontainer_sid": observed_sid,
            "enabled_capability_count": capability_count,
            "inherited_handles_requested": False,
            "authority": False}
    finally:
        kernel32.CloseHandle(token)


def launch_appcontainer_worker(*, argv: Sequence[str], appcontainer_sid: str,
        cwd: Path, environment: Mapping[str, str]) -> WindowsAppContainerProcess:
    """Launch a self-contained worker with no capabilities or inherited handles.

    The caller must provision read/execute ACLs for the worker runtime, branch
    state ACLs, and an authenticated IPC endpoint before launch. This function
    observes the process token but does not verify any resource access policy.
    """
    if (not isinstance(argv, Sequence) or isinstance(argv, (str, bytes))
            or not argv or len(argv) > 128
            or any(not isinstance(arg, str) or "\0" in arg or len(arg) > 4096
                for arg in argv)
            or not isinstance(appcontainer_sid, str)
            or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+", appcontainer_sid) is None
            or not isinstance(environment, Mapping)
            or len(environment) > 128):
        raise WindowsAppContainerProcessError("appcontainer_launch_arguments_invalid")
    if os.name != "nt":
        raise WindowsAppContainerProcessError("appcontainer_windows_only")
    try:
        executable = Path(argv[0]).resolve(strict=True)
        working_directory = Path(cwd).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise WindowsAppContainerProcessError(
            "appcontainer_launch_path_invalid") from exc
    if not executable.is_file() or not working_directory.is_dir():
        raise WindowsAppContainerProcessError("appcontainer_launch_path_invalid")
    safe_environment: dict[str, str] = {}
    environment_names: set[str] = set()
    for key, value in environment.items():
        if (not isinstance(key, str) or not key or "=" in key or "\0" in key
                or not isinstance(value, str) or "\0" in value
                or len(key) > 256 or len(value) > 24_000):
            raise WindowsAppContainerProcessError(
                "appcontainer_launch_environment_invalid")
        folded_key = key.casefold()
        if folded_key in environment_names:
            raise WindowsAppContainerProcessError(
                "appcontainer_launch_environment_duplicate_key")
        environment_names.add(folded_key)
        safe_environment[key] = value
    if "sentientos_worker_start_nonce" in environment_names:
        raise WindowsAppContainerProcessError(
            "appcontainer_launch_reserved_environment_key")
    process_start_nonce = secrets.token_hex(16)
    safe_environment["SENTIENTOS_WORKER_START_NONCE"] = process_start_nonce
    environment_text = "\0".join(
        f"{key}={safe_environment[key]}" for key in sorted(safe_environment,
            key=str.casefold)) + "\0\0"
    command_text = subprocess.list2cmdline([str(executable), *argv[1:]])
    try:
        command_units = len(command_text.encode("utf-16-le", errors="strict")) // 2
        environment_units = len(environment_text.encode("utf-16-le",
            errors="strict")) // 2
    except UnicodeEncodeError as exc:
        raise WindowsAppContainerProcessError(
            "appcontainer_launch_unicode_invalid") from exc
    if command_units > 32_766 or environment_units > 32_766:
        raise WindowsAppContainerProcessError(
            "appcontainer_launch_block_over_bound")

    executable_digest = hashlib.sha256()
    with executable.open("rb") as executable_stream:
        for chunk in iter(lambda: executable_stream.read(1024 * 1024), b""):
            executable_digest.update(chunk)
    kernel32, advapi32 = _windows_apis()
    sid_ptr = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW(appcontainer_sid,
            ctypes.byref(sid_ptr)):
        raise _winerror("appcontainer_sid_invalid")
    attribute_list = None
    attribute_list_initialized = False
    process_info = _PROCESS_INFORMATION()
    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        kernel32.LocalFree(sid_ptr)
        raise _winerror("appcontainer_job_create_failed")
    try:
        job_limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        job_limits.BasicLimitInformation.LimitFlags = 0x00002000 | 0x00000008
        job_limits.BasicLimitInformation.ActiveProcessLimit = 1
        if not kernel32.SetInformationJobObject(job_handle, 9,
                ctypes.byref(job_limits), ctypes.sizeof(job_limits)):
            raise _winerror("appcontainer_job_limits_failed")
        security_capabilities = _SECURITY_CAPABILITIES(
            AppContainerSid=sid_ptr, Capabilities=None,
            CapabilityCount=0, Reserved=0)
        attribute_size = ctypes.c_size_t()
        kernel32.InitializeProcThreadAttributeList(None, 1, 0,
            ctypes.byref(attribute_size))
        if not 1 <= attribute_size.value <= 65_536:
            raise WindowsAppContainerProcessError(
                "appcontainer_attribute_list_size_invalid")
        attribute_list = ctypes.create_string_buffer(attribute_size.value)
        if not kernel32.InitializeProcThreadAttributeList(attribute_list, 1, 0,
                ctypes.byref(attribute_size)):
            raise _winerror("appcontainer_attribute_list_init_failed")
        attribute_list_initialized = True
        if not kernel32.UpdateProcThreadAttribute(attribute_list, 0,
                0x00020009, ctypes.cast(ctypes.byref(security_capabilities),
                    ctypes.c_void_p), ctypes.sizeof(security_capabilities),
                None, None):
            raise _winerror("appcontainer_security_attribute_failed")

        startup = _STARTUPINFOEX()
        startup.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEX)
        startup.lpAttributeList = ctypes.cast(attribute_list, ctypes.c_void_p)
        command_line = ctypes.create_unicode_buffer(command_text)
        environment_block = ctypes.create_unicode_buffer(environment_text)
        if not kernel32.CreateProcessW(str(executable), command_line, None,
                None, False, 0x00080000 | 0x00000400 | 0x08000000 | 0x00000004,
                environment_block, str(working_directory),
                ctypes.cast(ctypes.byref(startup), ctypes.c_void_p),
                ctypes.byref(process_info)):
            raise _winerror("appcontainer_process_create_failed")
        if not kernel32.AssignProcessToJobObject(job_handle,
                process_info.hProcess):
            raise _winerror("appcontainer_job_assignment_failed")
        observation = _observe_process(process_info.hProcess, appcontainer_sid,
            kernel32=kernel32, advapi32=advapi32)
        observation.update({
            "process_start_nonce": process_start_nonce,
            "environment_block_sha256": hashlib.sha256(
                environment_text.encode("utf-16-le", errors="strict")
            ).hexdigest(),
            "requested_executable_sha256": executable_digest.hexdigest(),
            "requested_capability_count": 0,
            "job_object_bound": True,
            "job_active_process_limit": 1,
            "isolation_verified": False,
            "authority": False,
        })
        previous_suspend_count = kernel32.ResumeThread(process_info.hThread)
        if previous_suspend_count == 0xFFFFFFFF:
            raise _winerror("appcontainer_worker_resume_failed")
        if not kernel32.CloseHandle(process_info.hThread):
            raise _winerror("appcontainer_thread_handle_close_failed")
        process_info.hThread = None
        process = WindowsAppContainerProcess(process_info.hProcess, job_handle,
            observation, kernel32)
        process_info.hProcess = None
        job_handle = None
        return process
    except Exception as launch_error:
        partial_observation: dict[str, int] | None = None
        if process_info.hProcess:
            try:
                partial_observation = WindowsAppContainerProcess(
                    process_info.hProcess, job_handle or 0, {},
                    kernel32).observe_identity()
            except (OSError, TypeError, ValueError):
                pass
        cleanup_errors: list[str] = []
        if job_handle:
            if not kernel32.TerminateJobObject(job_handle, 1):
                cleanup_errors.append("termination_unconfirmed")
        elif process_info.hProcess:
            if not kernel32.TerminateProcess(process_info.hProcess, 1):
                cleanup_errors.append("termination_unconfirmed")
        if process_info.hProcess:
            wait_result = kernel32.WaitForSingleObject(
                process_info.hProcess, 30_000)
            if wait_result != 0:
                cleanup_errors.append("exit_unconfirmed")
        if process_info.hThread:
            if not kernel32.CloseHandle(process_info.hThread):
                cleanup_errors.append("thread_handle_close_failed")
        if process_info.hProcess:
            if not kernel32.CloseHandle(process_info.hProcess):
                cleanup_errors.append("process_handle_close_failed")
        if job_handle:
            if not kernel32.CloseHandle(job_handle):
                cleanup_errors.append("job_handle_close_failed")
        try:
            launch_error.partial_worker_process_observation = (
                partial_observation)
            launch_error.partial_worker_cleanup_errors = list(cleanup_errors)
        except (AttributeError, TypeError):
            pass
        raise
    finally:
        if attribute_list_initialized:
            kernel32.DeleteProcThreadAttributeList(attribute_list)
        if sid_ptr.value:
            kernel32.LocalFree(sid_ptr)


def launch_condition_appcontainer_worker(*, protocol_id: str,
        condition: str, argv: Sequence[str], cwd: Path,
        environment: Mapping[str, str]) -> WindowsAppContainerProcess:
    """Provision and launch the condition's deterministic AppContainer.

    This composes profile provisioning with the lower-level process launcher
    and binds the profile name, protocol, and condition into the observed
    launch record. It still does not provision resource ACLs or verify the
    access matrix. If launch fails after first-time profile creation, that
    per-user profile remains and must be handled by a separate cleanup policy.
    """
    from .windows_appcontainer_profile import (
        provision_condition_appcontainer_profile)

    profile = provision_condition_appcontainer_profile(
        protocol_id=protocol_id, condition=condition)
    process = launch_appcontainer_worker(argv=argv,
        appcontainer_sid=profile["appcontainer_sid"], cwd=cwd,
        environment=environment)
    process.observation.update({
        "profile_name": profile["profile_name"],
        "protocol_id": profile["protocol_id"],
        "condition": profile["condition"],
        "profile_local_data_path": profile["profile_local_data_path"],
        "profile_local_data_root_identity": profile[
            "profile_local_data_root_identity"],
        "profile_local_data_is_branch_state": False,
        "unaccounted_persistent_profile_state": True,
        "registry_state_inventory_verified": False,
        "profile_created_by_call": profile["profile_created_by_call"],
        "profile_sid_matches_observed_process_sid": (
            process.observation.get("appcontainer_sid") ==
            profile["appcontainer_sid"]),
    })
    if process.observation["profile_sid_matches_observed_process_sid"] is not True:
        process.terminate()
        process.close()
        raise WindowsAppContainerProcessError(
            "appcontainer_profile_process_sid_mismatch")
    return process


def launch_condition_appcontainer_worker_pair(*, protocol_id: str,
        profile_pair: Mapping[str, Any],
        worker_specs: Mapping[str, Mapping[str, Any]]
        ) -> tuple[dict[str, WindowsAppContainerProcess], dict[str, Any]]:
    """Launch both condition workers under their verified profile-pair SIDs.

    The profile pair is an identity binding only. This operation does not grant
    resource ACLs, create IPC, or verify effective access. If any launch fails,
    already-started workers are terminated and their process/job handles closed.
    """
    from .durable_developmental_learning_experiment import _CONDITIONS
    from .windows_appcontainer_profile import (
        verify_condition_appcontainer_profile_pair_result)

    if (not isinstance(protocol_id, str)
            or not isinstance(profile_pair, Mapping)
            or not isinstance(worker_specs, Mapping)
            or set(worker_specs) != set(_CONDITIONS)):
        raise WindowsAppContainerProcessError(
            "appcontainer_worker_pair_arguments_invalid")
    try:
        checked_pair = verify_condition_appcontainer_profile_pair_result(
            dict(profile_pair), protocol_id=protocol_id)
    except (TypeError, ValueError) as exc:
        raise WindowsAppContainerProcessError(
            "appcontainer_worker_pair_profile_binding_invalid") from exc
    if os.name != "nt":
        raise WindowsAppContainerProcessError("appcontainer_windows_only")

    processes: dict[str, WindowsAppContainerProcess] = {}
    observations: dict[str, dict[str, Any]] = {}
    launching_condition: str | None = None
    try:
        for condition in _CONDITIONS:
            launching_condition = condition
            spec = worker_specs[condition]
            if (not isinstance(spec, Mapping)
                    or set(spec) != {"argv", "cwd", "environment"}):
                raise WindowsAppContainerProcessError(
                    "appcontainer_worker_pair_spec_invalid")
            identity = checked_pair["condition_profiles"][condition]
            process = launch_appcontainer_worker(
                argv=spec["argv"],
                appcontainer_sid=identity["appcontainer_sid"],
                cwd=spec["cwd"], environment=spec["environment"])
            processes[condition] = process
            observation = dict(process.observation)
            observed_sid_match = (observation.get("appcontainer_sid") ==
                identity["appcontainer_sid"])
            observation.update({
                "protocol_id": protocol_id,
                "condition": condition,
                "profile_name": identity["profile_name"],
                "profile_local_data_path": identity[
                    "profile_local_data_path"],
                "profile_local_data_root_identity": identity[
                    "profile_local_data_root_identity"],
                "profile_sid_matches_observed_process_sid": observed_sid_match,
                "unaccounted_persistent_profile_state": True,
                "registry_state_inventory_verified": False,
                "authority": False,
            })
            if observed_sid_match is not True:
                raise WindowsAppContainerProcessError(
                    "appcontainer_worker_pair_process_sid_mismatch")
            observations[condition] = observation
    except Exception as launch_error:
        partial_observations = getattr(launch_error,
            "partial_worker_process_observations", {})
        if not isinstance(partial_observations, Mapping):
            partial_observations = {}
        else:
            partial_observations = dict(partial_observations)
        partial_observation = getattr(launch_error,
            "partial_worker_process_observation", None)
        if (launching_condition in _CONDITIONS
                and isinstance(partial_observation, Mapping)):
            partial_observations[launching_condition] = dict(
                partial_observation)
        partial_observations = {condition: dict(process.observation)
            for condition, process in processes.items()
            if isinstance(getattr(process, "observation", None), Mapping)
            and condition not in partial_observations} | partial_observations
        cleanup_errors: list[str] = []
        for process in reversed(tuple(processes.values())):
            try:
                process.terminate()
            except Exception:
                cleanup_errors.append("terminate_failed")
            try:
                process.close()
            except Exception:
                cleanup_errors.append("close_failed")
        launch_cleanup_errors = list(getattr(launch_error,
            "partial_worker_cleanup_errors", []))
        try:
            launch_error.partial_worker_process_observations = (
                partial_observations)
            launch_error.partial_worker_cleanup_errors = (
                launch_cleanup_errors + cleanup_errors)
        except (AttributeError, TypeError):
            pass
        if cleanup_errors:
            wrapped = WindowsAppContainerProcessError(
                "appcontainer_worker_pair_cleanup_failed:" +
                ",".join(cleanup_errors))
            wrapped.partial_worker_process_observations = partial_observations
            wrapped.partial_worker_cleanup_errors = (
                launch_cleanup_errors + cleanup_errors)
            raise wrapped from launch_error
        raise

    evidence = {"schema_version":
            "sentientos.windows_appcontainer_worker_pair_launch:v1",
        "protocol_id": protocol_id,
        "profile_pair_digest": checked_pair["profile_pair_digest"],
        "worker_observations": observations,
        "both_condition_sids_match_observed_process_tokens": True,
        "conversation_store_process_isolation_verified": False,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False}
    return processes, evidence


def launch_condition_appcontainer_worker_pair_with_pipes(*, protocol_id: str,
        protocol_digest: str,
        profile_pair: Mapping[str, Any],
        worker_specs: Mapping[str, Mapping[str, Any]],
        receipt_bundle_roots: Mapping[str, Path] | None = None,
        receipt_bundle_store_artifacts: Mapping[str, Mapping[str, Any]] | None = None,
        invocation_receipt_roots: Mapping[str, Path] | None = None,
        invocation_receipt_store_artifacts: Mapping[str, Mapping[str, Any]] | None = None,
        access_probe_manifests: Mapping[str, Mapping[str, Any]] | None = None,
        baseline_protocol: Mapping[str, Any] | None = None,
        baseline_runtime_manifests: Mapping[str, Mapping[str, Any]] | None = None
        ) -> tuple[dict[str, WindowsAppContainerProcess], dict[str, Any],
            dict[str, Any]]:
    """Create one restricted pipe per condition, then launch its worker pair.

    Pipe names and the supervisor's observed process identity are passed only
    through reserved bootstrap environment keys. This wires endpoint creation
    into startup, but workers still need a trusted dispatcher and resource ACL
    preflight before any experiment can use the processes.
    """
    from .durable_developmental_learning_experiment import _CONDITIONS
    from .windows_appcontainer_pipe import (
        create_condition_worker_pipe_endpoint,
        observe_current_pipe_supervisor)
    from .windows_appcontainer_profile import (
        verify_condition_appcontainer_profile_pair_result)
    from .local_model_authority import digest_payload
    from .windows_appcontainer_access import (
        verify_condition_worker_access_probe_manifest)

    if (not isinstance(protocol_id, str)
            or not isinstance(protocol_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", protocol_digest) is None
            or not isinstance(profile_pair, Mapping)
            or not isinstance(worker_specs, Mapping)
            or ((receipt_bundle_roots is None) !=
                (receipt_bundle_store_artifacts is None))
            or (receipt_bundle_roots is not None and
                (not isinstance(receipt_bundle_roots, Mapping)
                    or set(receipt_bundle_roots) != set(_CONDITIONS)))
            or (receipt_bundle_store_artifacts is not None and
                (not isinstance(receipt_bundle_store_artifacts, Mapping)
                    or set(receipt_bundle_store_artifacts) != set(_CONDITIONS)))
            or ((invocation_receipt_roots is None) !=
                (invocation_receipt_store_artifacts is None))
            or (invocation_receipt_roots is not None and
                (not isinstance(invocation_receipt_roots, Mapping)
                    or set(invocation_receipt_roots) != set(_CONDITIONS)))
            or (invocation_receipt_store_artifacts is not None and
                (not isinstance(invocation_receipt_store_artifacts, Mapping)
                    or set(invocation_receipt_store_artifacts) != set(_CONDITIONS)))
            or (access_probe_manifests is not None and
                (not isinstance(access_probe_manifests, Mapping)
                    or set(access_probe_manifests) != set(_CONDITIONS)))
            or ((baseline_protocol is None) !=
                (baseline_runtime_manifests is None))
            or (baseline_runtime_manifests is not None and
                (not isinstance(baseline_protocol, Mapping)
                    or not isinstance(baseline_runtime_manifests, Mapping)
                    or set(baseline_runtime_manifests) != set(_CONDITIONS)
                    or access_probe_manifests is not None))
            or ((receipt_bundle_roots is not None
                    or invocation_receipt_roots is not None)
                and baseline_runtime_manifests is None)
            or set(worker_specs) != set(_CONDITIONS)):
        raise WindowsAppContainerProcessError(
            "appcontainer_worker_pair_pipe_arguments_invalid")
    try:
        checked_pair = verify_condition_appcontainer_profile_pair_result(
            dict(profile_pair), protocol_id=protocol_id)
    except (TypeError, ValueError) as exc:
        raise WindowsAppContainerProcessError(
            "appcontainer_worker_pair_pipe_profile_binding_invalid") from exc
    if os.name != "nt":
        raise WindowsAppContainerProcessError("appcontainer_windows_only")

    supervisor = observe_current_pipe_supervisor()
    endpoints: dict[str, Any] = {}
    enriched_specs: dict[str, dict[str, Any]] = {}
    reserved = {"sentientos_worker_pipe_name",
        "sentientos_worker_appcontainer_sid",
        "sentientos_worker_protocol_id", "sentientos_worker_condition",
        "sentientos_worker_protocol_digest",
        "sentientos_supervisor_process_id",
        "sentientos_supervisor_creation_time_100ns",
        "sentientos_worker_receipt_bundle_root",
        "sentientos_worker_receipt_store_artifact_json",
        "sentientos_worker_invocation_receipt_root",
        "sentientos_worker_invocation_receipt_store_artifact_json",
        "sentientos_worker_access_probe_manifest_json",
        "sentientos_worker_baseline_protocol_json",
        "sentientos_worker_baseline_runtime_manifest_json"}
    checked_baseline_manifests: dict[str, Mapping[str, Any]] | None = None
    baseline_protocol_json: str | None = None
    if baseline_runtime_manifests is not None:
        from .durable_developmental_learning_experiment import (
            verify_durable_learning_protocol)
        from .durable_learning_condition_worker_backend import (
            verify_condition_worker_baseline_runtime_manifest)
        try:
            protocol_check = verify_durable_learning_protocol(baseline_protocol)
            if (baseline_protocol.get("protocol_id") != protocol_id
                    or baseline_protocol.get("protocol_digest") != protocol_digest):
                raise ValueError("baseline_protocol_binding_mismatch")
            checked_baseline_manifests = {}
            entrypoint_modules: set[str] = set()
            for condition in _CONDITIONS:
                spec = worker_specs[condition]
                argv = spec.get("argv") if isinstance(spec, Mapping) else None
                if (not isinstance(argv, Sequence)
                        or isinstance(argv, (str, bytes)) or len(argv) != 3
                        or tuple(argv[1:2]) != ("-m",)
                        or argv[2] not in {
                            "sentientos.durable_learning_condition_baseline_worker_entrypoint",
                            "sentientos.durable_learning_condition_recovery_worker_entrypoint"}):
                    raise ValueError("baseline_worker_entrypoint_not_pinned")
                entrypoint_modules.add(argv[2])
                sid = checked_pair["condition_profiles"][condition][
                    "appcontainer_sid"]
                checked_baseline_manifests[condition] = (
                    verify_condition_worker_baseline_runtime_manifest(
                        baseline_runtime_manifests[condition],
                        protocol=baseline_protocol, protocol_id=protocol_id,
                        protocol_digest=protocol_digest, condition=condition,
                        appcontainer_sid=sid))
            baseline_protocol_json = json.dumps(dict(baseline_protocol),
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                allow_nan=False)
            if (len(baseline_protocol_json.encode("utf-8")) > 24_000
                    or protocol_check.get("protocol_digest") != protocol_digest):
                raise ValueError("baseline_protocol_environment_payload_over_bound")
            recovery_entrypoint = entrypoint_modules == {
                "sentientos.durable_learning_condition_recovery_worker_entrypoint"}
            if (len(entrypoint_modules) != 1
                    or (recovery_entrypoint and (
                        receipt_bundle_roots is None
                        or invocation_receipt_roots is None))
                    or (not recovery_entrypoint and (
                        receipt_bundle_roots is not None
                        or invocation_receipt_roots is not None))):
                raise ValueError("baseline_worker_entrypoint_mode_mismatch")
        except (TypeError, ValueError) as exc:
            raise WindowsAppContainerProcessError(
                "appcontainer_worker_pair_baseline_binding_invalid") from exc
    try:
        for condition in _CONDITIONS:
            spec = worker_specs[condition]
            if (not isinstance(spec, Mapping)
                    or set(spec) != {"argv", "cwd", "environment"}
                    or not isinstance(spec["environment"], Mapping)):
                raise WindowsAppContainerProcessError(
                    "appcontainer_worker_pair_pipe_spec_invalid")
            identity = checked_pair["condition_profiles"][condition]
            environment = dict(spec["environment"])
            folded = {key.casefold() for key in environment
                if isinstance(key, str)}
            if folded & reserved:
                raise WindowsAppContainerProcessError(
                    "appcontainer_worker_pair_pipe_reserved_environment_key")
            endpoint = create_condition_worker_pipe_endpoint(
                protocol_id=protocol_id, condition=condition,
                package_sid=identity["appcontainer_sid"])
            endpoints[condition] = endpoint
            environment.update({
                "SENTIENTOS_WORKER_PIPE_NAME": endpoint.name,
                "SENTIENTOS_WORKER_APPCONTAINER_SID":
                    identity["appcontainer_sid"],
                "SENTIENTOS_WORKER_PROTOCOL_ID": protocol_id,
                "SENTIENTOS_WORKER_PROTOCOL_DIGEST": protocol_digest,
                "SENTIENTOS_WORKER_CONDITION": condition,
                "SENTIENTOS_SUPERVISOR_PROCESS_ID":
                    str(supervisor["process_id"]),
                "SENTIENTOS_SUPERVISOR_CREATION_TIME_100NS":
                    str(supervisor["process_creation_time_100ns"]),
            })
            if receipt_bundle_roots is not None:
                root = receipt_bundle_roots[condition]
                artifact = receipt_bundle_store_artifacts[condition]
                sid = identity["appcontainer_sid"]
                if (not isinstance(root, Path)
                        or not isinstance(artifact, Mapping)
                        or artifact.get("schema_version") !=
                            "sentientos.durable_learning_condition_receipt_bundle_store:v1"
                        or artifact.get("protocol_id") != protocol_id
                        or artifact.get("condition") != condition
                        or not isinstance(artifact.get("appcontainer_sid"), str)
                        or artifact["appcontainer_sid"].casefold() != sid.casefold()
                        or artifact.get("access_policy") != "condition_receipt_read"
                        or artifact.get("effective_access_verified") is not False
                        or artifact.get("peer_denial_verified") is not False
                        or artifact.get("bundle_receipt_authentication_verified") is not False
                        or artifact.get("authority") is not False):
                    raise WindowsAppContainerProcessError(
                        "appcontainer_worker_pair_receipt_artifact_invalid")
                semantic = {key: value for key, value in artifact.items()
                    if key != "artifact_digest"}
                if artifact.get("artifact_digest") != digest_payload(semantic):
                    raise WindowsAppContainerProcessError(
                        "appcontainer_worker_pair_receipt_artifact_digest_invalid")
                try:
                    resolved_root = root.resolve(strict=True)
                except (OSError, RuntimeError, ValueError) as exc:
                    raise WindowsAppContainerProcessError(
                        "appcontainer_worker_pair_receipt_root_invalid") from exc
                if not resolved_root.is_dir():
                    raise WindowsAppContainerProcessError(
                        "appcontainer_worker_pair_receipt_root_invalid")
                environment.update({
                    "SENTIENTOS_WORKER_RECEIPT_BUNDLE_ROOT": str(resolved_root),
                    "SENTIENTOS_WORKER_RECEIPT_STORE_ARTIFACT_JSON":
                        json.dumps(dict(artifact), sort_keys=True,
                            separators=(",", ":"), ensure_ascii=True),
                })
            if invocation_receipt_roots is not None:
                root = invocation_receipt_roots[condition]
                artifact = invocation_receipt_store_artifacts[condition]
                sid = identity["appcontainer_sid"]
                if (not isinstance(root, Path)
                        or not isinstance(artifact, Mapping)
                        or artifact.get("schema_version") !=
                            "sentientos.durable_learning_condition_invocation_receipt_store:v1"
                        or artifact.get("protocol_id") != protocol_id
                        or artifact.get("protocol_digest") != protocol_digest
                        or artifact.get("condition") != condition
                        or not isinstance(artifact.get("appcontainer_sid"), str)
                        or artifact["appcontainer_sid"].casefold() != sid.casefold()
                        or artifact.get("access_policy") != "condition_receipt_read"
                        or artifact.get("effective_access_verified") is not False
                        or artifact.get("peer_denial_verified") is not False
                        or artifact.get("source_receipts_reverified") is not True
                        or artifact.get("authority") is not False):
                    raise WindowsAppContainerProcessError(
                        "appcontainer_worker_pair_invocation_receipt_artifact_invalid")
                semantic = {key: value for key, value in artifact.items()
                    if key != "artifact_digest"}
                if artifact.get("artifact_digest") != digest_payload(semantic):
                    raise WindowsAppContainerProcessError(
                        "appcontainer_worker_pair_invocation_receipt_artifact_digest_invalid")
                try:
                    resolved_root = root.resolve(strict=True)
                except (OSError, RuntimeError, ValueError) as exc:
                    raise WindowsAppContainerProcessError(
                        "appcontainer_worker_pair_invocation_receipt_root_invalid") from exc
                if not resolved_root.is_dir():
                    raise WindowsAppContainerProcessError(
                        "appcontainer_worker_pair_invocation_receipt_root_invalid")
                environment.update({
                    "SENTIENTOS_WORKER_INVOCATION_RECEIPT_ROOT": str(resolved_root),
                    "SENTIENTOS_WORKER_INVOCATION_RECEIPT_STORE_ARTIFACT_JSON":
                        json.dumps(dict(artifact), sort_keys=True,
                            separators=(",", ":"), ensure_ascii=True),
                })
            if access_probe_manifests is not None:
                manifest = verify_condition_worker_access_probe_manifest(
                    access_probe_manifests[condition],
                    protocol_id=protocol_id, condition=condition,
                    appcontainer_sid=identity["appcontainer_sid"])
                environment["SENTIENTOS_WORKER_ACCESS_PROBE_MANIFEST_JSON"] = (
                    json.dumps(dict(manifest), sort_keys=True,
                        separators=(",", ":"), ensure_ascii=True))
            if checked_baseline_manifests is not None:
                environment["SENTIENTOS_WORKER_BASELINE_PROTOCOL_JSON"] = (
                    baseline_protocol_json)
                environment[
                    "SENTIENTOS_WORKER_BASELINE_RUNTIME_MANIFEST_JSON"] = (
                    json.dumps(dict(checked_baseline_manifests[condition]),
                        sort_keys=True, separators=(",", ":"),
                        ensure_ascii=True, allow_nan=False))
            enriched_specs[condition] = {"argv": spec["argv"],
                "cwd": spec["cwd"], "environment": environment}
        processes, evidence = launch_condition_appcontainer_worker_pair(
            protocol_id=protocol_id, profile_pair=checked_pair,
            worker_specs=enriched_specs)
    except Exception as launch_error:
        cleanup_errors: list[str] = []
        for endpoint in reversed(tuple(endpoints.values())):
            try:
                endpoint.close()
            except Exception:
                cleanup_errors.append("pipe_close_failed")
        try:
            launch_error.partial_created_endpoint_conditions = list(endpoints)
            launch_error.partial_pipe_cleanup_errors = list(cleanup_errors)
        except (AttributeError, TypeError):
            pass
        if cleanup_errors:
            wrapped = WindowsAppContainerProcessError(
                "appcontainer_worker_pair_pipe_cleanup_failed:" +
                ",".join(cleanup_errors))
            wrapped.partial_worker_process_observations = getattr(
                launch_error, "partial_worker_process_observations", {})
            wrapped.partial_worker_cleanup_errors = getattr(
                launch_error, "partial_worker_cleanup_errors", [])
            wrapped.partial_created_endpoint_conditions = list(endpoints)
            wrapped.partial_pipe_cleanup_errors = list(cleanup_errors)
            raise wrapped from launch_error
        raise

    evidence.update({
        "pipe_endpoints_created_for_both_conditions": True,
        "pipe_names_by_condition": {condition: endpoint.name
            for condition, endpoint in endpoints.items()},
        "supervisor_process_id": supervisor["process_id"],
        "supervisor_process_creation_time_100ns":
            supervisor["process_creation_time_100ns"],
        "environment_block_sha256_by_condition": {
            condition: process.observation.get("environment_block_sha256")
            for condition, process in processes.items()},
        "receipt_store_artifact_digest_by_condition": (
            {condition: receipt_bundle_store_artifacts[condition].get(
                "artifact_digest") for condition in _CONDITIONS}
            if receipt_bundle_store_artifacts is not None else {}),
        "access_probe_manifest_digest_by_condition": (
            {condition: access_probe_manifests[condition].get(
                "manifest_digest") for condition in _CONDITIONS}
            if access_probe_manifests is not None else {}),
        "baseline_runtime_manifest_digest_by_condition": (
            {condition: checked_baseline_manifests[condition].get(
                "manifest_digest") for condition in _CONDITIONS}
            if checked_baseline_manifests is not None else {}),
        "baseline_protocol_environment_bound":
            checked_baseline_manifests is not None,
        "rpc_dispatch_verified": False,
        "filesystem_isolation_verified": False,
        "retention_contrast_eligible": False,
        "authority": False,
    })
    return processes, evidence, endpoints
