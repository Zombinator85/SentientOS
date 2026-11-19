"""Handle-bound publication into an existing private Windows custody root.

Only fixed local drive roots are supported. Immutable artifacts use no-replace
publication; narrowly allowlisted mutable snapshots use atomic replacement after
the existing destination identity is rechecked. No directory is created, and
stale staging files are never adopted or removed. A successful result requires
file flush, destination readback, directory flush, and terminal custody checks.
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath
from typing import NoReturn

from sentientos.windows_handle_custody import (
    WindowsHandleCustodyError,
    _safe_child_name,
    _valid_file_identity,
    verify_private_handle_acl,
    verify_replay_ancestor_handle_acl,
)


class WindowsReplayCustodyError(ValueError):
    """Publication or durability could not be established under exact custody."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _publication_boundary(_phase: str) -> None:
    """Inert internal boundary used by native crash and race acceptance tests."""


def publish_immutable_replay_bytes(
    path: Path, data: bytes, *, max_bytes: int, max_entries: int,
    expected_root_identity: tuple[int, bytes] | None = None,
    filename_policy: str = "peer_event",
    replace_existing: bool = False,
) -> bool:
    """Return True for one new record or False for an exact durable retry.

    Errors after rename preserve the complete visible destination and issue no
    success acknowledgement. An interrupted pre-rename stage remains diagnostic
    only; a fresh retry never promotes it. The final root handle stays bound while
    every ancestor remains held against replacement. Atomic no-replace rename
    resolves canonical-name races without replacing an existing record. The two
    allowlisted mutable snapshot policies use ReplaceFileW only after the old
    file identity and bytes have been rechecked under the held private root.
    """
    if os.name != "nt":
        raise WindowsReplayCustodyError("windows_replay_publication_unsupported")
    if expected_root_identity is None:
        raise WindowsReplayCustodyError("windows_replay_root_identity_required")
    if not isinstance(path, Path):
        raise WindowsReplayCustodyError("windows_replay_publication_arguments_invalid")
    path = Path(os.fspath(path))
    sequence_match = (re.fullmatch(r"event-([0-9]{20})\.json", path.name)
        if filename_policy == "peer_event" else
        re.fullmatch(r"([0-9]{20})-self-reconciliation-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "longitudinal_self_model" else None)
    content_addressed_match = (re.fullmatch(r"devrec-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "developmental_record" else
        re.fullmatch(r"devreceipt-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "developmental_receipt" else None)
    mutable_state_match = ((filename_policy == "resident_cognition_state"
            and path.name == "composition_state.json")
        or (filename_policy == "runtime_admission_ledger"
            and path.name in {"admissions.json", "runtime_admissions.json"})
        or (filename_policy == "objective_request"
            and path.name == "pending_objective_intervention.json"))
    cognition_artifact_match = (re.fullmatch(r"devcog-[0-9a-f]{24}\.json", path.name)
        if filename_policy in {"cognition_observation", "epistemic_probe_capture"}
        else None)
    experiment_artifact_match = (
        re.fullmatch(r"devexp-protocol-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "developmental_experiment_protocol" else
        re.fullmatch(r"devexp-run-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "developmental_experiment_run" else None)
    ordinary_chat_experiment_artifact_match = (
        re.fullmatch(r"ordinary-history-protocol-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "ordinary_chat_history_protocol" else None)
    ordinary_chat_schedule_artifact_match = (
        re.fullmatch(r"ordinary-history-schedule-[0-9a-f]{24}-[0-9]{8}\.json", path.name)
        if filename_policy == "ordinary_chat_history_schedule" else None)
    ordinary_chat_execution_artifact_match = (
        re.fullmatch(r"ordinary-history-execution-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "ordinary_chat_history_execution_claim" else None)
    ordinary_chat_scoring_plan_artifact_match = (
        re.fullmatch(r"ordinary-history-score-plan-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "ordinary_chat_history_scoring_plan" else None)
    ordinary_chat_result_artifact_match = (
        re.fullmatch(r"ordinary-history-result-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "ordinary_chat_history_result" else None)
    ordinary_chat_score_artifact_match = (
        re.fullmatch(r"ordinary-history-score-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "ordinary_chat_history_score" else None)
    objective_artifact_match = (
        re.fullmatch(r"objective-task-plan-devexp-protocol-[0-9a-f]{24}\.json", path.name)
        if filename_policy == "objective_task_plan" else
        re.fullmatch(r"objective-score-devexp-protocol-[0-9a-f]{24}-(history_present|history_withheld|history_restored)\.json", path.name)
        if filename_policy == "objective_condition_score" else None)
    objective_archive_match = (re.fullmatch(r"[0-9a-f]{64}\.json", path.name)
        if filename_policy == "objective_request_archive" else None)
    epistemic_artifact_patterns = {
        "epistemic_propositions": r"proposition-[0-9a-f]{24}\.json",
        "epistemic_bindings": r"evidence-[0-9a-f]{24}\.json",
        "epistemic_states": r"[0-9]{12}-epistemic-state-[0-9a-f]{24}\.json",
        "epistemic_updates": r"[0-9]{12}-epistemic-update-[0-9a-f]{24}\.json",
        "epistemic_relations": r"[0-9a-f]{64}\.json",
        "epistemic_calibrations": r"epistemic-calibration-[0-9a-f]{24}\.json",
        "epistemic_transactions": r"[0-9a-f]{24}\.json",
        "epistemic_mutation_intent": r"[0-9a-f]{24}\.json",
        "epistemic_mutation_receipt": r"epistemic-mutation-receipt-[0-9a-f]{24}\.json",
        "resident_semantic_history_index": r"semantic-[0-9a-f]{64}\.json",
    }
    epistemic_artifact_match = (re.fullmatch(
        epistemic_artifact_patterns[filename_policy], path.name)
        if filename_policy in epistemic_artifact_patterns else None)
    sequence_number = (int(sequence_match.group(1)) if sequence_match is not None
        else 1 if (content_addressed_match is not None
            or mutable_state_match or cognition_artifact_match is not None
            or experiment_artifact_match is not None
            or ordinary_chat_experiment_artifact_match is not None
            or ordinary_chat_schedule_artifact_match is not None
            or ordinary_chat_execution_artifact_match is not None
            or ordinary_chat_scoring_plan_artifact_match is not None
            or ordinary_chat_result_artifact_match is not None
            or ordinary_chat_score_artifact_match is not None
            or objective_artifact_match is not None
            or objective_archive_match is not None
            or epistemic_artifact_match is not None) else 0)
    maximum_file_bytes = (16_777_216 if filename_policy in {
        "resident_cognition_state", "epistemic_probe_capture"}
        else 4_194_304 if filename_policy == "longitudinal_self_model"
        else 4_194_304 if filename_policy == "runtime_admission_ledger"
        else 4_194_304 if filename_policy in {
            "developmental_experiment_protocol", "developmental_experiment_run",
            "ordinary_chat_history_protocol", "ordinary_chat_history_result",
            "ordinary_chat_history_score", "ordinary_chat_history_scoring_plan",
            "ordinary_chat_history_schedule", "ordinary_chat_history_execution_claim"}
        else 4_194_304 if filename_policy in {
            "objective_task_plan", "objective_condition_score"}
        else 1_048_576 if filename_policy in {
            "objective_request", "objective_request_archive"}
        else 1_048_576)
    if (not path.is_absolute()
            or (sequence_match is None and content_addressed_match is None
                and cognition_artifact_match is None
                and experiment_artifact_match is None
                and ordinary_chat_experiment_artifact_match is None
                and ordinary_chat_schedule_artifact_match is None
                and ordinary_chat_execution_artifact_match is None
                and ordinary_chat_scoring_plan_artifact_match is None
                and ordinary_chat_result_artifact_match is None
                and ordinary_chat_score_artifact_match is None
                and objective_artifact_match is None
                and objective_archive_match is None
                and epistemic_artifact_match is None
                and not mutable_state_match)
            or type(replace_existing) is not bool
            or (replace_existing and not mutable_state_match)
            or not 1 <= sequence_number <= 2**63 - 1
            or type(data) is not bytes or not data
            or type(max_bytes) is not int or not 1 <= max_bytes <= maximum_file_bytes
            or len(data) > max_bytes
            or type(max_entries) is not int or not 1 <= max_entries <= 8192
            or (expected_root_identity is not None
                and not _valid_file_identity(expected_root_identity))):
        raise WindowsReplayCustodyError("windows_replay_publication_arguments_invalid")
    root = PureWindowsPath(os.path.abspath(path.parent))
    if (not root.is_absolute() or len(root.drive) != 2 or root.drive[1] != ":"
            or not root.drive[0].isascii() or not root.drive[0].isalpha()
            or any(not _safe_child_name(part) for part in root.parts[1:])):
        raise WindowsReplayCustodyError("windows_replay_root_form_unsupported")
    import ctypes
    import struct
    from ctypes import wintypes

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

    class FILE_RENAME_INFORMATION(ctypes.Structure):
        _fields_ = [("ReplaceIfExists", wintypes.BOOLEAN), ("RootDirectory", wintypes.HANDLE),
                    ("FileNameLength", wintypes.ULONG), ("FileName", wintypes.WCHAR * 1)]

    kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    native = getattr(ctypes, "WinDLL")("ntdll")
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    replace_file = kernel.ReplaceFileW
    replace_file.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    replace_file.restype = wintypes.BOOL
    drive_type = kernel.GetDriveTypeW
    drive_type.argtypes = [wintypes.LPCWSTR]
    drive_type.restype = wintypes.UINT
    final_name = kernel.GetFinalPathNameByHandleW
    final_name.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    final_name.restype = wintypes.DWORD
    info = kernel.GetFileInformationByHandleEx
    info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    info.restype = wintypes.BOOL
    flush = kernel.FlushFileBuffers
    flush.argtypes = [wintypes.HANDLE]
    flush.restype = wintypes.BOOL
    seek = kernel.SetFilePointerEx
    seek.argtypes = [wintypes.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD]
    seek.restype = wintypes.BOOL
    read = kernel.ReadFile
    write = kernel.WriteFile
    for operation in (read, write):
        operation.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        operation.restype = wintypes.BOOL
    nt_create = native.NtCreateFile
    nt_create.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
        ctypes.POINTER(OBJECT_ATTRIBUTES), ctypes.POINTER(IO_STATUS_BLOCK), ctypes.c_void_p,
        wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG]
    nt_create.restype = ctypes.c_long
    nt_query = native.NtQueryInformationFile
    nt_query.argtypes = [wintypes.HANDLE, ctypes.POINTER(IO_STATUS_BLOCK), ctypes.c_void_p,
                        wintypes.ULONG, ctypes.c_int]
    nt_query.restype = ctypes.c_long
    nt_set = native.NtSetInformationFile
    nt_set.argtypes = nt_query.argtypes
    nt_set.restype = ctypes.c_long
    nt_list = native.NtQueryDirectoryFile
    nt_list.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(IO_STATUS_BLOCK), ctypes.c_void_p, wintypes.ULONG, ctypes.c_int,
        wintypes.BOOLEAN, ctypes.POINTER(UNICODE_STRING), wintypes.BOOLEAN]
    nt_list.restype = ctypes.c_long
    opened: list[int] = []
    directories: list[int] = []
    staging: int | None = None
    staging_identity: tuple[int, bytes] | None = None
    previous_target: int | None = None
    previous_target_bytes: bytes | None = None
    committed = False

    def fail(code: str) -> NoReturn:
        raise WindowsReplayCustodyError(code)

    def close_opened(handle: int) -> None:
        if handle in opened:
            if not close(handle):
                fail("windows_replay_handle_close_failed")
            opened.remove(handle)

    def identity(handle: int) -> tuple[int, bytes]:
        value = FILE_ID_INFO()
        if not info(handle, 18, ctypes.byref(value), ctypes.sizeof(value)):
            fail("windows_replay_identity_unavailable")
        return int(value.VolumeSerialNumber), bytes(value.FileId)

    def metadata(handle: int) -> FILE_STANDARD_INFO:
        tag, standard, iosb = FILE_ATTRIBUTE_TAG_INFO(), FILE_STANDARD_INFO(), IO_STATUS_BLOCK()
        if (not info(handle, 9, ctypes.byref(tag), ctypes.sizeof(tag))
                or nt_query(handle, ctypes.byref(iosb), ctypes.byref(standard), ctypes.sizeof(standard), 5) < 0):
            fail("windows_replay_metadata_unavailable")
        if tag.FileAttributes & 0x400 or standard.DeletePending:
            fail("windows_replay_reparse_or_deleted")
        return standard

    def open_at(parent: int, name: str, *, directory: bool = False,
                writable: bool = False, exclusive_create: bool = False,
                delete_access: bool = False, sharing: int = 1) -> int:
        if not _safe_child_name(name):
            fail("windows_replay_child_name_invalid")
        backing = ctypes.create_unicode_buffer(name)
        length = len(name.encode("utf-16-le"))
        text = UNICODE_STRING(length, length + 2, ctypes.cast(backing, wintypes.LPWSTR))
        security_descriptor = None
        if exclusive_create:
            advapi = getattr(ctypes, "WinDLL")("advapi32", use_last_error=True)
            current_process = kernel.GetCurrentProcess
            current_process.restype = wintypes.HANDLE
            open_token = advapi.OpenProcessToken
            open_token.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
            open_token.restype = wintypes.BOOL
            get_token_information = advapi.GetTokenInformation
            get_token_information.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
            get_token_information.restype = wintypes.BOOL
            sid_to_string = advapi.ConvertSidToStringSidW
            sid_to_string.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
            sid_to_string.restype = wintypes.BOOL
            sddl_to_descriptor = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
            sddl_to_descriptor.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
            sddl_to_descriptor.restype = wintypes.BOOL
            local_free = kernel.LocalFree
            local_free.argtypes = [ctypes.c_void_p]
            local_free.restype = ctypes.c_void_p
            token, sid_text = wintypes.HANDLE(), wintypes.LPWSTR()
            try:
                needed = wintypes.DWORD()
                if not open_token(current_process(), 0x0008, ctypes.byref(token)):
                    fail("windows_replay_current_user_unavailable")
                get_token_information(token, 1, None, 0, ctypes.byref(needed))
                if not 0 < needed.value <= 65_536:
                    fail("windows_replay_current_user_unavailable")
                token_buffer = ctypes.create_string_buffer(needed.value)
                if not get_token_information(token, 1, token_buffer, needed.value, ctypes.byref(needed)):
                    fail("windows_replay_current_user_unavailable")
                sid = ctypes.cast(token_buffer, ctypes.POINTER(ctypes.c_void_p)).contents
                if not sid.value or not sid_to_string(sid, ctypes.byref(sid_text)) or not sid_text.value:
                    fail("windows_replay_current_user_unavailable")
                descriptor_text = (
                    f"O:{sid_text.value}D:P(A;;FA;;;{sid_text.value})"
                    "(A;;FA;;;SY)(A;;FA;;;BA)"
                )
                security_descriptor = ctypes.c_void_p()
                if not sddl_to_descriptor(descriptor_text, 1, ctypes.byref(security_descriptor), None):
                    security_descriptor = None
                    fail("windows_replay_private_acl_creation_unavailable")
            finally:
                if sid_text:
                    local_free(sid_text)
                if token:
                    close(token)
        attributes = OBJECT_ATTRIBUTES(ctypes.sizeof(OBJECT_ATTRIBUTES), parent,
            ctypes.pointer(text), 0x40 | 0x1000, security_descriptor, None)
        handle, iosb = wintypes.HANDLE(), IO_STATUS_BLOCK()
        access = 0x1 | 0x80 | 0x20000 | 0x100000
        if writable:
            access |= 0x2 | (0x10000 if exclusive_create else 0)
        if delete_access:
            access |= 0x10000
        if directory and writable:
            access = 0xC0100000
        options = (0x1 if directory else 0x40) | 0x20 | 0x00200000
        if exclusive_create:
            options |= 0x2  # FILE_WRITE_THROUGH
        try:
            status = nt_create(ctypes.byref(handle), access, ctypes.byref(attributes), ctypes.byref(iosb),
                None, 0x80 if exclusive_create else 0,
                5 if exclusive_create and not replace_existing else sharing,
                2 if exclusive_create else 1,
                options, None, 0)
        finally:
            if security_descriptor:
                local_free(security_descriptor)
        if status < 0 or not handle.value:
            fail("windows_replay_open_unavailable")
        value = int(handle.value)
        opened.append(value)
        return value

    def validate_directories() -> None:
        for index, handle in enumerate(directories):
            if not metadata(handle).Directory:
                fail("windows_replay_directory_invalid")
            if index == len(directories) - 1:
                verify_private_handle_acl(handle)
            else:
                verify_replay_ancestor_handle_acl(handle)

    def names_at(handle: int) -> tuple[str, ...]:
        names: list[str] = []
        buffer = ctypes.create_string_buffer(65_536)
        restart = True
        while True:
            iosb = IO_STATUS_BLOCK()
            status = nt_list(handle, None, None, None, ctypes.byref(iosb), buffer, len(buffer),
                             1, False, None, restart)
            restart = False
            if status & 0xFFFFFFFF == 0x80000006:
                break
            if status < 0 or not 0 < iosb.Information <= len(buffer):
                fail("windows_replay_listing_unavailable")
            offset = 0
            while offset < iosb.Information:
                if iosb.Information - offset < 64:
                    fail("windows_replay_listing_invalid")
                next_offset = struct.unpack_from("<I", buffer.raw, offset)[0]
                length = struct.unpack_from("<I", buffer.raw, offset + 60)[0]
                if length % 2 or length > 510 or offset + 64 + length > iosb.Information:
                    fail("windows_replay_listing_invalid")
                name = buffer.raw[offset + 64:offset + 64 + length].decode("utf-16-le")
                if name not in {".", ".."}:
                    if not _safe_child_name(name):
                        fail("windows_replay_listing_invalid")
                    names.append(name)
                    if len(names) > max_entries:
                        fail("windows_replay_directory_bound_exceeded")
                if next_offset == 0:
                    break
                if next_offset < 64 or offset + next_offset > iosb.Information:
                    fail("windows_replay_listing_invalid")
                offset += next_offset
        if len({name.casefold() for name in names}) != len(names):
            fail("windows_replay_listing_ambiguous")
        return tuple(names)

    def read_back(handle: int) -> bytes:
        before, file_id = metadata(handle), identity(handle)
        verify_private_handle_acl(handle)
        if before.Directory or before.NumberOfLinks != 1 or not 0 <= before.EndOfFile <= max_bytes:
            fail("windows_replay_file_unbounded_or_aliased")
        if not seek(handle, 0, None, 0):
            fail("windows_replay_seek_unavailable")
        result = bytearray()
        while len(result) <= max_bytes:
            amount = min(65_536, max_bytes + 1 - len(result))
            if not amount:
                break
            buffer, count = ctypes.create_string_buffer(amount), wintypes.DWORD()
            if not read(handle, buffer, amount, ctypes.byref(count), None):
                fail("windows_replay_readback_unavailable")
            if not count.value:
                break
            result.extend(buffer.raw[:count.value])
        after = metadata(handle)
        if (len(result) != before.EndOfFile or after.EndOfFile != before.EndOfFile
                or after.NumberOfLinks != 1 or identity(handle) != file_id):
            fail("windows_replay_readback_changed")
        verify_private_handle_acl(handle)
        return bytes(result)

    def durable_existing(root_handle: int) -> bool:
        if path.name not in names_at(root_handle):
            fail("windows_replay_target_name_noncanonical")
        existing = open_at(root_handle, path.name, writable=True)
        if read_back(existing) != data:
            fail("replay_owner_record_conflict")
        validate_directories()
        if not flush(existing) or not flush(root_handle):
            fail("windows_replay_retry_durability_unverified")
        if read_back(existing) != data:
            fail("windows_replay_readback_changed")
        validate_directories()
        return False

    try:
        volume = root.drive + "\\"
        if drive_type(volume) != 3:
            fail("windows_replay_fixed_local_drive_required")
        raw = create(volume, 0x80100000, 1, None, 3, 0x02200000, None)
        if raw == ctypes.c_void_p(-1).value or not raw:
            fail("windows_replay_volume_unavailable")
        current = int(raw)
        opened.append(current)
        directories.append(current)
        name_buffer = ctypes.create_unicode_buffer(512)
        length = final_name(current, name_buffer, len(name_buffer), 0)
        if not 0 < length < len(name_buffer) or name_buffer.value.casefold() != ("\\\\?\\" + volume).casefold():
            fail("windows_replay_volume_alias_unsupported")
        for index, component in enumerate(root.parts[1:]):
            if not metadata(current).Directory:
                fail("windows_replay_directory_invalid")
            verify_replay_ancestor_handle_acl(current)
            last = index == len(root.parts[1:]) - 1
            current = open_at(current, component, directory=True, writable=last,
                sharing=7 if last else 1)
            directories.append(current)
        root_handle = current
        root_identity = identity(root_handle)
        if expected_root_identity is not None and root_identity != expected_root_identity:
            fail("windows_replay_root_identity_mismatch")
        validate_directories()
        names = names_at(root_handle)
        target_present = any(name.casefold() == path.name.casefold() for name in names)
        if target_present and not replace_existing:
            return durable_existing(root_handle)
        if not target_present and len(names) >= max_entries:
            fail("windows_replay_directory_bound_exceeded")
        if target_present and replace_existing:
            previous_target = open_at(root_handle, path.name, writable=True,
                delete_access=True, sharing=7)
            previous_target_bytes = read_back(previous_target)
            if previous_target_bytes == data:
                validate_directories()
                if not flush(previous_target) or not flush(root_handle):
                    fail("windows_replay_retry_durability_unverified")
                return False
        temporary_name = ".pending-" + os.urandom(16).hex()
        staging = open_at(root_handle, temporary_name, writable=True,
            exclusive_create=True, sharing=7 if replace_existing else 1)
        staging_identity = identity(staging)
        if metadata(staging).Directory or metadata(staging).NumberOfLinks != 1:
            fail("windows_replay_staging_invalid")
        verify_private_handle_acl(staging)
        offset = 0
        while offset < len(data):
            chunk = ctypes.create_string_buffer(data[offset:offset + 65_536])
            count = wintypes.DWORD()
            if not write(staging, chunk, min(65_536, len(data) - offset), ctypes.byref(count), None) or not count.value:
                fail("windows_replay_short_write")
            offset += int(count.value)
        if not flush(staging) or read_back(staging) != data:
            fail("windows_replay_staging_durability_unverified")
        _publication_boundary("prepared")
        validate_directories()
        current_names = names_at(root_handle)
        current_target_present = any(
            name.casefold() == path.name.casefold() for name in current_names)
        if current_target_present != (previous_target is not None):
            fail("windows_replay_mutable_destination_raced")
        if previous_target is not None:
            checked_target = open_at(root_handle, path.name, writable=True,
                delete_access=True, sharing=7)
            if (identity(previous_target) != identity(checked_target)
                    or read_back(previous_target) != previous_target_bytes):
                fail("windows_replay_mutable_destination_raced")
            close_opened(checked_target)
        if identity(root_handle) != root_identity or identity(staging) != staging_identity or read_back(staging) != data:
            fail("windows_replay_precommit_changed")
        encoded = path.name.encode("utf-16-le")
        if replace_existing and previous_target is not None:
            current_target = open_at(root_handle, path.name, writable=True,
                delete_access=True, sharing=7)
            if (identity(root_handle) != root_identity
                    or identity(previous_target) != identity(current_target)
                    or read_back(previous_target) != previous_target_bytes):
                fail("windows_replay_mutable_destination_raced")
            source_identity = staging_identity
            close_opened(current_target)
            close_opened(previous_target)
            previous_target = None
            close_opened(staging)
            staging = None
            staging_path = str(path.parent / temporary_name)
            if not replace_file(str(path), staging_path, None, 0x1, None, None):
                fail(f"windows_replay_atomic_replace_failed_0x{getattr(ctypes, 'get_last_error')():08x}")
            staging = open_at(root_handle, path.name, writable=True, sharing=7)
            if identity(staging) != source_identity:
                fail("windows_replay_destination_identity_mismatch")
            committed = True
            _publication_boundary("committed")
        else:
            name_offset = FILE_RENAME_INFORMATION.FileName.offset
            rename_buffer = ctypes.create_string_buffer(name_offset + len(encoded))
            rename = ctypes.cast(rename_buffer,
                ctypes.POINTER(FILE_RENAME_INFORMATION)).contents
            rename.ReplaceIfExists, rename.RootDirectory, rename.FileNameLength = (
                False, root_handle, len(encoded))
            ctypes.memmove(ctypes.addressof(rename_buffer) + name_offset, encoded, len(encoded))
            iosb = IO_STATUS_BLOCK()
            status = nt_set(staging, ctypes.byref(iosb), rename_buffer,
                len(rename_buffer), 10)
            if status & 0xFFFFFFFF == 0xC0000035:
                if replace_existing:
                    fail("windows_replay_mutable_destination_raced")
                return durable_existing(root_handle)
            if status < 0:
                fail(f"windows_replay_no_replace_rename_failed_0x{status & 0xFFFFFFFF:08x}")
            committed = True
            _publication_boundary("committed")
        names_at(root_handle)
        installed = open_at(root_handle, path.name, sharing=7)
        if identity(installed) != staging_identity or read_back(installed) != data:
            fail("windows_replay_destination_identity_mismatch")
        if not flush(staging):
            fail("windows_replay_file_flush_failed")
        _publication_boundary("before_directory_flush")
        validate_directories()
        if not flush(root_handle):
            fail("windows_replay_directory_flush_failed")
        if (identity(root_handle) != root_identity or identity(installed) != staging_identity
                or read_back(installed) != data):
            fail("windows_replay_terminal_changed")
        validate_directories()
        return True
    except WindowsReplayCustodyError:
        raise
    except WindowsHandleCustodyError as exc:
        raise WindowsReplayCustodyError(exc.code) from exc
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise WindowsReplayCustodyError("windows_replay_publication_unavailable") from exc
    finally:
        cleanup_error: WindowsReplayCustodyError | None = None
        if staging is not None and not committed:
            try:
                if identity(staging) == staging_identity and metadata(staging).NumberOfLinks == 1:
                    delete, iosb = wintypes.BOOLEAN(True), IO_STATUS_BLOCK()
                    if nt_set(staging, ctypes.byref(iosb), ctypes.byref(delete), ctypes.sizeof(delete), 13) < 0:
                        fail("windows_replay_staging_cleanup_failed")
            except WindowsReplayCustodyError as exc:
                cleanup_error = exc
        for handle in reversed(opened):
            if not close(handle) and cleanup_error is None:
                cleanup_error = WindowsReplayCustodyError("windows_replay_handle_close_failed")
        if cleanup_error is not None:
            raise cleanup_error
