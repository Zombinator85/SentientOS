"""Security and integration tests for immutable root-issuer public trust custody."""
from __future__ import annotations

import ast
import base64
import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentientos.causal_resource_principal import CausalResourcePrincipal, RootPrincipalIssuer, VerifiedOperatorSponsorship
from sentientos.causal_resource_principal_authentication import (
    AuthenticatedRootPrincipalEvidence,
    RootIssuerProvenanceError,
    RootIssuerProvenanceVerifier,
    RootPrincipalIssuerProvenance,
    TrustedRootIssuerKey,
    canonical_root_provenance_payload,
)
from sentientos.causal_resource_principal_ed25519 import CryptographyEd25519RootIssuerSignatureVerifier
import sentientos.causal_resource_principal_trust_catalog as catalog_module
from sentientos.causal_resource_principal_trust_catalog import (
    CATALOG_SCHEMA,
    ReadOnlyTrustedIssuerCatalog,
    TrustedIssuerCatalogError,
    catalog_digest_for,
)

pytestmark = pytest.mark.no_legacy_skip


def encoded(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def key_material(seed: int = 0) -> tuple[Ed25519PrivateKey, str, str]:
    private = Ed25519PrivateKey.from_private_bytes(bytes((value + seed) % 256 for value in range(32)))
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, encoded(raw), "ed25519-sha256:" + hashlib.sha256(raw).hexdigest()


def catalog_value(*, seed: int = 0, issuer_id: str = "resource-principal-issuer", version: int = 1) -> dict[str, object]:
    _, public_key, key_id = key_material(seed)
    value: dict[str, object] = {
        "schema": CATALOG_SCHEMA,
        "catalog_version": version,
        "entries": [{
            "issuer_id": issuer_id,
            "signing_key_id": key_id,
            "algorithm": "ed25519",
            "public_key": public_key,
            "valid_from": "2026-09-21T07:00:00Z",
            "valid_until": "2026-09-21T10:00:00Z",
            "revocation_status": "active",
        }],
    }
    value["catalog_digest"] = catalog_digest_for(value)
    return value


def write_catalog(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load(path: Path, value: dict[str, object]) -> ReadOnlyTrustedIssuerCatalog:
    return ReadOnlyTrustedIssuerCatalog.load(
        path,
        expected_catalog_version=cast(int, value["catalog_version"]),
        expected_catalog_digest=str(value["catalog_digest"]),
    )


def test_valid_catalog_loads_and_exact_lookup_succeeds(tmp_path: Path) -> None:
    value = catalog_value(); path = tmp_path / "catalog.json"; write_catalog(path, value)
    catalog = load(path, value)
    entry = cast(list[dict[str, Any]], value["entries"])[0]
    assert catalog.lookup(issuer_id=entry["issuer_id"], signing_key_id=entry["signing_key_id"], algorithm="ed25519") == TrustedRootIssuerKey(**entry)
    assert catalog.catalog_version == 1
    assert catalog.catalog_digest == value["catalog_digest"]


def test_unknown_exact_tuples_return_no_trust(tmp_path: Path) -> None:
    value = catalog_value(); path = tmp_path / "catalog.json"; write_catalog(path, value); catalog = load(path, value)
    entry = value["entries"][0]  # type: ignore[index]
    assert catalog.lookup(issuer_id="unknown", signing_key_id=entry["signing_key_id"], algorithm="ed25519") is None
    assert catalog.lookup(issuer_id=entry["issuer_id"], signing_key_id="ed25519-sha256:" + "0" * 64, algorithm="ed25519") is None
    assert catalog.lookup(issuer_id=entry["issuer_id"], signing_key_id=entry["signing_key_id"], algorithm="Ed25519") is None


@pytest.mark.parametrize("mutation", ["schema", "version", "missing", "extra"])
def test_nonexact_or_unsupported_catalog_shape_fails_closed(tmp_path: Path, mutation: str) -> None:
    value = catalog_value()
    if mutation == "schema": value["schema"] = "wrong:v1"
    elif mutation == "version": value["catalog_version"] = 0
    elif mutation == "missing": del value["entries"]
    else: value["extra"] = True
    value["catalog_digest"] = catalog_digest_for(value)
    path = tmp_path / "catalog.json"; write_catalog(path, value)
    with pytest.raises(TrustedIssuerCatalogError):
        ReadOnlyTrustedIssuerCatalog.load(path, expected_catalog_version=1, expected_catalog_digest=str(value["catalog_digest"]))


def test_digest_corruption_fails_closed(tmp_path: Path) -> None:
    value = catalog_value(); value["catalog_digest"] = "sha256:" + "g" * 64
    path = tmp_path / "catalog.json"; write_catalog(path, value)
    with pytest.raises(TrustedIssuerCatalogError, match="^invalid_catalog_digest$"):
        ReadOnlyTrustedIssuerCatalog.load(path, expected_catalog_version=1, expected_catalog_digest="sha256:" + "0" * 64)
    value = catalog_value(); expected = str(value["catalog_digest"])
    value["entries"][0]["valid_until"] = "2026-09-21T11:00:00Z"  # type: ignore[index]
    write_catalog(path, value)
    with pytest.raises(TrustedIssuerCatalogError, match="^catalog_digest_mismatch$"):
        ReadOnlyTrustedIssuerCatalog.load(path, expected_catalog_version=1, expected_catalog_digest=expected)


def test_operator_expected_catalog_substitution_fails_closed(tmp_path: Path) -> None:
    trusted = catalog_value(seed=0); attacker = catalog_value(seed=1)
    path = tmp_path / "catalog.json"; write_catalog(path, attacker)
    with pytest.raises(TrustedIssuerCatalogError, match="^unexpected_catalog_digest$"):
        ReadOnlyTrustedIssuerCatalog.load(path, expected_catalog_version=1, expected_catalog_digest=str(trusted["catalog_digest"]))
    newer = catalog_value(seed=0, version=2); write_catalog(path, newer)
    with pytest.raises(TrustedIssuerCatalogError, match="^unexpected_catalog_version$"):
        ReadOnlyTrustedIssuerCatalog.load(path, expected_catalog_version=1, expected_catalog_digest=str(newer["catalog_digest"]))


def test_duplicate_exact_trust_tuple_fails_closed(tmp_path: Path) -> None:
    value = catalog_value(); entries = cast(list[dict[str, object]], value["entries"]); entries.append(copy.deepcopy(entries[0]))
    value["catalog_digest"] = catalog_digest_for(value); path = tmp_path / "catalog.json"; write_catalog(path, value)
    with pytest.raises(TrustedIssuerCatalogError, match="^duplicate_trust_tuple$"):
        load(path, value)


@pytest.mark.parametrize("issuer", ["Bad", "", "all", "any", " space"])
def test_invalid_or_reserved_issuer_fails_closed(tmp_path: Path, issuer: str) -> None:
    value = catalog_value(); value["entries"][0]["issuer_id"] = issuer  # type: ignore[index]
    value["catalog_digest"] = catalog_digest_for(value); path = tmp_path / "catalog.json"; write_catalog(path, value)
    with pytest.raises(TrustedIssuerCatalogError, match="^invalid_issuer_id$"): load(path, value)


@pytest.mark.parametrize("public_key", ["bad!", "eA==", "eA ", "+" * 43, encoded(b"x" * 31)])
def test_canonical_ed25519_public_key_encoding_is_enforced(tmp_path: Path, public_key: str) -> None:
    value = catalog_value(); value["entries"][0]["public_key"] = public_key  # type: ignore[index]
    value["catalog_digest"] = catalog_digest_for(value); path = tmp_path / "catalog.json"; write_catalog(path, value)
    with pytest.raises(TrustedIssuerCatalogError, match="^invalid_public_key$"): load(path, value)


def test_derived_signing_key_id_is_enforced(tmp_path: Path) -> None:
    value = catalog_value(); value["entries"][0]["signing_key_id"] = "ed25519-sha256:" + "0" * 64  # type: ignore[index]
    value["catalog_digest"] = catalog_digest_for(value); path = tmp_path / "catalog.json"; write_catalog(path, value)
    with pytest.raises(TrustedIssuerCatalogError, match="^invalid_signing_key_id$"): load(path, value)


@pytest.mark.parametrize(("field", "replacement"), [("valid_from", "2026-09-21 07:00:00Z"), ("valid_until", "bad"), ("valid_until", "2026-09-21T07:00:00Z")])
def test_exact_ordered_validity_is_enforced(tmp_path: Path, field: str, replacement: str) -> None:
    value = catalog_value(); value["entries"][0][field] = replacement  # type: ignore[index]
    value["catalog_digest"] = catalog_digest_for(value); path = tmp_path / "catalog.json"; write_catalog(path, value)
    with pytest.raises(TrustedIssuerCatalogError, match="^invalid_entry_validity$"): load(path, value)


@pytest.mark.parametrize(("field", "replacement", "reason"), [("algorithm", "ssh-ed25519", "unsupported_entry_algorithm"), ("revocation_status", "unknown", "invalid_revocation_status")])
def test_algorithm_and_static_revocation_vocabularies_are_exact(tmp_path: Path, field: str, replacement: str, reason: str) -> None:
    value = catalog_value(); value["entries"][0][field] = replacement  # type: ignore[index]
    value["catalog_digest"] = catalog_digest_for(value); path = tmp_path / "catalog.json"; write_catalog(path, value)
    with pytest.raises(TrustedIssuerCatalogError, match=f"^{reason}$"): load(path, value)


def test_loaded_catalog_is_immutable_and_does_not_reload(tmp_path: Path) -> None:
    value = catalog_value(); path = tmp_path / "catalog.json"; write_catalog(path, value); catalog = load(path, value)
    with pytest.raises(FrozenInstanceError): catalog.catalog_version = 2  # type: ignore[misc]
    with pytest.raises(TypeError): catalog._entries[("x", "y", "z")] = catalog._entries[next(iter(catalog._entries))]  # type: ignore[index]
    path.write_text("not json", encoding="utf-8")
    entry = value["entries"][0]  # type: ignore[index]
    assert catalog.lookup(issuer_id=entry["issuer_id"], signing_key_id=entry["signing_key_id"], algorithm="ed25519") is not None


def test_source_exposes_no_mutation_private_key_signing_secret_or_network_capability() -> None:
    source = Path(catalog_module.__file__).read_text(encoding="utf-8"); tree = ast.parse(source)
    forbidden_names = {"add", "insert", "update", "delete", "revoke", "rotate", "enroll", "import_key", "generate_key", "save", "write", "commit", "sign", "generate", "urlopen", "request", "getenv"}
    public_methods = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")}
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    called = {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))}
    assert public_methods == {"catalog_digest_for", "load", "lookup"}
    assert called.isdisjoint(forbidden_names)
    assert imported.isdisjoint({"Ed25519PrivateKey", "keyring", "requests", "urllib", "socket", "nacl.signing"})
    assert all(token not in source for token in ("private_key", "environment secret", "SSH signer", "HMAC signer"))


