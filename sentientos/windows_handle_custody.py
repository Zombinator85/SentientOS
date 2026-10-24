"""Read-only, reparse-safe bounded Windows custody reads.

This helper deliberately supports only local drive paths and regular files
under an explicit directory. It does not publish or mutate custody.
"""
from __future__ import annotations

import os
import stat
import struct
from pathlib import Path
from typing import Literal, NoReturn, overload


class WindowsHandleCustodyError(ValueError):
    """The requested Windows custody read could not be proven safe."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _safe_child_name(name: object) -> bool:
    """Accept one literal Windows component, never a stream or path expression."""
    if (not isinstance(name, str) or not name or name in {".", ".."}
            or name.endswith((".", " "))
            or any(ord(character) < 32 or character in '<>:"/\\|?*' for character in name)):
        return False
    try:
        return len(name.encode("utf-16-le")) <= 510
    except UnicodeEncodeError:
        return False


def verify_private_handle_acl(handle: int) -> None:
    """Require current-user ownership and deny broad data readers or writers.

    The check is performed against the same handle used by the bounded reader.
    Only the current user, LocalSystem, and local Administrators may receive
    data-read or data-write rights. Unsupported or conditional ACE forms fail
    closed. Write grants matter because they let an untrusted principal replace
    a locally pinned trust root even when the reader itself is race-safe.
    """
    _verify_handle_acl(handle, require_private=True)


def verify_replay_ancestor_handle_acl(handle: int) -> None:
    """Reject ancestry whose owner or replacement rights can reset replay custody.

    Public directory traversal/read and child creation are permitted. Existing
    private children must not be removable by an untrusted parent owner, delete-
    child grant, ownership grant, or DACL grant. TrustedInstaller is trusted only
    for OS ancestry; it receives no private replay-file grant here.
    """
    _verify_handle_acl(handle, require_private=False)


def _verify_handle_acl(handle: int, *, require_private: bool) -> None:
    if os.name != "nt" or type(handle) is not int or handle <= 0:
        raise WindowsHandleCustodyError("private_acl_handle_invalid")
    import ctypes
    from ctypes import wintypes

    advapi = getattr(ctypes, "WinDLL")("advapi32", use_last_error=True)
    kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    get_security = advapi.GetSecurityInfo
    get_security.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p)]
    get_security.restype = wintypes.DWORD
    get_acl_info = advapi.GetAclInformation
    get_acl_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_int]
    get_acl_info.restype = wintypes.BOOL
    get_ace = advapi.GetAce
    get_ace.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    get_ace.restype = wintypes.BOOL
    equal_sid = advapi.EqualSid
    equal_sid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    equal_sid.restype = wintypes.BOOL
    is_valid_sid = advapi.IsValidSid
    is_valid_sid.argtypes = [ctypes.c_void_p]
    is_valid_sid.restype = wintypes.BOOL
    sid_length = advapi.GetLengthSid
    sid_length.argtypes = [ctypes.c_void_p]
    sid_length.restype = wintypes.DWORD
    convert_sid = advapi.ConvertStringSidToSidW
    convert_sid.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    convert_sid.restype = wintypes.BOOL
    open_token = advapi.OpenProcessToken
    open_token.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    open_token.restype = wintypes.BOOL
    token_info = advapi.GetTokenInformation
    token_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    token_info.restype = wintypes.BOOL
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p
    get_process = kernel32.GetCurrentProcess
    get_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    status = get_security(wintypes.HANDLE(handle), 1, 0x1 | 0x4,
        ctypes.byref(owner), None, ctypes.byref(dacl), None,
        ctypes.byref(descriptor))
    if status != 0 or not owner.value or not dacl.value or not descriptor.value:
        raise WindowsHandleCustodyError("private_acl_unavailable")

    token = wintypes.HANDLE()
    known_sids: list[ctypes.c_void_p] = []
    try:
        needed = wintypes.DWORD()
        if not open_token(get_process(), 0x0008, ctypes.byref(token)):
            raise WindowsHandleCustodyError("private_acl_current_user_unavailable")
        token_info(token, 1, None, 0, ctypes.byref(needed))
        if needed.value < ctypes.sizeof(ctypes.c_void_p) or needed.value > 65536:
            raise WindowsHandleCustodyError("private_acl_token_user_invalid")
        token_buffer = ctypes.create_string_buffer(needed.value)
        if not token_info(token, 1, token_buffer, needed.value, ctypes.byref(needed)):
            raise WindowsHandleCustodyError("private_acl_current_user_unavailable")
        current_user = ctypes.cast(token_buffer, ctypes.POINTER(ctypes.c_void_p)).contents
        if not current_user.value:
            raise WindowsHandleCustodyError("private_acl_owner_mismatch")

        trusted: list[ctypes.c_void_p] = [current_user]
        trusted_names = ["S-1-5-18", "S-1-5-32-544"]
        if not require_private:
            trusted_names.append(
                "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464")
        for sid_text in trusted_names:
            sid = ctypes.c_void_p()
            if not convert_sid(sid_text, ctypes.byref(sid)) or not sid.value:
                raise WindowsHandleCustodyError("private_acl_trusted_sid_unavailable")
            known_sids.append(sid)
            trusted.append(sid)
        if require_private:
            if not equal_sid(owner, current_user):
                raise WindowsHandleCustodyError("private_acl_owner_mismatch")
        elif not any(equal_sid(owner, sid) for sid in trusted):
            raise WindowsHandleCustodyError("ancestor_acl_owner_untrusted")

        class ACL_SIZE_INFORMATION(ctypes.Structure):
            _fields_ = [("AceCount", wintypes.DWORD),
                ("AclBytesInUse", wintypes.DWORD), ("AclBytesFree", wintypes.DWORD)]

        info = ACL_SIZE_INFORMATION()
        if not get_acl_info(dacl, ctypes.byref(info), ctypes.sizeof(info), 2):
            raise WindowsHandleCustodyError("private_acl_structure_invalid")
        if info.AceCount > 4096:
            raise WindowsHandleCustodyError("private_acl_ace_bound_exceeded")
        read_mask = 0x80000000 | 0x10000000 | 0x00000001 | 0x00000008 | 0x00000080 | 0x00020000
        write_mask = (
            0x40000000 | 0x10000000 | 0x00000002 | 0x00000004
            | 0x00000010 | 0x00000040 | 0x00000100 | 0x00010000
            | 0x00040000 | 0x00080000 | 0x01000000
        )
        if not require_private:
            read_mask = 0
            write_mask = 0x10000000 | 0x40 | 0x10000 | 0x40000 | 0x80000 | 0x01000000
        for index in range(info.AceCount):
            ace = ctypes.c_void_p()
            if not get_ace(dacl, index, ctypes.byref(ace)) or not ace.value:
                raise WindowsHandleCustodyError("private_acl_ace_unavailable")
            header = ctypes.string_at(ace, 4)
            ace_type, ace_flags = header[0], header[1]
            ace_size = struct.unpack_from("<H", header, 2)[0]
            if ace_size < 16:
                raise WindowsHandleCustodyError("private_acl_ace_size_invalid")
            if ace_flags & 0x08:  # inherit-only ACE does not grant this handle access
                continue
            if ace_type == 1:  # ACCESS_DENIED_ACE_TYPE
                continue
            if ace_type != 0:  # conditional/object grants need a richer evaluator
                raise WindowsHandleCustodyError("private_acl_ace_form_unsupported")
            mask = struct.unpack_from("<I", ctypes.string_at(ace, 8), 4)[0]
            if not (mask & (read_mask | write_mask)):
                continue
            sid_ptr = ctypes.c_void_p(ace.value + 8)
            if (not is_valid_sid(sid_ptr) or sid_length(sid_ptr) > ace_size - 8):
                raise WindowsHandleCustodyError("private_acl_ace_sid_invalid")
            if not any(equal_sid(sid_ptr, trusted_sid) for trusted_sid in trusted):
                if mask & read_mask:
                    raise WindowsHandleCustodyError("private_acl_broad_read_grant")
                if not require_private:
                    raise WindowsHandleCustodyError("ancestor_acl_replacement_grant")
                raise WindowsHandleCustodyError("private_acl_broad_write_grant")

    finally:
        for sid in known_sids:
            if sid.value:
                local_free(sid)
        if token:
            close_handle(token)
        if descriptor.value:
            local_free(descriptor)


def read_explicit_file(path: Path, *, max_bytes: int,
                       require_private_acl: bool = False) -> bytes:
    """Read one explicit regular file without following links or racing replacement."""
    if (type(max_bytes) is not int or max_bytes < 1
            or type(require_private_acl) is not bool):
        raise WindowsHandleCustodyError("explicit_file_limit_invalid")
    source = Path(path)
    if os.name == "nt":
        entries = read_regular_files(source.parent, max_entries=1,
            max_file_bytes=max_bytes, max_total_bytes=max_bytes,
            selected_names=(source.name,), require_private_acl=require_private_acl)
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
        if (not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes
                or before.st_nlink != 1
                or (require_private_acl and (before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) & 0o077))):
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


def verify_explicit_directory(path: Path, *, require_private_acl: bool = False) -> None:
    """Verify one configured Windows directory through held, reparse-safe handles."""
    if type(require_private_acl) is not bool:
        raise WindowsHandleCustodyError("explicit_directory_acl_flag_invalid")
    if os.name != "nt":
        raise WindowsHandleCustodyError("explicit_directory_windows_reader_on_non_windows")
    # An empty explicit selection opens and validates the directory chain but
    # reads no children and does not grant discovery over its contents.
    read_regular_files(Path(path), max_entries=1, max_file_bytes=1,
        max_total_bytes=1, selected_names=(), require_private_acl=require_private_acl)


@overload
def read_regular_files(root: Path, *, max_entries: int, max_file_bytes: int,
                       max_total_bytes: int, suffix: str = ".json",
                       selected_names: tuple[str, ...] | None = None,
                       require_private_acl: bool = False,
                       expected_root_identity: tuple[int, bytes] | None = None,
                       return_root_identity: Literal[False] = False
                       ) -> list[tuple[str, bytes]]: ...


@overload
def read_regular_files(root: Path, *, max_entries: int, max_file_bytes: int,
                       max_total_bytes: int, suffix: str = ".json",
                       selected_names: tuple[str, ...] | None = None,
                       require_private_acl: bool = False,
                       expected_root_identity: tuple[int, bytes] | None = None,
                       return_root_identity: Literal[True]
                       ) -> tuple[list[tuple[str, bytes]], tuple[int, bytes]]: ...


def read_regular_files(root: Path, *, max_entries: int, max_file_bytes: int,
                       max_total_bytes: int, suffix: str = ".json",
                       selected_names: tuple[str, ...] | None = None,
                       require_private_acl: bool = False,
                       expected_root_identity: tuple[int, bytes] | None = None,
                       return_root_identity: bool = False
                       ) -> list[tuple[str, bytes]] | tuple[list[tuple[str, bytes]], tuple[int, bytes]]:
    """Read bounded regular files through bound Windows handles.

    Win32 path opens are not used for descendants.  The configured root is
    walked component-by-component from the volume root with NtCreateFile,
    OBJ_DONT_REPARSE, and FILE_OPEN_REPARSE_POINT.  Children are then opened
    relative to the held directory handle.  Read-only sharing deliberately
    denies concurrent write/delete opens. All selected file handles remain held
    through terminal identity, metadata, and optional private-ACL checks; an
    earlier input cannot be replaced while a later input is read. Unsupported
    filesystems/APIs fail closed. This code is syntax-checked on non-Windows hosts, not runtime
    verified there.
    """
    invalid_names = selected_names is not None and (
        not isinstance(selected_names, tuple) or len(selected_names) > max_entries
        or any(not _safe_child_name(name) for name in selected_names)
        or (isinstance(selected_names, tuple)
            and len(selected_names) != len({name.casefold() for name in selected_names})))
    if (type(max_entries) is not int or max_entries < 1
            or type(max_file_bytes) is not int or max_file_bytes < 1
            or type(max_total_bytes) is not int or max_total_bytes < 1
            or not isinstance(suffix, str) or "/" in suffix or "\\" in suffix
            or type(require_private_acl) is not bool
            or type(return_root_identity) is not bool
            or (expected_root_identity is not None and not _valid_file_identity(expected_root_identity))
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

    kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    ntdll = getattr(ctypes, "WinDLL")("ntdll")
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

    def fail(code: str, cause: BaseException | None = None) -> NoReturn:
        error = WindowsHandleCustodyError(code)
        if cause is None:
            raise error
        raise error from cause

    def nt_open(parent: int | None, name: str, *, directory: bool) -> int:
        if not _safe_child_name(name):
            fail("windows_custody_child_name_invalid")
        backing = ctypes.create_unicode_buffer(name)
        byte_length = len(name.encode("utf-16-le"))
        unicode_name = UNICODE_STRING(byte_length, byte_length + 2, ctypes.cast(backing, wintypes.LPWSTR))
        attrs = OBJECT_ATTRIBUTES(ctypes.sizeof(OBJECT_ATTRIBUTES), wintypes.HANDLE(parent or 0),
            ctypes.pointer(unicode_name), OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE, None, None)
        handle = wintypes.HANDLE()
        iosb = IO_STATUS_BLOCK()
        access = FILE_READ_ATTRIBUTES | SYNCHRONIZE | (FILE_LIST_DIRECTORY if directory else 0x1)
        if require_private_acl:
            access |= 0x00020000  # READ_CONTROL for same-handle DACL inspection
        options = (FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE) | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT
        status = nt_create(ctypes.byref(handle), access, ctypes.byref(attrs), ctypes.byref(iosb), None,
            0, FILE_SHARE_READ, FILE_OPEN, options, None, 0)
        if (status & 0xFFFFFFFF) in {STATUS_OBJECT_NAME_NOT_FOUND, STATUS_OBJECT_PATH_NOT_FOUND}:
            fail("explicit_file_missing")
        raw_handle_value = handle.value
        if status < 0 or not raw_handle_value:
            fail("cognition_observation_windows_open_failed")
        return int(raw_handle_value)

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
        volume_access = FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | SYNCHRONIZE
        if require_private_acl:
            volume_access |= 0x00020000
        current_raw = create_file(volume_root, volume_access,
            FILE_SHARE_READ, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, None)
        if current_raw == INVALID_HANDLE_VALUE:
            fail("cognition_observation_windows_root_open_failed")
        current = int(current_raw); opened_handles.append(current)
        attrs, standard = attrs_and_standard(current)
        if not standard.Directory:
            fail("cognition_observation_windows_root_not_directory")
        for component in path.parts[1:]:
            if not _safe_child_name(component):
                fail("cognition_observation_windows_root_component_invalid")
            child = nt_open(current, component, directory=True)
            opened_handles.append(child)
            attrs, standard = attrs_and_standard(child)
            if not standard.Directory:
                fail("cognition_observation_windows_root_not_directory")
            current = child

        root_handle = current
        root_identity = file_id(root_handle)
        if expected_root_identity is not None and root_identity != expected_root_identity:
            fail("windows_custody_root_identity_mismatch")
        if require_private_acl:
            verify_private_handle_acl(root_handle)
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
        if (file_id(root_handle) != root_identity
                or (expected_root_identity is not None and root_identity != expected_root_identity)):
            fail("cognition_observation_windows_root_identity_changed")
        result: list[tuple[str, bytes]] = []
        total = 0
        seen_names: set[str] = set()
        retained_files: list[tuple[int, tuple[int, bytes], int]] = []
        for name, _directory_attrs in sorted(entries):
            if not _safe_child_name(name):
                fail("windows_custody_child_name_invalid")
            folded_name = name.casefold()
            if folded_name in seen_names:
                fail("windows_custody_child_name_ambiguous")
            seen_names.add(folded_name)
            handle = nt_open(root_handle, name, directory=False)
            # Keep every input's read-only sharing contract until the entire
            # bounded read is complete, including terminal metadata checks.
            opened_handles.append(handle)
            before_id = file_id(handle)
            if require_private_acl:
                verify_private_handle_acl(handle)
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
            retained_files.append((handle, before_id, size))
        if file_id(root_handle) != root_identity:
            fail("cognition_observation_windows_root_identity_changed")
        if require_private_acl:
            verify_private_handle_acl(root_handle)
        for retained, identity, size in retained_files:
            _, standard = attrs_and_standard(retained)
            if (standard.Directory or standard.NumberOfLinks != 1
                    or int(standard.EndOfFile) != size or file_id(retained) != identity):
                fail("cognition_observation_windows_file_changed")
            if require_private_acl:
                verify_private_handle_acl(retained)
        if return_root_identity:
            return result, root_identity
        return result
    except WindowsHandleCustodyError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        fail("cognition_observation_windows_recovery_failed", exc)
    finally:
        close_error: WindowsHandleCustodyError | None = None
        for handle in reversed(opened_handles):
            try:
                close(handle)
            except WindowsHandleCustodyError as exc:
                if close_error is None:
                    close_error = exc
        if close_error is not None:
            raise close_error


def _valid_file_identity(value: object) -> bool:
    return (isinstance(value, tuple) and len(value) == 2
            and type(value[0]) is int and 0 <= value[0] <= 2**64 - 1
            and type(value[1]) is bytes and len(value[1]) == 16)


def observe_private_directory_identity(root: Path) -> tuple[int, bytes]:
    """Return a reparse-safe identity for an existing private Windows directory."""
    result = read_regular_files(
        root, max_entries=1, max_file_bytes=1, max_total_bytes=1,
        selected_names=(), require_private_acl=True, return_root_identity=True,
    )
    if not isinstance(result, tuple) or len(result) != 2 or result[0]:
        raise WindowsHandleCustodyError("windows_custody_root_identity_unavailable")
    return result[1]

