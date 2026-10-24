from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from sentientos.federation import peer_health_source_factory as factory
from sentientos.federation.peer_authentication_ed25519 import (
    CryptographyEd25519FederationPeerSignatureVerifier,
)
from sentientos.federation.peer_health_source_factory import (
    PIN_SCHEMA,
    WINDOWS_PIN_SCHEMA,
    FederationPeerHealthSourceFactoryError,
    load_operator_pinned_peer_health_sources,
)
from sentientos.federation.peer_replay_owner import FederationPeerReplayOwner
from sentientos.federation.peer_trust_catalog import CATALOG_SCHEMA, catalog_digest_for

pytestmark = [
    pytest.mark.no_legacy_skip,
    pytest.mark.skipif(os.name == "nt", reason="uses POSIX private-file fixtures"),
]


def _write_pinned_peer(
    tmp_path: Path, *, peer_id: str = "peer-one", windows_identity: tuple[int, bytes] | None = None,
) -> tuple[Path, Path, str]:
    runtime_root = tmp_path / "runtime"
    catalog_path = runtime_root / "federation" / "peer_trust_catalogs" / f"{peer_id}.json"
    catalog_path.parent.mkdir(parents=True)
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_text = base64.urlsafe_b64encode(public).decode("ascii").rstrip("=")
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest()
    body = {
        "schema": CATALOG_SCHEMA,
        "catalog_version": 4,
        "entries": [{
            "peer_id": peer_id,
            "signing_key_id": key_id,
            "endpoint": "https://peer.example.test/presence",
            "algorithm": "ed25519",
            "public_key": public_text,
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_until": "2027-01-01T00:00:00Z",
            "revocation_status": "active",
        }],
    }
    catalog = {**body, "catalog_digest": catalog_digest_for(body)}
    catalog_raw = (json.dumps(catalog, sort_keys=True, separators=(",", ":")) + "\n").encode()
    catalog_path.write_bytes(catalog_raw)

    pin_path = tmp_path / "peer-health-pin.json"
    row = {
            "peer_id": peer_id,
            "catalog_version": 4,
            "catalog_digest": catalog["catalog_digest"],
            "max_age_seconds": 300,
        }
    if windows_identity is not None:
        row["root_identity"] = {
            "volume_serial_number": windows_identity[0],
            "file_id": windows_identity[1].hex(),
        }
    pin = {
        "schema": WINDOWS_PIN_SCHEMA if windows_identity is not None else PIN_SCHEMA,
        "peers": [row],
    }
    pin_path.write_text(json.dumps(pin, sort_keys=True, separators=(",", ":")) + "\n")
    pin_path.chmod(0o600)
    return pin_path, runtime_root, str(catalog["catalog_digest"])


def test_operator_pin_composes_exact_catalog_and_durable_peer_owner(tmp_path: Path):
    pin_path, runtime_root, digest = _write_pinned_peer(tmp_path)

    sources = load_operator_pinned_peer_health_sources(
        pin_path,
        runtime_root=runtime_root,
        configured_peer_ids={"peer-one", "peer-two"},
    )

    assert tuple(sources) == ("peer-one",)
    source = sources["peer-one"]
    assert source.owner.peer_id == "peer-one"
    assert source.owner.root == runtime_root / "federation" / "peer_health_replay" / "peer-one"
    assert source.catalog.catalog_digest == digest
    assert source.catalog.peer_ids == frozenset({"peer-one"})
    assert type(source.signature_verifier) is CryptographyEd25519FederationPeerSignatureVerifier
    assert source.max_age_seconds == 300
    assert not source.owner.root.exists()


def test_operator_pin_rejects_catalog_digest_drift(tmp_path: Path):
    pin_path, runtime_root, _ = _write_pinned_peer(tmp_path)
    pin = json.loads(pin_path.read_text())
    pin["peers"][0]["catalog_digest"] = "sha256:" + "0" * 64
    pin_path.write_text(json.dumps(pin, sort_keys=True, separators=(",", ":")) + "\n")
    pin_path.chmod(0o600)

    with pytest.raises(FederationPeerHealthSourceFactoryError, match="peer_health_trust_catalog_invalid"):
        load_operator_pinned_peer_health_sources(
            pin_path, runtime_root=runtime_root, configured_peer_ids={"peer-one"})


def test_operator_pin_rejects_catalog_containing_another_peer(tmp_path: Path):
    pin_path, runtime_root, _ = _write_pinned_peer(tmp_path)
    catalog_path = runtime_root / "federation" / "peer_trust_catalogs" / "peer-one.json"
    catalog = json.loads(catalog_path.read_text())
    other = dict(catalog["entries"][0])
    other["peer_id"] = "peer-two"
    catalog["entries"].append(other)
    catalog["catalog_digest"] = catalog_digest_for(catalog)
    catalog_path.write_text(json.dumps(catalog, sort_keys=True, separators=(",", ":")) + "\n")
    pin = json.loads(pin_path.read_text())
    pin["peers"][0]["catalog_digest"] = catalog["catalog_digest"]
    pin_path.write_text(json.dumps(pin, sort_keys=True, separators=(",", ":")) + "\n")
    pin_path.chmod(0o600)

    with pytest.raises(FederationPeerHealthSourceFactoryError, match="peer_health_trust_catalog_identity_mismatch"):
        load_operator_pinned_peer_health_sources(
            pin_path, runtime_root=runtime_root, configured_peer_ids={"peer-one", "peer-two"})