class Sponsor:
    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        return VerifiedOperatorSponsorship("sha256:" + "1" * 64)


def integration_claim(private: Ed25519PrivateKey, key_id: str) -> tuple[CausalResourcePrincipal, RootPrincipalIssuerProvenance]:
    principal = RootPrincipalIssuer(issuer_id="resource-principal-issuer", sponsorship_verifier=Sponsor()).mint_root(
        sponsorship_evidence={}, subject_binding_digest="sha256:" + "2" * 64, epoch=1,
        issued_at="2026-09-21T08:00:00Z", expires_at="2026-09-21T09:00:00Z")
    signed_at = "2026-09-21T08:10:00Z"
    payload = canonical_root_provenance_payload(principal_id=principal.principal_id, principal_binding_digest=principal.binding_digest,
        issuer_id=principal.issuer_id, signing_key_id=key_id, algorithm="ed25519", signed_at=signed_at)
    provenance = RootPrincipalIssuerProvenance.create(principal_id=principal.principal_id, principal_binding_digest=principal.binding_digest,
        issuer_id=principal.issuer_id, signing_key_id=key_id, algorithm="ed25519", signed_at=signed_at, signature=encoded(private.sign(payload)))
    return principal, provenance


def test_catalog_to_real_ed25519_verifier_returns_exact_authenticated_evidence(tmp_path: Path) -> None:
    private, _, key_id = key_material(); value = catalog_value(); path = tmp_path / "catalog.json"; write_catalog(path, value)
    principal, provenance = integration_claim(private, key_id)
    result = RootIssuerProvenanceVerifier(trust_store=load(path, value), signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier()).verify(
        principal, provenance, current_time="2026-09-21T08:30:00Z")
    assert result == AuthenticatedRootPrincipalEvidence(principal_id=principal.principal_id, principal_binding_digest=principal.binding_digest,
        provenance_digest=provenance.provenance_digest, issuer_id=principal.issuer_id, signing_key_id=key_id,
        algorithm="ed25519", signed_at="2026-09-21T08:10:00Z")


def test_valid_signature_under_untrusted_key_is_trusted_key_not_found(tmp_path: Path) -> None:
    untrusted_private, _, untrusted_key_id = key_material(seed=1); value = catalog_value(seed=0)
    path = tmp_path / "catalog.json"; write_catalog(path, value); principal, provenance = integration_claim(untrusted_private, untrusted_key_id)
    with pytest.raises(RootIssuerProvenanceError, match="^trusted_key_not_found$"):
        RootIssuerProvenanceVerifier(trust_store=load(path, value), signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier()).verify(
            principal, provenance, current_time="2026-09-21T08:30:00Z")
