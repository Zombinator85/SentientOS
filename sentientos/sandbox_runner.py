"""Tiny sandbox wrapper enforcing resource limits when spawning subprocesses."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def run(
    command: Sequence[str],
    *,
    timeout: Optional[float] = None,
    cpu_seconds: int = 2,
    memory_mb: int = 256,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> SandboxResult:
    """Execute *command* within a constrained subprocess sandbox."""

    if sys.platform == "win32":
        return _run_windows(command, timeout, cpu_seconds, memory_mb, cwd, env)
    return _run_posix(command, timeout, cpu_seconds, memory_mb, cwd, env)


def _run_posix(
    command: Sequence[str],
    timeout: Optional[float],
    cpu_seconds: int,
    memory_mb: int,
    cwd: Optional[str],
    env: Optional[Mapping[str, str]],
) -> SandboxResult:
    import resource

    def _limits() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        memory_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

    proc = subprocess.Popen(
        command,
        cwd=cwd,
        env=None if env is None else {**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=_limits,
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        timed_out = True
    return SandboxResult(proc.returncode, stdout, stderr, timed_out)


def _run_windows(
    command: Sequence[str],
    timeout: Optional[float],
    cpu_seconds: int,
    memory_mb: int,
    cwd: Optional[str],
    env: Optional[Mapping[str, str]],
) -> SandboxResult:
    # CPython exposes this Windows-only flag at runtime, while POSIX stubs do not.
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    job = None
    try:
        import ctypes
        import ctypes.wintypes

        ctypes_api: Any = ctypes
        windows_types: Any = ctypes_api.wintypes
        kernel32 = ctypes_api.windll.kernel32
        job = kernel32.CreateJobObjectW(None, None)
        info_class = 9  # JobObjectExtendedLimitInformation
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", windows_types.LARGE_INTEGER),
                ("PerJobUserTimeLimit", windows_types.LARGE_INTEGER),
                ("LimitFlags", windows_types.DWORD),
                ("MinimumWorkingSetSize", windows_types.SIZE_T),
                ("MaximumWorkingSetSize", windows_types.SIZE_T),
                ("ActiveProcessLimit", windows_types.DWORD),
                ("Affinity", windows_types.ULONG_PTR),
                ("PriorityClass", windows_types.DWORD),
                ("SchedulingClass", windows_types.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", windows_types.ULONG64),
                ("WriteOperationCount", windows_types.ULONG64),
                ("OtherOperationCount", windows_types.ULONG64),
                ("ReadTransferCount", windows_types.ULONG64),
                ("WriteTransferCount", windows_types.ULONG64),
                ("OtherTransferCount", windows_types.ULONG64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", windows_types.SIZE_T),
                ("JobMemoryLimit", windows_types.SIZE_T),
                ("PeakProcessMemoryUsed", windows_types.SIZE_T),
                ("PeakJobMemoryUsed", windows_types.SIZE_T),
            ]

        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x100
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY
        limits.ProcessMemoryLimit = windows_types.SIZE_T(memory_mb * 1024 * 1024)
        kernel32.SetInformationJobObject(job, info_class, ctypes_api.byref(limits), ctypes_api.sizeof(limits))
    except Exception:
        job = None

    proc = subprocess.Popen(
        command,
        cwd=cwd,
        env=None if env is None else {**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    if job is not None:
        ctypes_api.windll.kernel32.AssignProcessToJobObject(
            job, getattr(proc, "_handle"))
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        timed_out = True
    return SandboxResult(proc.returncode, stdout, stderr, timed_out)


__all__ = ["run", "SandboxResult"]
