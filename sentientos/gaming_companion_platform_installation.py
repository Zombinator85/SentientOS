"""Load a signed companion platform catalog and build its read-only owners.

The catalog contains opaque references and relative asset locations only. The
signing key must already be pinned outside the catalog by the installation
authority. This loader verifies the catalog before constructing custody or
receipt-store adapters; it does not provision identities or issue receipts.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .gaming_companion_authority import (
    CompanionAuthorityCallbacks,
    CompanionAuthorityReceiptStore,
    SignedCompanionAuthorityVerifier,
    canonical_receipt_bytes,
)
from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_platform_custody import (
    CompanionCustodyReference,
    CompanionPlatformCustodyResolver,
)
from .gaming_companion_tls_transport import (
    read_posix_bridge_source_key,
    read_windows_dpapi_bridge_source_key,
)

CATALOG_SCHEMA = "sentientos.companion_platform_custody_catalog:v1"
CATALOG_FIELDS = frozenset({
    "schema_version", "installation_id", "custody_root",
    "receipt_store_root", "custody_references",
})
CATALOG_ENTRY_FIELDS = frozenset({
    "kind", "relative_path", "protection", "passphrase_reference",
})
MAX_CATALOG_BYTES = 256 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,511}\Z")


class CompanionPlatformInstallationCatalogError(CompanionBridgeError):
    """Invalid, untrusted, or unavailable installation catalog."""


@dataclass(frozen=True, slots=True)
class CompanionPlatformInstallation:
    installation_id: str
    catalog_digest: str
    custody: CompanionPlatformCustodyResolver
    authority: CompanionAuthorityCallbacks


def load_companion_platform_installation(*, installation_root: Path | str,
        catalog_relative_path: str,
        catalog_receipt: Mapping[str, Any],
        trusted_issuer_public_keys: Mapping[str, bytes],
        system_name: str | None = None,
        is_wsl2: bool | None = None) -> CompanionPlatformInstallation:
    """Verify a detached platform-catalog receipt before opening target assets.

    Public issuer keys are injected by a separately trusted installation
    authority. No key or receipt is accepted from the catalog itself.
    """
    root = Path(installation_root)
    if root.is_symlink() or not root.is_dir():
        raise CompanionPlatformInstallationCatalogError("companion_installation_root_invalid")
    try:
        root = root.resolve(strict=True)
        catalog_path = _resolve_relative(root, catalog_relative_path)
        catalog = _read_catalog(catalog_path, system_name=system_name)
    except CompanionPlatformInstallationCatalogError:
        raise
    except (OSError, ValueError) as exc:
        raise CompanionPlatformInstallationCatalogError("companion_installation_catalog_unavailable") from exc
    value = _validate_catalog(catalog)
    digest = "sha256:" + hashlib.sha256(canonical_receipt_bytes(value)).hexdigest()
    installation_id = str(value["installation_id"])
    verifier = SignedCompanionAuthorityVerifier(trusted_issuer_public_keys)
    try:
        verifier.verify(catalog_receipt, receipt_type="platform_catalog",
            expected_subject={"action": "install_platform_catalog",
                "installation_id": installation_id, "catalog_digest": digest})
    except CompanionBridgeError as exc:
        raise CompanionPlatformInstallationCatalogError(
            "companion_installation_catalog_authority_invalid") from exc
    custody_root = _resolve_relative(root, str(value["custody_root"]))
    receipt_root = _resolve_relative(root, str(value["receipt_store_root"]))
    references = {
        reference: CompanionCustodyReference(**entry)
        for reference, entry in value["custody_references"].items()
    }
    resolver = CompanionPlatformCustodyResolver(root=custody_root,
        references=references, system_name=system_name, is_wsl2=is_wsl2,
        posix_key_reader=read_posix_bridge_source_key,
        windows_key_reader=read_windows_dpapi_bridge_source_key)
    receipt_store = CompanionAuthorityReceiptStore(receipt_root)
    return CompanionPlatformInstallation(installation_id, digest, resolver,
        CompanionAuthorityCallbacks(verifier=verifier, store=receipt_store))


def _validate_catalog(value: object) -> dict[str, Any]:
    if (not isinstance(value, Mapping) or set(value) != CATALOG_FIELDS
            or value.get("schema_version") != CATALOG_SCHEMA):
        raise CompanionPlatformInstallationCatalogError("companion_installation_catalog_shape_invalid")
    installation_id = value.get("installation_id")
    if not isinstance(installation_id, str) or _IDENTIFIER.fullmatch(installation_id) is None:
        raise CompanionPlatformInstallationCatalogError("companion_installation_id_invalid")
    for field in ("custody_root", "receipt_store_root"):
        entry = value.get(field)
        if not isinstance(entry, str) or not entry or len(entry) > 1024:
            raise CompanionPlatformInstallationCatalogError("companion_installation_root_reference_invalid")
        _validate_relative(entry)
    references = value.get("custody_references")
    if not isinstance(references, Mapping) or not references:
        raise CompanionPlatformInstallationCatalogError("companion_installation_references_required")
    normalized: dict[str, dict[str, Any]] = {}
    for reference, entry in references.items():
        if (not isinstance(reference, str) or _REFERENCE.fullmatch(reference) is None
                or not isinstance(entry, Mapping) or set(entry) != CATALOG_ENTRY_FIELDS):
            raise CompanionPlatformInstallationCatalogError("companion_installation_reference_shape_invalid")
        relative_path = entry.get("relative_path")
        if not isinstance(relative_path, str) or not relative_path:
            raise CompanionPlatformInstallationCatalogError("companion_installation_asset_path_invalid")
        _validate_relative(relative_path)
        for field in ("kind", "protection"):
            if not isinstance(entry.get(field), str):
                raise CompanionPlatformInstallationCatalogError("companion_installation_reference_shape_invalid")
        passphrase = entry.get("passphrase_reference")
        if passphrase is not None and (not isinstance(passphrase, str)
                or _REFERENCE.fullmatch(passphrase) is None):
            raise CompanionPlatformInstallationCatalogError("companion_installation_reference_shape_invalid")
        normalized[reference] = dict(entry)
    return {"schema_version": CATALOG_SCHEMA, "installation_id": installation_id,
        "custody_root": value["custody_root"], "receipt_store_root": value["receipt_store_root"],
        "custody_references": normalized}


def _validate_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (path.is_absolute() or "\\" in value or "\x00" in value
            or any(part in {"", ".", ".."} or ":" in part for part in value.split("/"))):
        raise CompanionPlatformInstallationCatalogError("companion_installation_relative_path_invalid")
    return path


def _resolve_relative(root: Path, relative: str) -> Path:
    path = _validate_relative(relative)
    candidate = root.joinpath(*path.parts)
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise CompanionPlatformInstallationCatalogError("companion_installation_symlink_forbidden")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise CompanionPlatformInstallationCatalogError("companion_installation_path_outside_root") from exc
    return resolved


def _read_catalog(path: Path, *, system_name: str | None) -> dict[str, Any]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0))
    except OSError as exc:
        raise CompanionPlatformInstallationCatalogError("companion_installation_catalog_unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_size <= 0
                or info.st_size > MAX_CATALOG_BYTES):
            raise CompanionPlatformInstallationCatalogError("companion_installation_catalog_size_invalid")
        if (system_name or platform.system()) == "Linux":
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise CompanionPlatformInstallationCatalogError("companion_installation_catalog_custody_invalid")
        data = bytearray()
        while len(data) <= MAX_CATALOG_BYTES:
            block = os.read(descriptor, min(8192, MAX_CATALOG_BYTES + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > MAX_CATALOG_BYTES:
            raise CompanionPlatformInstallationCatalogError("companion_installation_catalog_size_invalid")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CompanionPlatformInstallationCatalogError("companion_installation_catalog_invalid_json") from exc
    if not isinstance(value, dict):
        raise CompanionPlatformInstallationCatalogError("companion_installation_catalog_shape_invalid")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_field")
        result[key] = value
    return result


__all__ = ["CATALOG_SCHEMA", "CompanionPlatformInstallation",
    "CompanionPlatformInstallationCatalogError", "load_companion_platform_installation"]
