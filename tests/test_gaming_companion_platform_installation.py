from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentientos.gaming_companion_authority import RECEIPT_SCHEMA, canonical_receipt_bytes
from sentientos.gaming_companion_platform_installation import (
    CATALOG_SCHEMA,
    CompanionPlatformInstallationCatalogError,
    load_companion_platform_installation,
)

pytestmark = pytest.mark.no_legacy_skip


def _fixture(tmp_path: Path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    root = tmp_path / "installation"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    custody = root / "custody"
    key_dir = custody / "keys"
    key_dir.mkdir(parents=True, mode=0o700)
    os.chmod(custody, 0o700)
    os.chmod(key_dir, 0o700)
    key_path = key_dir / "edge-source.bin"
    key_path.write_bytes(b"e" * 32)
    os.chmod(key_path, 0o600)
    receipts = root / "receipts"
    receipts.mkdir(mode=0o700)
    os.chmod(receipts, 0o700)
    catalog = {
        "schema_version": CATALOG_SCHEMA,
        "installation_id": "glorp-installation",
        "custody_root": "custody",
        "receipt_store_root": "receipts",
        "custody_references": {
            "credential-store:sentientos/edge-source": {
                "kind": "bridge_key",
                "relative_path": "keys/edge-source.bin",
                "protection": "posix_private_file",
                "passphrase_reference": None,
            },
        },
    }
    catalog_path = root / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, sort_keys=True), encoding="utf-8")
    os.chmod(catalog_path, 0o600)
    now = datetime.now(timezone.utc)
    subject = {
        "action": "install_platform_catalog",
        "installation_id": catalog["installation_id"],
        "catalog_digest": "sha256:" + hashlib.sha256(
            canonical_receipt_bytes(catalog)).hexdigest(),
    }
    body = {
        "schema_version": RECEIPT_SCHEMA,
        "receipt_type": "platform_catalog",
        "issuer_id": "fixture-install-authority",
        "decision": "allow",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "subject": subject,
    }
    receipt = {
        **body,
        "semantic_digest": "sha256:" + hashlib.sha256(
            canonical_receipt_bytes(body)).hexdigest(),
        "signature": base64.b64encode(
            private_key.sign(canonical_receipt_bytes(body))).decode("ascii"),
    }
    return root, catalog, catalog_path, receipt, public_key


def test_signed_platform_catalog_builds_custody_and_authority_adapters(tmp_path: Path) -> None:
    root, _catalog, _path, receipt, public_key = _fixture(tmp_path)

    installation = load_companion_platform_installation(
        installation_root=root, catalog_relative_path="catalog.json",
        catalog_receipt=receipt,
        trusted_issuer_public_keys={"fixture-install-authority": public_key},
        system_name="Linux", is_wsl2=True)

    assert installation.installation_id == "glorp-installation"
    assert installation.catalog_digest == receipt["subject"]["catalog_digest"]
    assert installation.custody.read_bridge_key(
        "credential-store:sentientos/edge-source") == b"e" * 32
    assert type(installation.authority).__name__ == "CompanionAuthorityCallbacks"


def test_platform_catalog_signature_binds_reference_paths_before_asset_access(
        tmp_path: Path) -> None:
    root, catalog, catalog_path, receipt, public_key = _fixture(tmp_path)
    catalog["custody_references"]["credential-store:sentientos/edge-source"][
        "relative_path"] = "keys/changed.bin"
    catalog_path.write_text(json.dumps(catalog, sort_keys=True), encoding="utf-8")
    os.chmod(catalog_path, 0o600)

    with pytest.raises(CompanionPlatformInstallationCatalogError,
                       match="companion_installation_catalog_authority_invalid"):
        load_companion_platform_installation(installation_root=root,
            catalog_relative_path="catalog.json", catalog_receipt=receipt,
            trusted_issuer_public_keys={"fixture-install-authority": public_key},
            system_name="Linux", is_wsl2=True)


def test_platform_catalog_rejects_untrusted_receipt_and_path_escape(tmp_path: Path) -> None:
    root, catalog, catalog_path, receipt, public_key = _fixture(tmp_path)
    receipt["signature"] = base64.b64encode(b"x" * 64).decode("ascii")
    with pytest.raises(CompanionPlatformInstallationCatalogError,
                       match="companion_installation_catalog_authority_invalid"):
        load_companion_platform_installation(installation_root=root,
            catalog_relative_path="catalog.json", catalog_receipt=receipt,
            trusted_issuer_public_keys={"fixture-install-authority": public_key},
            system_name="Linux", is_wsl2=True)

    catalog["custody_root"] = "../outside"
    catalog_path.write_text(json.dumps(catalog, sort_keys=True), encoding="utf-8")
    os.chmod(catalog_path, 0o600)
    with pytest.raises(CompanionPlatformInstallationCatalogError,
                       match="companion_installation_relative_path_invalid"):
        load_companion_platform_installation(installation_root=root,
            catalog_relative_path="catalog.json", catalog_receipt=receipt,
            trusted_issuer_public_keys={"fixture-install-authority": public_key},
            system_name="Linux", is_wsl2=True)


def test_platform_catalog_rejects_duplicate_json_fields_and_open_permissions(
        tmp_path: Path) -> None:
    root, _catalog, catalog_path, receipt, public_key = _fixture(tmp_path)
    catalog_path.write_text('{"schema_version":"ignored","schema_version":"also-ignored"}',
                            encoding="utf-8")
    os.chmod(catalog_path, 0o600)
    with pytest.raises(CompanionPlatformInstallationCatalogError,
                       match="companion_installation_catalog_invalid_json"):
        load_companion_platform_installation(installation_root=root,
            catalog_relative_path="catalog.json", catalog_receipt=receipt,
            trusted_issuer_public_keys={"fixture-install-authority": public_key},
            system_name="Linux", is_wsl2=True)

    catalog_path.write_text("{}", encoding="utf-8")
    os.chmod(catalog_path, 0o644)
    with pytest.raises(CompanionPlatformInstallationCatalogError,
                       match="companion_installation_catalog_custody_invalid"):
        load_companion_platform_installation(installation_root=root,
            catalog_relative_path="catalog.json", catalog_receipt=receipt,
            trusted_issuer_public_keys={"fixture-install-authority": public_key},
            system_name="Linux", is_wsl2=True)
