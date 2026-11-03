"""Resolve split-host companion references through bounded OS custody readers.

The provider receives a target-installed reference catalog. Manifest values
remain opaque identifiers; they cannot choose arbitrary filesystem paths. This
module has no provisioning or authority-issuance operations.
"""
from __future__ import annotations

import json
import os
import platform
import re
import ssl
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
    MIN_TLS_VERSION,
    read_posix_bridge_source_key,
    read_windows_dpapi_bridge_source_key,
)

_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,511}\Z")
_KINDS = frozenset({"bridge_key", "secret", "generation_record", "ca_bundle",
                    "certificate", "private_key"})
_PROTECTIONS = frozenset({"posix_private_file", "windows_dpapi", "private_record",
                          "public_file", "encrypted_pem"})
_MAX_FILE_BYTES = 1024 * 1024
_MAX_RECORD_BYTES = 16 * 1024
_MAX_PASSPHRASE_BYTES = 128
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class CompanionCustodyReferenceError(CompanionBridgeError):
    """An opaque custody reference or platform-bound asset is invalid."""


@dataclass(frozen=True, slots=True)
class CompanionCustodyReference:
    kind: str
    relative_path: str
    protection: str
    passphrase_reference: str | None = None


class CompanionPlatformCustodyResolver:
    """Resolve manifest refs only through an installed, root-bounded catalog.

    The catalog is passed by the platform provider, which must load it from
    installation-controlled configuration. It cannot turn a manifest string
    into a new path. On WSL, secret and generation files are checked for owner
    and mode. Windows bridge secrets use DPAPI CurrentUser. TLS private keys
    must be encrypted PEMs with a separately custodied passphrase.
    """

    def __init__(self, *, root: Path | str,
                 references: Mapping[str, CompanionCustodyReference],
                 system_name: str | None = None,
                 is_wsl2: bool | None = None,
                 posix_key_reader: Callable[[Path], bytes] = read_posix_bridge_source_key,
                 windows_key_reader: Callable[[Path], bytes] = read_windows_dpapi_bridge_source_key) -> None:
        self._system = system_name or platform.system()
        if self._system not in {"Windows", "Linux"}:
            raise CompanionCustodyReferenceError("companion_custody_unsupported_platform")
        self._is_wsl2 = _detect_wsl2() if is_wsl2 is None else is_wsl2
        if self._system == "Linux" and self._is_wsl2 is not True:
            raise CompanionCustodyReferenceError("companion_custody_wsl2_required")
        if self._system == "Windows" and is_wsl2 is True:
            raise CompanionCustodyReferenceError("companion_custody_platform_mismatch")
        if not isinstance(references, Mapping) or not references:
            raise CompanionCustodyReferenceError("companion_custody_reference_catalog_required")
        self._root = Path(root)
        if self._is_reparse(self._root) or not self._root.is_dir():
            raise CompanionCustodyReferenceError("companion_custody_root_invalid")
        try:
            self._root = self._root.resolve(strict=True)
        except OSError as exc:
            raise CompanionCustodyReferenceError("companion_custody_root_invalid") from exc
        if self._system == "Linux" and _is_windows_mount(self._root):
            raise CompanionCustodyReferenceError("companion_custody_wsl_native_root_required")
        if any(not _catalog_entry_valid(ref, entry)
               for ref, entry in references.items()):
            raise CompanionCustodyReferenceError("companion_custody_reference_catalog_invalid")
        self._references = dict(references)
        self._posix_key_reader = posix_key_reader
        self._windows_key_reader = windows_key_reader

    def read_bridge_key(self, reference: str) -> bytes:
        entry, path = self._resolve(reference, "bridge_key")
        if self._system == "Windows":
            if entry.protection != "windows_dpapi":
                raise CompanionCustodyReferenceError("companion_custody_windows_dpapi_required")
            self._validate_file(path, secret=False, maximum=4096)
            key = self._windows_key_reader(path)
        else:
            if entry.protection != "posix_private_file":
                raise CompanionCustodyReferenceError("companion_custody_posix_secret_required")
            key = self._posix_key_reader(path)
        if not isinstance(key, bytes) or not 32 <= len(key) <= 128:
            raise CompanionCustodyReferenceError("companion_custody_bridge_key_invalid")
        return key

    def read_secret(self, reference: str) -> bytes:
        """Resolve a separately protected secret such as an encrypted PEM password."""
        entry, path = self._resolve(reference, "secret")
        if self._system == "Windows":
            if entry.protection != "windows_dpapi":
                raise CompanionCustodyReferenceError("companion_custody_windows_dpapi_required")
            self._validate_file(path, secret=False, maximum=4096)
            value = self._windows_key_reader(path)
        else:
            if entry.protection != "posix_private_file":
                raise CompanionCustodyReferenceError("companion_custody_posix_secret_required")
            value = self._posix_key_reader(path)
        if not isinstance(value, bytes) or not 32 <= len(value) <= _MAX_PASSPHRASE_BYTES:
            raise CompanionCustodyReferenceError("companion_custody_secret_invalid")
        return value

    def load_generation_pair(self, source_reference: str,
                             acknowledgment_reference: str) -> BridgeGenerationPair:
        source = self._load_generation(source_reference)
        acknowledgment = self._load_generation(acknowledgment_reference)
        return BridgeGenerationPair(source, acknowledgment)

    def server_tls_context(self, ca_reference: str, certificate_reference: str,
                           private_key_reference: str) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = MIN_TLS_VERSION
        context.verify_mode = ssl.CERT_REQUIRED
        self._configure_tls(context, ca_reference, certificate_reference, private_key_reference)
        return context

    def client_tls_context(self, ca_reference: str, certificate_reference: str,
                           private_key_reference: str) -> ssl.SSLContext:
        ca_entry, ca_path = self._resolve(ca_reference, "ca_bundle")
        ca_bytes = self._read_public_file(ca_entry, ca_path)
        try:
            ca_data = ca_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise CompanionCustodyReferenceError("companion_custody_ca_bundle_invalid") from exc
        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cadata=ca_data)
        except ssl.SSLError as exc:
            raise CompanionCustodyReferenceError("companion_custody_ca_bundle_invalid") from exc
        context.minimum_version = MIN_TLS_VERSION
        context.check_hostname = True
        self._configure_client_identity(context, certificate_reference, private_key_reference)
        return context

    def _configure_tls(self, context: ssl.SSLContext, ca_reference: str,
                       certificate_reference: str, private_key_reference: str) -> None:
        ca_entry, ca_path = self._resolve(ca_reference, "ca_bundle")
        ca_bytes = self._read_public_file(ca_entry, ca_path)
        try:
            context.load_verify_locations(cadata=ca_bytes.decode("ascii"))
        except (UnicodeDecodeError, ssl.SSLError) as exc:
            raise CompanionCustodyReferenceError("companion_custody_ca_bundle_invalid") from exc
        self._configure_client_identity(context, certificate_reference, private_key_reference)

    def _configure_client_identity(self, context: ssl.SSLContext,
                                   certificate_reference: str,
                                   private_key_reference: str) -> None:
        cert_entry, cert_path = self._resolve(certificate_reference, "certificate")
        key_entry, key_path = self._resolve(private_key_reference, "private_key")
        self._read_public_file(cert_entry, cert_path)
        key_bytes = self._read_public_file(key_entry, key_path)
        if b"-----BEGIN ENCRYPTED PRIVATE KEY-----" not in key_bytes:
            raise CompanionCustodyReferenceError("companion_custody_encrypted_pem_required")
        password: bytes | None = None
        if key_entry.protection != "encrypted_pem" or not key_entry.passphrase_reference:
            raise CompanionCustodyReferenceError("companion_custody_tls_key_passphrase_required")
        password = self.read_secret(key_entry.passphrase_reference)
        try:
            context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path), password=password)
        except (OSError, ssl.SSLError, ValueError) as exc:
            raise CompanionCustodyReferenceError("companion_custody_tls_identity_invalid") from exc

    def _load_generation(self, reference: str) -> BridgeGenerationCustodyRecord:
        entry, path = self._resolve(reference, "generation_record")
        contents = self._read_bounded(path, maximum=16_384, secret=True)
        try:
            value = json.loads(contents.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CompanionCustodyReferenceError("companion_custody_generation_record_invalid") from exc
        if not isinstance(value, Mapping):
            raise CompanionCustodyReferenceError("companion_custody_generation_record_invalid")
        if self._system == "Linux" and entry.protection != "private_record":
            raise CompanionCustodyReferenceError("companion_custody_generation_record_protection_invalid")
        return BridgeGenerationCustodyRecord.from_mapping(value)

    def _resolve(self, reference: str, expected_kind: str) -> tuple[CompanionCustodyReference, Path]:
        if not isinstance(reference, str) or _REFERENCE.fullmatch(reference) is None:
            raise CompanionCustodyReferenceError("companion_custody_reference_invalid")
        entry = self._references.get(reference)
        if entry is None or entry.kind != expected_kind:
            raise CompanionCustodyReferenceError("companion_custody_reference_unresolved")
        path_parts = entry.relative_path.split("/")
        relative = PurePosixPath(entry.relative_path)
        if (not entry.relative_path or "\x00" in entry.relative_path
                or "\\" in entry.relative_path or relative.is_absolute()
                or any(part in {"", ".", ".."} or ":" in part for part in path_parts)):
            raise CompanionCustodyReferenceError("companion_custody_relative_path_invalid")
        candidate = self._root.joinpath(*relative.parts)
        current = self._root
        for part in relative.parts:
            current = current / part
            if self._is_reparse(current):
                raise CompanionCustodyReferenceError("companion_custody_reparse_path_forbidden")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self._root)
        except (OSError, ValueError) as exc:
            raise CompanionCustodyReferenceError("companion_custody_path_outside_root") from exc
        if not resolved.is_file():
            raise CompanionCustodyReferenceError("companion_custody_file_required")
        return entry, resolved

    def _read_public_file(self, entry: CompanionCustodyReference, path: Path) -> bytes:
        expected_protection = "encrypted_pem" if entry.kind == "private_key" else "public_file"
        if entry.protection != expected_protection:
            raise CompanionCustodyReferenceError("companion_custody_public_file_protection_invalid")
        return self._read_bounded(path, maximum=_MAX_FILE_BYTES,
                                  secret=entry.kind == "private_key")

    def _validate_file(self, path: Path, *, secret: bool, maximum: int) -> None:
        self._read_bounded(path, maximum=maximum, secret=secret)

    def _read_bounded(self, path: Path, *, maximum: int, secret: bool) -> bytes:
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                                 | getattr(os, "O_NONBLOCK", 0))
        except OSError as exc:
            raise CompanionCustodyReferenceError("companion_custody_file_unavailable") from exc
        try:
            info = os.fstat(descriptor)
            if self._system == "Linux":
                invalid_owner = (info.st_uid != os.getuid() if secret
                                 else info.st_uid not in {0, os.getuid()})
                invalid_mode = bool(info.st_mode & (0o077 if secret else 0o022))
            else:
                invalid_owner = invalid_mode = False
            if (not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > maximum
                    or (self._system == "Linux" and (invalid_owner or invalid_mode))):
                raise CompanionCustodyReferenceError("companion_custody_file_permissions_invalid")
            result = bytearray()
            while len(result) <= maximum:
                block = os.read(descriptor, min(4096, maximum + 1 - len(result)))
                if not block:
                    break
                result.extend(block)
            if len(result) > maximum:
                raise CompanionCustodyReferenceError("companion_custody_file_too_large")
            return bytes(result)
        finally:
            os.close(descriptor)

    @staticmethod
    def _is_reparse(path: Path) -> bool:
        try:
            metadata = path.lstat()
        except OSError:
            return False
        return (stat.S_ISLNK(metadata.st_mode)
                or bool(getattr(metadata, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT))


def _detect_wsl2() -> bool:
    marker = os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP")
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
    except OSError:
        release = ""
    return os.name == "posix" and bool(marker or "microsoft" in release)


def _is_windows_mount(path: Path) -> bool:
    return path == Path("/mnt") or Path("/mnt") in path.parents


def _catalog_entry_valid(reference: object, entry: object) -> bool:
    if (not isinstance(reference, str) or _REFERENCE.fullmatch(reference) is None
            or type(entry) is not CompanionCustodyReference
            or not isinstance(entry.kind, str) or not isinstance(entry.protection, str)
            or entry.kind not in _KINDS or entry.protection not in _PROTECTIONS
            or not isinstance(entry.relative_path, str) or not entry.relative_path):
        return False
    if entry.kind in {"bridge_key", "secret"}:
        return entry.protection in {"posix_private_file", "windows_dpapi"}
    if entry.kind == "generation_record":
        return entry.protection == "private_record"
    if entry.kind in {"ca_bundle", "certificate"}:
        return entry.protection == "public_file" and entry.passphrase_reference is None
    if entry.kind == "private_key":
        return (entry.protection == "encrypted_pem"
                and isinstance(entry.passphrase_reference, str)
                and _REFERENCE.fullmatch(entry.passphrase_reference) is not None)
    return False


__all__ = ["CompanionCustodyReference", "CompanionCustodyReferenceError",
           "CompanionPlatformCustodyResolver"]
