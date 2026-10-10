"""Read-only, reparse-safe bounded Windows custody reads.

This helper deliberately supports only local drive paths and regular files
under an explicit directory. It does not publish or mutate custody.
"""
from __future__ import annotations

import os
import stat
import struct
from pathlib import Path


class WindowsHandleCustodyError(ValueError):
    """The requested Windows custody read could not be proven safe."""


def read_explicit_file(path: Path, *, max_bytes: int) -> bytes:
    """Read one explicit regular file without following links or racing replacement."""
    if type(max_bytes) is not int or max_bytes < 1:
        raise WindowsHandleCustodyError("explicit_file_limit_invalid")
    source = Path(path)
    if os.name == "nt":
        entries = read_regular_files(source.parent, max_entries=1,
            max_file_bytes=max_bytes, max_total_bytes=max_bytes,
            selected_names=(source.name,))
        if not entries:
            raise WindowsHandleCustodyError("explicit_file_missing")
        if len(entries) != 1 or entries[0][0] != source.name:
            raise WindowsHandleCustodyError("explicit_file_missing_or_ambiguous")
        return entries[0][1]
    descriptor: int | None = None
    parent_descriptor: int | None = None
    try:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        directory = getattr(os, "O_DIRECTORY", None)
        if nofollow is None or directory is None or not os.supports_dir_fd.__contains__(os.open):
            raise WindowsHandleCustodyError("explicit_file_safe_open_unsupported")
        absolute = Path(os.path.abspath(source))
        if not absolute.name or absolute.name in {".", ".."}:
            raise WindowsHandleCustodyError("explicit_file_path_invalid")
        parent_descriptor = os.open(os.sep, os.O_RDONLY | directory)
        for component in absolute.parts[1:-1]:
            if component in {"", ".", ".."}:
                raise WindowsHandleCustodyError("explicit_file_path_component_invalid")
            next_parent = os.open(component, os.O_RDONLY | directory | nofollow,
                                  dir_fd=parent_descriptor)
            parent_metadata = os.fstat(next_parent)
            if not stat.S_ISDIR(parent_metadata.st_mode):
                os.close(next_parent)
                raise WindowsHandleCustodyError("explicit_file_parent_not_directory")
            os.close(parent_descriptor)
            parent_descriptor = next_parent
        descriptor = os.open(absolute.name,
            os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0), dir_fd=parent_descriptor)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes or before.st_nlink != 1):
            raise WindowsHandleCustodyError("explicit_file_changed_during_open")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk); remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (len(data) > max_bytes or len(data) != before.st_size
                or after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns
                or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
            raise WindowsHandleCustodyError("explicit_file_changed_during_read")
        return data
    except WindowsHandleCustodyError:
        raise
    except FileNotFoundError as exc:
        raise WindowsHandleCustodyError("explicit_file_missing") from exc
    except OSError as exc:
        raise WindowsHandleCustodyError("explicit_file_unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def read_regular_files(root: Path, *, max_entries: int, max_file_bytes: int,
                       max_total_bytes: int, suffix: str = ".json",
                       selected_names: tuple[str, ...] | None = None) -> list[tuple[str, bytes]]:
    """Read bounded regular files through bound Windows handles.

    Win32 path opens are not used for descendants.  The configured root is
    walked component-by-component from the volume root with NtCreateFile,
    OBJ_DONT_REPARSE, and FILE_OPEN_REPARSE_POINT.  Children are then opened
    relative to the held directory handle.  Read-only sharing deliberately
    denies concurrent write/delete opens; unsupported filesystems/APIs fail
    closed.  This code is syntax-checked on non-Windows hosts, not runtime
    verified there.
    """
    invalid_names = selected_names is not None and (
        not isinstance(selected_names, tuple) or len(selected_names) > max_entries
        or any(not isinstance(name, str) or not name or name in {".", ".."}
            or "/" in name or "\\" in name for name in selected_names)
        or (isinstance(selected_names, tuple) and len(selected_names) != len(set(selected_names))))
    if (type(max_entries) is not int or max_entries < 1
            or type(max_file_bytes) is not int or max_file_bytes < 1
            or type(max_total_bytes) is not int or max_total_bytes < 1
            or not isinstance(suffix, str) or "/" in suffix or "\\" in suffix
            or invalid_names):
        raise WindowsHandleCustodyError("windows_custody_read_limits_invalid")
    if os.name != "nt":
        raise WindowsHandleCustodyError("windows_custody_reader_on_non_windows")
    import ctypes
    from ctypes import wintypes
    from pathlib import PureWindowsPath

    class UNICODE_STRING(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT),
                    ("Buffer", wintypes.LPWSTR)]

    class OBJECT_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Length", wintypes.ULONG), ("RootDirectory", wintypes.HANDLE),
                    ("ObjectName", ctypes.POINTER(UNICODE_STRING)), ("Attributes", wintypes.ULONG),
                    ("SecurityDescriptor", ctypes.c_void_p), ("SecurityQualityOfService", ctypes.c_void_p)]

    class IO_STATUS_BLOCK(ctypes.Structure):
        _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

    class FILE_ID_INFO(ctypes.Structure):
        _fields_ = [("VolumeSerialNumber", ctypes.c_ulonglong), ("FileId", ctypes.c_ubyte * 16)]

    class FILE_STANDARD_INFO(ctypes.Structure):
        _fields_ = [("AllocationSize", ctypes.c_longlong), ("EndOfFile", ctypes.c_longlong),
                    ("NumberOfLinks", wintypes.ULONG), ("DeletePending", wintypes.BOOLEAN),
                    ("Directory", wintypes.BOOLEAN)]

    class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
        _fields_ = [("FileAttributes", wintypes.ULONG), ("ReparseTag", wintypes.ULONG)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    create_file = kernel32.CreateFileW
    create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    get_info = kernel32.GetFileInformationByHandleEx
    get_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    read_file = kernel32.ReadFile
    read_file.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    read_file.restype = wintypes.BOOL
    nt_create = ntdll.NtCreateFile
    nt_create.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
        ctypes.POINTER(OBJECT_ATTRIBUTES), ctypes.POINTER(IO_STATUS_BLOCK), ctypes.c_void_p,
        wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG]
    nt_create.restype = ctypes.c_long
    nt_query_dir = ntdll.NtQueryDirectoryFile
    nt_query_dir.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(IO_STATUS_BLOCK), ctypes.c_void_p, wintypes.ULONG, ctypes.c_int,
        wintypes.BOOLEAN, ctypes.POINTER(UNICODE_STRING), wintypes.BOOLEAN]
    nt_query_dir.restype = ctypes.c_long
    nt_query_file = ntdll.NtQueryInformationFile
    nt_query_file.argtypes = [wintypes.HANDLE, ctypes.POINTER(IO_STATUS_BLOCK), ctypes.c_void_p,
                              wintypes.ULONG, ctypes.c_int]
    nt_query_file.restype = ctypes.c_long

    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    FILE_READ_ATTRIBUTES, FILE_LIST_DIRECTORY, SYNCHRONIZE = 0x80, 0x1, 0x100000
    FILE_SHARE_READ = 0x1
    OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT = 3, 0x02000000, 0x00200000
    FILE_OPEN, FILE_DIRECTORY_FILE, FILE_NON_DIRECTORY_FILE = 1, 0x1, 0x40
    FILE_SYNCHRONOUS_IO_NONALERT, FILE_OPEN_REPARSE_POINT = 0x20, 0x00200000
    OBJ_CASE_INSENSITIVE, OBJ_DONT_REPARSE = 0x40, 0x1000
    STATUS_NO_MORE_FILES = 0x80000006
    STATUS_OBJECT_NAME_NOT_FOUND = 0xC0000034
    STATUS_OBJECT_PATH_NOT_FOUND = 0xC000003A
    FILE_ATTRIBUTE_REPARSE_POINT = 0x400

    def fail(code: str, cause: BaseException | None = None) -> None:
        error = WindowsHandleCustodyError(code)
        if cause is None:
            raise error
        raise error from cause

    def nt_open(parent: int | None, name: str, *, directory: bool) -> int:
        backing = ctypes.create_unicode_buffer(name)
        byte_length = len(name.encode("utf-16-le"))
        unicode_name = UNICODE_STRING(byte_length, byte_length + 2, ctypes.cast(backing, wintypes.LPWSTR))
        attrs = OBJECT_ATTRIBUTES(ctypes.sizeof(OBJECT_ATTRIBUTES), wintypes.HANDLE(parent or 0),
            ctypes.pointer(unicode_name), OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE, None, None)
        handle = wintypes.HANDLE()
        iosb = IO_STATUS_BLOCK()
        access = FILE_READ_ATTRIBUTES | SYNCHRONIZE | (FILE_LIST_DIRECTORY if directory else 0x1)
        options = (FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE) | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT
        status = nt_create(ctypes.byref(handle), access, ctypes.byref(attrs), ctypes.byref(iosb), None,
            0, FILE_SHARE_READ, FILE_OPEN, options, None, 0)
        if (status & 0xFFFFFFFF) in {STATUS_OBJECT_NAME_NOT_FOUND, STATUS_OBJECT_PATH_NOT_FOUND}:
            fail("explicit_file_missing")
        if status < 0 or not handle.value:
            fail("cognition_observation_windows_open_failed")
        return int(handle.value)

    def file_id(handle: int) -> tuple[int, bytes]:
        value = FILE_ID_INFO()
        if not get_info(wintypes.HANDLE(handle), 18, ctypes.byref(value), ctypes.sizeof(value)):
            fail("cognition_observation_windows_identity_unavailable")
        return int(value.VolumeSerialNumber), bytes(value.FileId)

    def attrs_and_standard(handle: int) -> tuple[int, FILE_STANDARD_INFO]:
        tag = FILE_ATTRIBUTE_TAG_INFO()
        standard = FILE_STANDARD_INFO()
        iosb = IO_STATUS_BLOCK()
        if (not get_info(wintypes.HANDLE(handle), 9, ctypes.byref(tag), ctypes.sizeof(tag))
                or nt_query_file(wintypes.HANDLE(handle), ctypes.byref(iosb), ctypes.byref(standard),
                                 ctypes.sizeof(standard), 5) < 0):
            fail("cognition_observation_windows_metadata_unavailable")
        if tag.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
            fail("cognition_observation_windows_reparse_point")
        return int(tag.FileAttributes), standard

    def close(handle: int | None) -> None:
        if handle is not None and not close_handle(wintypes.HANDLE(handle)):
            fail("cognition_observation_windows_close_failed")

    path = PureWindowsPath(os.path.abspath(root))
    # Reject UNC/device paths: walking from a local volume root is required to
    # validate every parent component without following junctions.
    if not path.drive or path.drive.startswith("\\") or not path.is_absolute():
        fail("cognition_observation_windows_root_form_unsupported")
    volume_root = path.drive + "\\"
    current: int | None = None
    opened_handles: list[int] = []
    try:
        current_raw = create_file(volume_root, FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
            FILE_SHARE_READ, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, None)
        if current_raw == INVALID_HANDLE_VALUE:
            fail("cognition_observation_windows_root_open_failed")
        current = int(current_raw); opened_handles.append(current)
        attrs, standard = attrs_and_standard(current)
        if not standard.Directory:
            fail("cognition_observation_windows_root_not_directory")
        for component in path.parts[1:]:
            if component in {"", ".", "..", "\\"}:
                fail("cognition_observation_windows_root_component_invalid")
            child = nt_open(current, component, directory=True)
            opened_handles.append(child)
            attrs, standard = attrs_and_standard(child)
            if not standard.Directory:
                fail("cognition_observation_windows_root_not_directory")
            current = child

        root_handle = current
        root_identity = file_id(root_handle)
        entries: list[tuple[str, int]] = []
        observed_entries = 0
        if selected_names is not None:
            entries = [(name, 0) for name in selected_names]
        else:
            directory_buffer = ctypes.create_string_buffer(65_536)
            restart = True
            while True:
                iosb = IO_STATUS_BLOCK()
                status = nt_query_dir(wintypes.HANDLE(root_handle), None, None, None, ctypes.byref(iosb),
                    directory_buffer, len(directory_buffer), 1, False, None, restart)
                restart = False
                unsigned_status = status & 0xFFFFFFFF
                if unsigned_status == STATUS_NO_MORE_FILES:
                    break
                if status < 0 or iosb.Information > len(directory_buffer):
                    fail("cognition_observation_windows_directory_read_failed")
                if iosb.Information == 0:
                    fail("cognition_observation_windows_directory_empty_response")
                offset = 0
                while offset < iosb.Information:
                    if iosb.Information - offset < 64:
                        fail("cognition_observation_windows_directory_entry_invalid")
                    next_offset, _index = struct.unpack_from("<II", directory_buffer.raw, offset)
                    attrs_value = struct.unpack_from("<I", directory_buffer.raw, offset + 56)[0]
                    name_length = struct.unpack_from("<I", directory_buffer.raw, offset + 60)[0]
                    if name_length % 2 or name_length > 1024 or offset + 64 + name_length > iosb.Information:
                        fail("cognition_observation_windows_directory_entry_invalid")
                    name = directory_buffer.raw[offset + 64:offset + 64 + name_length].decode("utf-16-le")
                    observed_entries += 1
                    if observed_entries > max_entries:
                        fail("cognition_observation_retention_limit_exceeded")
                    if name not in {".", ".."} and name.endswith(suffix):
                        if attrs_value & FILE_ATTRIBUTE_REPARSE_POINT:
                            fail("cognition_observation_windows_reparse_point")
                        entries.append((name, attrs_value))
                    if next_offset == 0:
                        break
                    if next_offset < 64 or offset + next_offset > iosb.Information:
                        fail("cognition_observation_windows_directory_entry_invalid")
                    offset += next_offset
                if len(entries) > max_entries:
                    fail("cognition_observation_retention_limit_exceeded")
        if file_id(root_handle) != root_identity:
            fail("cognition_observation_windows_root_identity_changed")
        result: list[tuple[str, bytes]] = []
        total = 0
        for name, _directory_attrs in sorted(entries):
            if not name or "\\" in name or "/" in name or name in {".", ".."}:
                fail("cognition_observation_not_regular")
            handle = nt_open(root_handle, name, directory=False)
            try:
                before_id = file_id(handle)
                attrs, standard = attrs_and_standard(handle)
                if standard.Directory or standard.EndOfFile < 0 or standard.EndOfFile > max_file_bytes:
                    fail("cognition_observation_not_regular")
                if standard.NumberOfLinks != 1:
                    fail("cognition_observation_windows_file_alias_rejected")
                size = int(standard.EndOfFile)
                data = bytearray()
                while len(data) <= max_file_bytes:
                    amount = min(65_536, max_file_bytes + 1 - len(data))
                    if amount <= 0:
                        break
                    buffer = ctypes.create_string_buffer(amount)
                    read_count = wintypes.DWORD()
                    if not read_file(wintypes.HANDLE(handle), buffer, amount, ctypes.byref(read_count), None):
                        fail("cognition_observation_windows_read_failed")
                    if not read_count.value:
                        break
                    data.extend(buffer.raw[:read_count.value])
                after_attrs, after_standard = attrs_and_standard(handle)
                if (len(data) != size or int(after_standard.EndOfFile) != size
                        or file_id(handle) != before_id or file_id(root_handle) != root_identity):
                    fail("cognition_observation_windows_file_changed")
                total += len(data)
                if total > max_total_bytes:
                    fail("cognition_observation_retention_limit_exceeded")
                result.append((name, bytes(data)))
            finally:
                close(handle)
        return result
    except WindowsHandleCustodyError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        fail("cognition_observation_windows_recovery_failed", exc)
    finally:
        for handle in reversed(opened_handles):
            close(handle)