def test_operator_pin_rejects_unconfigured_peer(tmp_path: Path):
    pin_path, runtime_root, _ = _write_pinned_peer(tmp_path)

    with pytest.raises(FederationPeerHealthSourceFactoryError, match="peer_health_pin_peer_not_configured"):
        load_operator_pinned_peer_health_sources(
            pin_path, runtime_root=runtime_root, configured_peer_ids={"other-peer"})


def test_operator_pin_requires_private_file_custody(tmp_path: Path):
    pin_path, runtime_root, _ = _write_pinned_peer(tmp_path)
    pin_path.chmod(0o644)

    with pytest.raises(FederationPeerHealthSourceFactoryError, match="peer_health_pin_custody_invalid"):
        load_operator_pinned_peer_health_sources(
            pin_path, runtime_root=runtime_root, configured_peer_ids={"peer-one"})


def test_operator_pin_fails_closed_without_replay_owner_platform_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    pin_path, runtime_root, _ = _write_pinned_peer(tmp_path)
    monkeypatch.setattr(factory, "_supports_replay_owner_custody", lambda: False)

    with pytest.raises(FederationPeerHealthSourceFactoryError, match="peer_replay_owner_custody_unsupported"):
        load_operator_pinned_peer_health_sources(
            pin_path, runtime_root=runtime_root, configured_peer_ids={"peer-one"})


def test_windows_operator_pin_binds_existing_private_replay_root_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    identity = (0x123456789ABCDEF0, bytes(range(16)))
    pin_path, runtime_root, _ = _write_pinned_peer(tmp_path, windows_identity=identity)
    owner_root = runtime_root / "federation" / "peer_health_replay" / "peer-one"
    monkeypatch.setattr(factory, "_requires_windows_root_identity", lambda: True)
    monkeypatch.setattr(factory, "_supports_replay_owner_custody", lambda: True)
    monkeypatch.setattr(factory, "observe_private_directory_identity", lambda _root: identity)

    sources = load_operator_pinned_peer_health_sources(
        pin_path, runtime_root=runtime_root, configured_peer_ids={"peer-one"})

    assert sources["peer-one"].owner.root == owner_root
    assert sources["peer-one"].owner.expected_root_identity == identity


def test_windows_operator_pin_rejects_root_identity_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    pinned = (7, bytes(range(16)))
    replacement = (7, bytes(reversed(range(16))))
    pin_path, runtime_root, _ = _write_pinned_peer(tmp_path, windows_identity=pinned)
    monkeypatch.setattr(factory, "_requires_windows_root_identity", lambda: True)
    monkeypatch.setattr(factory, "_supports_replay_owner_custody", lambda: True)
    monkeypatch.setattr(factory, "observe_private_directory_identity", lambda _root: replacement)

    with pytest.raises(FederationPeerHealthSourceFactoryError,
                       match="peer_health_replay_root_identity_mismatch"):
        load_operator_pinned_peer_health_sources(
            pin_path, runtime_root=runtime_root, configured_peer_ids={"peer-one"})
    assert not (runtime_root / "federation" / "peer_health_replay" / "peer-one").exists()


def test_windows_operator_pin_rejects_legacy_unpinned_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    pin_path, runtime_root, _ = _write_pinned_peer(tmp_path)
    monkeypatch.setattr(factory, "_requires_windows_root_identity", lambda: True)
    monkeypatch.setattr(factory, "_supports_replay_owner_custody", lambda: True)

    with pytest.raises(FederationPeerHealthSourceFactoryError,
                       match="peer_health_pin_root_identity_required"):
        load_operator_pinned_peer_health_sources(
            pin_path, runtime_root=runtime_root, configured_peer_ids={"peer-one"})
    assert not (runtime_root / "federation" / "peer_health_replay" / "peer-one").exists()


def test_windows_operator_pin_rejects_malformed_root_identity(tmp_path: Path):
    pin_path, runtime_root, _ = _write_pinned_peer(
        tmp_path, windows_identity=(1, bytes(range(16))))
    pin = json.loads(pin_path.read_text())
    pin["peers"][0]["root_identity"]["file_id"] = "A" * 32
    pin_path.write_text(json.dumps(pin, sort_keys=True, separators=(",", ":")) + "\n")
    pin_path.chmod(0o600)

    with pytest.raises(FederationPeerHealthSourceFactoryError,
                       match="peer_health_pin_root_identity_invalid"):
        factory._load_pin(pin_path)


def test_operator_pin_rejects_invalid_path_argument(tmp_path: Path):
    with pytest.raises(FederationPeerHealthSourceFactoryError, match="peer_health_pin_path_invalid"):
        load_operator_pinned_peer_health_sources(
            42, runtime_root=tmp_path / "runtime", configured_peer_ids={"peer-one"})  # type: ignore[arg-type]


def test_operator_pin_rejects_string_configured_peer_collection(tmp_path: Path):
    pin_path, runtime_root, _ = _write_pinned_peer(tmp_path)

    with pytest.raises(
        FederationPeerHealthSourceFactoryError,
        match="peer_health_configured_peer_ids_invalid",
    ):
        load_operator_pinned_peer_health_sources(
            pin_path, runtime_root=runtime_root, configured_peer_ids="peer-one")  # type: ignore[arg-type]
