"""Disposable native Windows durability research, with no replay publication API."""
from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, cast

from sentientos.windows_handle_custody import verify_private_handle_acl


def main() -> None:
    if os.name != "nt":
        print(json.dumps({"status": "native_windows_required"}))
        return
    import ctypes
    from ctypes import wintypes

    get_last_error = cast(Callable[[], int], getattr(ctypes, "get_last_error"))
    set_last_error = cast(Callable[[int], int], getattr(ctypes, "set_last_error"))
    kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    ntdll = getattr(ctypes, "WinDLL")("ntdll")
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    flush = kernel.FlushFileBuffers
    flush.argtypes = [wintypes.HANDLE]
    flush.restype = wintypes.BOOL
    write = kernel.WriteFile
    write.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    write.restype = wintypes.BOOL

    class IO_STATUS_BLOCK(ctypes.Structure):
        _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

    nt_flush = ntdll.NtFlushBuffersFile
    nt_flush.argtypes = [wintypes.HANDLE, ctypes.POINTER(IO_STATUS_BLOCK)]
    nt_flush.restype = ctypes.c_long
    invalid = ctypes.c_void_p(-1).value
    identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
    sid = next(csv.reader([identity]))[1]
    results: list[dict[str, object]] = []
    with TemporaryDirectory(prefix="sentientos-directory-flush-probe-") as temporary:
        root = Path(temporary)
        for args in (
            ["/grant:r", f"*{sid}:(OI)(CI)(F)", "*S-1-5-18:(OI)(CI)(F)", "*S-1-5-32-544:(OI)(CI)(F)"],
            ["/inheritance:r"], ["/setowner", f"*{sid}"],
        ):
            subprocess.run(["icacls", str(root), *args], check=True,
                           capture_output=True, text=True, timeout=20)
        for write_through in (False, True):
            flags = 0x02000000 | 0x00200000 | (0x80000000 if write_through else 0)
            handle = create(str(root), 0xC0000000, 0, None, 3, flags, None)
            if handle == invalid:
                results.append({"directory_write_through": write_through,
                    "directory_open_error": get_last_error()})
                continue
            try:
                verify_private_handle_acl(int(handle))
                set_last_error(0)
                flushed = bool(flush(handle))
                flush_error = get_last_error()
                iosb = IO_STATUS_BLOCK()
                status = nt_flush(handle, ctypes.byref(iosb))
                row: dict[str, object] = {
                    "directory_write_through": write_through,
                    "directory_private_acl_verified": True,
                    "directory_flush_file_buffers": flushed,
                    "directory_flush_error": flush_error,
                    "directory_nt_flush_status": hex(status & 0xFFFFFFFF),
                }
                path = root / f"control-{write_through}.bin"
                control = create(str(path), 0xC0000000, 0, None, 1, 0x80200000, None)
                if control == invalid:
                    row["control_open_error"] = get_last_error()
                else:
                    try:
                        data = ctypes.create_string_buffer(b"probe")
                        count = wintypes.DWORD()
                        row["control_write"] = bool(write(control, data, 5, ctypes.byref(count), None))
                        row["control_bytes_written"] = int(count.value)
                        set_last_error(0)
                        row["control_flush"] = bool(flush(control))
                        row["control_flush_error"] = get_last_error()
                    finally:
                        if not close(control):
                            raise OSError("control_handle_close_failed")
                results.append(row)
            finally:
                if not close(handle):
                    raise OSError("directory_handle_close_failed")
    print(json.dumps({"schema_version": "sentientos.windows_directory_flush_probe:v1",
        "status": "diagnostic_only", "runtime_publication_authority": False,
        "results": results}, sort_keys=True))


if __name__ == "__main__":
    main()
