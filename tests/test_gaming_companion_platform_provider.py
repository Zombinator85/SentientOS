from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from sentientos.gaming_companion_authority import CompanionAuthorityCallbacks
from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_core_runtime import WSLCoreGamingCompanionRuntime
from sentientos.gaming_companion_edge_runtime import WindowsEdgeAvatarRuntime
from sentientos.gaming_companion_platform_custody import (
    CompanionCustodyReference,
    CompanionPlatformCustodyResolver,
)
from sentientos.gaming_companion_platform_provider import GamingCompanionPlatformRoleProvider
from sentientos.gaming_companion_tls_transport import BridgeGenerationCustodyRecord
from tests.test_gaming_companion_deployment import _reverse_mutual_tls_manifest
from tests.test_gaming_companion_tls_transport import _certificate_bundle

pytestmark = pytest.mark.no_legacy_skip

_TLS_PASSWORD = b"fixture tls private key passphrase with enough bytes"


def _authority(*, allow_role: bool = True):
    # Fixture callbacks deliberately stand in for the already-tested signed
    # verifier/store. They never authorize a real deployment.
    value = object.__new__(CompanionAuthorityCallbacks)
    value.verify_generation = lambda _digest, _record: True
    value.authorize_role_launch = lambda _role, _manifest: allow_role
    return value


def _generation(source_id: str, generation_id: str, key_ref: str, digest: str):
    return BridgeGenerationCustodyRecord(source_id, generation_id, key_ref,
        "fixture-authority", "2026-11-03T12:00:00+00:00", digest * 64, None)


def _custody(root: Path, *, wsl: bool):
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    _certificate_bundle(root)
    for filename in ("server.key", "client.key"):
        path = root / filename
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(_TLS_PASSWORD)))
        os.chmod(path, 0o600)
    (root / "tls-password.bin").write_bytes(_TLS_PASSWORD)
    os.chmod(root / "tls-password.bin", 0o600)
    records = {
        "operator-ledger:windows-edge-generation": _generation(
            "windows-edge", "edge-forward-1", "credential-store:sentientos/windows-edge-source", "a"),
        "operator-ledger:wsl-core-generation": _generation(
            "wsl-core", "core-forward-ack-1", "credential-store:sentientos/wsl-core-forward-ack", "b"),
        "operator-ledger:wsl-core-avatar-generation": _generation(
            "wsl-core", "core-avatar-1", "credential-store:sentientos/wsl-core-avatar-source", "c"),
        "operator-ledger:windows-edge-avatar-generation": _generation(
            "windows-edge", "edge-avatar-ack-1", "credential-store:sentientos/windows-edge-avatar-ack", "d"),
    }
    record_files = {}
    for index, (reference, record) in enumerate(records.items()):
        filename = f"generation-{index}.json"
        (root / filename).write_text(json.dumps(record.to_dict()), encoding="utf-8")
        os.chmod(root / filename, 0o600)
        record_files[reference] = filename
    key_names = (
        "credential-store:sentientos/windows-edge-source",
        "credential-store:sentientos/wsl-core-forward-ack",
        "credential-store:sentientos/wsl-core-avatar-source",
        "credential-store:sentientos/windows-edge-avatar-ack",
    )
    references = {
        key: CompanionCustodyReference("bridge_key", f"key-{index}.bin",
            "posix_private_file" if wsl else "windows_dpapi")
        for index, key in enumerate(key_names)
    }
    for index, key in enumerate(key_names):
        (root / f"key-{index}.bin").write_bytes(bytes([index + 1]) * 32)
        os.chmod(root / f"key-{index}.bin", 0o600)
    for reference, filename in record_files.items():
        references[reference] = CompanionCustodyReference(
            "generation_record", filename, "private_record")
    references.update({
        "windows:credential-store/bridge-ca": CompanionCustodyReference("ca_bundle", "ca.pem", "public_file"),
        "wsl:/etc/sentientos/bridge/ca.pem": CompanionCustodyReference("ca_bundle", "ca.pem", "public_file"),
        "wsl:/etc/sentientos/bridge/core.pem": CompanionCustodyReference("certificate", "server.pem", "public_file"),
        "wsl:/etc/sentientos/bridge/core.key": CompanionCustodyReference("private_key", "server.key", "encrypted_pem", "secret:tls-password"),
        "windows:credential-store/edge-server-cert": CompanionCustodyReference("certificate", "server.pem", "public_file"),
        "wsl:/etc/sentientos/bridge/core-client.pem": CompanionCustodyReference("certificate", "client.pem", "public_file"),
        "windows:dpapi/edge-server-key": CompanionCustodyReference("private_key", "server.key", "encrypted_pem", "secret:tls-password"),
        "wsl:/etc/sentientos/bridge/core-client.key": CompanionCustodyReference("private_key", "client.key", "encrypted_pem", "secret:tls-password"),
        "secret:tls-password": CompanionCustodyReference("secret", "tls-password.bin",
            "posix_private_file" if wsl else "windows_dpapi"),
    })
    if wsl:
        resolver = CompanionPlatformCustodyResolver(root=root, references=references,
            system_name="Linux", is_wsl2=True,
            posix_key_reader=lambda path: path.read_bytes())
    else:
        resolver = CompanionPlatformCustodyResolver(root=root, references=references,
            system_name="Windows", is_wsl2=False,
            windows_key_reader=lambda _path: _TLS_PASSWORD)
    return resolver


