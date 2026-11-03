from __future__ import annotations

import json
import os
import ssl
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from sentientos.gaming_companion_platform_custody import (
    CompanionCustodyReference,
    CompanionCustodyReferenceError,
    CompanionPlatformCustodyResolver,
)
from sentientos.gaming_companion_tls_transport import BridgeGenerationCustodyRecord
from tests.test_gaming_companion_tls_transport import _certificate_bundle

pytestmark = pytest.mark.no_legacy_skip


def _entry(kind: str, path: str, protection: str, password_ref: str | None = None):
    return CompanionCustodyReference(kind, path, protection, password_ref)


def _custody_fixture(root: Path):
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    server_context, client_context, _peer_pin = _certificate_bundle(root)
    del server_context, client_context
    password = b"fixture TLS private key passphrase 32 bytes"
    for filename in ("server.key", "client.key"):
        key_path = root / filename
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(password)))
        os.chmod(key_path, 0o600)
    password_path = root / "tls-password.bin"
    password_path.write_bytes(password)
    os.chmod(password_path, 0o600)
    source_path = root / "source.key"
    source_path.write_bytes(b"s" * 32)
    os.chmod(source_path, 0o600)
    records = (
        BridgeGenerationCustodyRecord("windows-edge", "edge-g2", "wsl:edge-key", "authority",
            "2026-11-03T12:00:00+00:00", "a" * 64, "edge-g1"),
        BridgeGenerationCustodyRecord("wsl-core", "core-g2", "wsl:core-key", "authority",
            "2026-11-03T12:00:00+00:00", "b" * 64, "core-g1"),
    )
    for name, record in zip(("edge-generation.json", "core-generation.json"), records):
        target = root / name
        target.write_text(json.dumps(record.to_dict()), encoding="utf-8")
        os.chmod(target, 0o600)
    refs = {
        "credential-store:edge-source": _entry("bridge_key", "source.key", "posix_private_file"),
        "generation:edge": _entry("generation_record", "edge-generation.json", "private_record"),
        "generation:core": _entry("generation_record", "core-generation.json", "private_record"),
        "tls:ca": _entry("ca_bundle", "ca.pem", "public_file"),
        "tls:server-cert": _entry("certificate", "server.pem", "public_file"),
        "tls:client-cert": _entry("certificate", "client.pem", "public_file"),
        "tls:server-key": _entry("private_key", "server.key", "encrypted_pem", "secret:tls-pass"),
        "tls:client-key": _entry("private_key", "client.key", "encrypted_pem", "secret:tls-pass"),
        "secret:tls-pass": _entry("secret", "tls-password.bin", "posix_private_file"),
    }
    return refs


def test_wsl_custody_resolves_generation_keys_and_mtls_contexts(tmp_path: Path) -> None:
    root = tmp_path / "custody"
    refs = _custody_fixture(root)
    resolver = CompanionPlatformCustodyResolver(root=root, references=refs,
        system_name="Linux", is_wsl2=True)

    assert resolver.read_bridge_key("credential-store:edge-source") == b"s" * 32
    pair = resolver.load_generation_pair("generation:edge", "generation:core")
    assert pair.source.generation_id == "edge-g2"
    assert pair.acknowledgment.generation_id == "core-g2"
    server = resolver.server_tls_context("tls:ca", "tls:server-cert", "tls:server-key")
    client = resolver.client_tls_context("tls:ca", "tls:client-cert", "tls:client-key")
    assert server.verify_mode == ssl.CERT_REQUIRED
    assert server.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert client.check_hostname is True
    assert client.verify_mode == ssl.CERT_REQUIRED


def test_windows_custody_uses_dpapi_reader_for_opaque_key_reference(tmp_path: Path) -> None:
    root = tmp_path / "windows-custody"
    root.mkdir()
    blob = root / "edge.dpapi"
    blob.write_bytes(b"fixture ciphertext")
    seen: list[Path] = []

    def unseal(path: Path) -> bytes:
        seen.append(path)
        return b"w" * 32

    resolver = CompanionPlatformCustodyResolver(root=root,
        references={"credential-store:edge-source": _entry(
            "bridge_key", "edge.dpapi", "windows_dpapi")},
        system_name="Windows", is_wsl2=False, windows_key_reader=unseal)

    assert resolver.read_bridge_key("credential-store:edge-source") == b"w" * 32
    assert seen == [blob]


@pytest.mark.parametrize("relative_path", ["../outside.key", "/absolute.key", "folder\\escape.key", "C:/escape.key"])
def test_custody_catalog_rejects_paths_that_escape_or_change_platform_root(
        tmp_path: Path, relative_path: str) -> None:
    root = tmp_path / "custody"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    resolver = CompanionPlatformCustodyResolver(root=root,
        references={"secret:source": _entry("bridge_key", relative_path, "posix_private_file")},
        system_name="Linux", is_wsl2=True)

    with pytest.raises(CompanionCustodyReferenceError,
                       match="companion_custody_relative_path_invalid"):
        resolver.read_bridge_key("secret:source")


def test_custody_catalog_rejects_symlink_asset_and_unknown_reference(tmp_path: Path) -> None:
    root = tmp_path / "custody"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    outside = tmp_path / "outside.key"
    outside.write_bytes(b"x" * 32)
    os.chmod(outside, 0o600)
    (root / "source.key").symlink_to(outside)
    resolver = CompanionPlatformCustodyResolver(root=root,
        references={"secret:source": _entry("bridge_key", "source.key", "posix_private_file")},
        system_name="Linux", is_wsl2=True)

    with pytest.raises(CompanionCustodyReferenceError,
                       match="companion_custody_reparse_path_forbidden"):
        resolver.read_bridge_key("secret:source")
    with pytest.raises(CompanionCustodyReferenceError,
                       match="companion_custody_reference_unresolved"):
        resolver.read_bridge_key("secret:unmapped")


def test_custody_catalog_rejects_incompatible_protection_and_nonstring_path(tmp_path: Path) -> None:
    root = tmp_path / "custody"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    with pytest.raises(CompanionCustodyReferenceError,
                       match="companion_custody_reference_catalog_invalid"):
        CompanionPlatformCustodyResolver(root=root,
            references={"secret:wrong-protection": _entry(
                "bridge_key", "key.bin", "encrypted_pem")},
            system_name="Linux", is_wsl2=True)
    with pytest.raises(CompanionCustodyReferenceError,
                       match="companion_custody_reference_catalog_invalid"):
        CompanionPlatformCustodyResolver(root=root,
            references={"secret:wrong-path": CompanionCustodyReference(
                "bridge_key", None, "posix_private_file")},
            system_name="Linux", is_wsl2=True)


def test_linux_host_that_is_not_wsl_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "custody"
    root.mkdir()
    with pytest.raises(CompanionCustodyReferenceError, match="companion_custody_wsl2_required"):
        CompanionPlatformCustodyResolver(root=root,
            references={"secret:source": _entry("bridge_key", "source.key", "posix_private_file")},
            system_name="Linux", is_wsl2=False)

@pytest.mark.skipif(os.name != "nt", reason="CurrentUser DPAPI requires Windows")
def test_windows_dpapi_reader_unseals_current_user_key(tmp_path: Path) -> None:
    import ctypes

    from sentientos.gaming_companion_tls_transport import (
        read_windows_dpapi_bridge_source_key,
    )

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32),
                    ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    plaintext = b"disposable GLORP DPAPI custody test key" + b"x" * 32
    source_buffer = (ctypes.c_ubyte * len(plaintext)).from_buffer_copy(plaintext)
    source = DataBlob(len(plaintext),
        ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    protected = DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = (
        ctypes.POINTER(DataBlob), ctypes.c_wchar_p, ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.POINTER(DataBlob))
    crypt32.CryptProtectData.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p

    if not crypt32.CryptProtectData(
            ctypes.byref(source), "SentientOS disposable test key", None,
            None, None, 0x1, ctypes.byref(protected)):
        raise AssertionError("CryptProtectData failed")

    protected_path = tmp_path / "disposable-current-user.dpapi"
    try:
        protected_path.write_bytes(
            ctypes.string_at(protected.pbData, protected.cbData))
    finally:
        ctypes.memset(protected.pbData, 0, protected.cbData)
        kernel32.LocalFree(protected.pbData)

    assert read_windows_dpapi_bridge_source_key(protected_path) == plaintext