def test_platform_provider_composes_windows_edge_with_custody_and_explicit_renderer_hooks(
        tmp_path: Path) -> None:
    resolver = _custody(tmp_path / "windows", wsl=False)
    provider = GamingCompanionPlatformRoleProvider(custody=resolver,
        authority=_authority(), windows_avatar_state_path=tmp_path / "avatar-state.json",
        command_receipt_verifier=lambda _receipt_id, _digest, _message: True,
        system_name="Windows", is_wsl2=False)

    runtime = provider.create_runtime("windows_edge", _reverse_mutual_tls_manifest())

    assert type(runtime) is WindowsEdgeAvatarRuntime
    assert runtime.status().state == "stopped"
    assert runtime.status().renderer_effect_proven is False


def test_platform_provider_composes_wsl_core_and_requires_governed_admission_hook(
        tmp_path: Path) -> None:
    resolver = _custody(tmp_path / "wsl", wsl=True)
    provider = GamingCompanionPlatformRoleProvider(custody=resolver,
        authority=_authority(), admission_receipt_builder=lambda _authorization: {
            "receipt_id": "fixture-only", "semantic_digest": "f" * 64},
        system_name="Linux", is_wsl2=True)

    runtime = provider.create_runtime("wsl_core", _reverse_mutual_tls_manifest())

    assert type(runtime) is WSLCoreGamingCompanionRuntime
    assert runtime.status()["state"] == "stopped"
    assert runtime.status()["authority_effects_performed"] is False
    runtime.close()


def test_platform_provider_fails_closed_before_secret_reads_or_runtime_creation(
        tmp_path: Path) -> None:
    resolver = _custody(tmp_path / "wsl", wsl=True)
    provider = GamingCompanionPlatformRoleProvider(custody=resolver,
        authority=_authority(allow_role=False), admission_receipt_builder=lambda _authorization: {},
        system_name="Linux", is_wsl2=True)

    with pytest.raises(CompanionBridgeError,
                       match="companion_role_launch_authority_denied"):
        provider.create_runtime("wsl_core", _reverse_mutual_tls_manifest())


def test_platform_provider_requires_the_native_host_for_each_role(tmp_path: Path) -> None:
    resolver = _custody(tmp_path / "wsl", wsl=True)
    provider = GamingCompanionPlatformRoleProvider(custody=resolver,
        authority=_authority(), admission_receipt_builder=lambda _authorization: {},
        system_name="Linux", is_wsl2=False)

    with pytest.raises(CompanionBridgeError, match="companion_platform_windows_required"):
        provider.create_runtime("windows_edge", _reverse_mutual_tls_manifest())
    with pytest.raises(CompanionBridgeError, match="companion_platform_wsl2_required"):
        provider.create_runtime("wsl_core", _reverse_mutual_tls_manifest())


def test_platform_provider_does_not_supply_missing_application_authority_hooks(
        tmp_path: Path) -> None:
    windows = _custody(tmp_path / "windows", wsl=False)
    edge = GamingCompanionPlatformRoleProvider(custody=windows,
        authority=_authority(), system_name="Windows", is_wsl2=False)
    with pytest.raises(CompanionBridgeError,
                       match="companion_windows_avatar_state_path_required"):
        edge.create_runtime("windows_edge", _reverse_mutual_tls_manifest())

    wsl = _custody(tmp_path / "wsl", wsl=True)
    core = GamingCompanionPlatformRoleProvider(custody=wsl,
        authority=_authority(), system_name="Linux", is_wsl2=True)
    with pytest.raises(CompanionBridgeError,
                       match="companion_core_admission_receipt_builder_required"):
        core.create_runtime("wsl_core", _reverse_mutual_tls_manifest())
