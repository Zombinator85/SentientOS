from __future__ import annotations

import ast
import base64
from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import json
from pathlib import Path
from typing import Callable, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import sentientos.causal_resource_principal_currentness as currentness
from sentientos.causal_resource_principal import CausalResourcePrincipal, RootPrincipalIssuer, VerifiedOperatorSponsorship
from sentientos.causal_resource_principal_authentication import AuthenticatedRootPrincipalEvidence, RootIssuerProvenanceVerifier
from sentientos.causal_resource_principal_ed25519 import CryptographyEd25519RootIssuerSignatureVerifier
from sentientos.causal_resource_principal_provenance_signer import CryptographyEd25519RootIssuerProvenanceSigner
from sentientos.causal_resource_principal_signer_custody import RootIssuerPrivateKeyBackend, RootIssuerPrivateKeyCustody, RootIssuerSigningKeyReference
from sentientos.causal_resource_principal_trust_catalog import CATALOG_SCHEMA, ReadOnlyTrustedIssuerCatalog, catalog_digest_for
from sentientos.causal_resource_principal_currentness import (
    CurrentAuthenticatedRootPrincipalEvidence, PrincipalCurrentnessError, PrincipalCurrentnessVerifier,
    ReadOnlyPrincipalRevocationRegistry, REGISTRY_SCHEMA, registry_digest_for,
)

pytestmark = pytest.mark.no_legacy_skip
ISSUER = "resource-principal-issuer"
SEED = bytes(range(32))
ISSUED = "2026-09-21T08:00:00Z"
SIGNED = "2026-09-21T08:10:00Z"
NOW = "2026-09-21T08:30:00Z"
EXPIRES = "2026-09-21T09:00:00Z"


class Sponsor:
    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        return VerifiedOperatorSponsorship("sha256:" + "1" * 64)


class Backend:
    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        return bytearray(base64.urlsafe_b64encode(SEED).rstrip(b"="))


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _authenticated(tmp_path: Path, *, issued: str = ISSUED, expires: str = EXPIRES, epoch: int = 1) -> tuple[CausalResourcePrincipal, AuthenticatedRootPrincipalEvidence, ReadOnlyTrustedIssuerCatalog]:
    public = Ed25519PrivateKey.from_private_bytes(SEED).public_key().public_bytes_raw()
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest()
    reference = RootIssuerSigningKeyReference(issuer_id=ISSUER, signing_key_id=key_id, algorithm="ed25519", key_reference="operator-key-v1")
    signer = CryptographyEd25519RootIssuerProvenanceSigner(
        reference=reference,
        custody=RootIssuerPrivateKeyCustody(reference=reference, backend=cast(RootIssuerPrivateKeyBackend, Backend())),
    )
    issuance = RootPrincipalIssuer(issuer_id=ISSUER, sponsorship_verifier=Sponsor(), provenance_signer=signer).mint_root_with_provenance(
        sponsorship_evidence={"operator": "signed"}, subject_binding_digest="sha256:" + "2" * 64,
        epoch=epoch, issued_at=issued, expires_at=expires, signed_at=SIGNED,
    )
    catalog_body = {"schema": CATALOG_SCHEMA, "catalog_version": 1, "entries": [{
        "issuer_id": ISSUER, "signing_key_id": key_id, "algorithm": "ed25519", "public_key": _encoded(public),
        "valid_from": "2026-09-21T07:00:00Z", "valid_until": "2026-09-21T10:00:00Z", "revocation_status": "active",
    }]}
    catalog_digest = catalog_digest_for(catalog_body)
    catalog_path = tmp_path / f"catalog-{epoch}.json"
    catalog_path.write_text(json.dumps({**catalog_body, "catalog_digest": catalog_digest}), encoding="utf-8")
    catalog = ReadOnlyTrustedIssuerCatalog.load(catalog_path, expected_catalog_version=1, expected_catalog_digest=catalog_digest)
    authenticated = RootIssuerProvenanceVerifier(trust_store=catalog, signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier()).verify(
        issuance.principal, issuance.provenance, current_time=SIGNED,
    )
    return issuance.principal, authenticated, catalog


def _registry(tmp_path: Path, principal: CausalResourcePrincipal, *, entries: list[dict[str, object]] | None = None,
              generated: str = "2026-09-21T08:00:00Z", valid_until: str = "2026-09-21T08:45:00Z",
              version: int = 1, expected_version: int | None = None, expected_digest: str | None = None) -> ReadOnlyPrincipalRevocationRegistry:
    body = {"schema": REGISTRY_SCHEMA, "registry_version": version, "generated_at": generated,
            "valid_until": valid_until, "revoked_principals": entries or []}
    digest = registry_digest_for(body)
    path = tmp_path / f"revocations-{len(list(tmp_path.iterdir()))}.json"
    path.write_text(json.dumps({**body, "registry_digest": digest}), encoding="utf-8")
    return ReadOnlyPrincipalRevocationRegistry.load(path, expected_registry_version=expected_version or version,
                                                     expected_registry_digest=expected_digest or digest)


def _entry(principal: CausalResourcePrincipal, *, revoked_at: str = "2026-09-21T08:20:00Z", **changes: object) -> dict[str, object]:
    result: dict[str, object] = {"principal_id": principal.principal_id, "principal_binding_digest": principal.binding_digest,
                                 "issuer_id": principal.issuer_id, "epoch": principal.epoch, "revoked_at": revoked_at}
    result.update(changes)
    return result


def _fails(code: str, action: Callable[[], object]) -> None:
    with pytest.raises(PrincipalCurrentnessError, match=f"^{code}$"):
        action()


def test_real_ed25519_authenticated_root_fresh_registry_returns_currentness_evidence(tmp_path: Path) -> None:
    principal, authenticated, _ = _authenticated(tmp_path)
    registry = _registry(tmp_path, principal)
    evidence = PrincipalCurrentnessVerifier().verify(principal, authenticated, registry, current_time=NOW)
    assert isinstance(evidence, CurrentAuthenticatedRootPrincipalEvidence)
    assert (evidence.principal_id, evidence.principal_binding_digest, evidence.issuer_id, evidence.epoch) == (
        principal.principal_id, principal.binding_digest, principal.issuer_id, principal.epoch)
    assert evidence.provenance_digest == authenticated.provenance_digest
    assert evidence.revocation_registry_digest == registry.registry_digest
    with pytest.raises(FrozenInstanceError):
        evidence.checked_at = SIGNED  # type: ignore[misc]


def test_effective_and_future_revocation_boundary(tmp_path: Path) -> None:
    principal, authenticated, catalog = _authenticated(tmp_path)
    future = _registry(tmp_path, principal, entries=[_entry(principal, revoked_at="2026-09-21T08:31:00Z")])
    PrincipalCurrentnessVerifier().verify(principal, authenticated, future, current_time=NOW)
    _fails("principal_revoked", lambda: PrincipalCurrentnessVerifier().verify(principal, authenticated, future, current_time="2026-09-21T08:31:00Z"))
    effective = _registry(tmp_path, principal, entries=[_entry(principal)])
    _fails("principal_revoked", lambda: PrincipalCurrentnessVerifier().verify(principal, authenticated, effective, current_time=NOW))
    trusted = catalog.lookup(issuer_id=authenticated.issuer_id, signing_key_id=authenticated.signing_key_id, algorithm=authenticated.algorithm)
    assert trusted is not None and trusted.revocation_status == "active"


def test_principal_time_and_registry_time_fail_independently(tmp_path: Path) -> None:
    principal, authenticated, _ = _authenticated(tmp_path)
    fresh = _registry(tmp_path, principal)
    _fails("principal_expired", lambda: PrincipalCurrentnessVerifier().verify(principal, authenticated, fresh, current_time=EXPIRES))
    _fails("principal_not_yet_valid", lambda: PrincipalCurrentnessVerifier().verify(principal, authenticated, fresh, current_time="2026-09-21T07:59:59Z"))
    stale = _registry(tmp_path, principal, valid_until=NOW)
    _fails("registry_stale", lambda: PrincipalCurrentnessVerifier().verify(principal, authenticated, stale, current_time=NOW))
    not_yet = _registry(tmp_path, principal, generated="2026-09-21T08:31:00Z")
    _fails("registry_not_yet_valid", lambda: PrincipalCurrentnessVerifier().verify(principal, authenticated, not_yet, current_time=NOW))


def test_registry_digest_version_schema_and_duplicate_resistance(tmp_path: Path) -> None:
    principal, _, _ = _authenticated(tmp_path)
    body = {"schema": REGISTRY_SCHEMA, "registry_version": 1, "generated_at": ISSUED, "valid_until": EXPIRES,
            "revoked_principals": [_entry(principal), _entry(principal)]}
    digest = registry_digest_for(body)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({**body, "registry_digest": digest}), encoding="utf-8")
    _fails("duplicate_principal_revocation", lambda: ReadOnlyPrincipalRevocationRegistry.load(path, expected_registry_version=1, expected_registry_digest=digest))
    body["revoked_principals"] = []
    digest = registry_digest_for(body)
    path.write_text(json.dumps({**body, "registry_digest": "sha256:" + "0" * 64}), encoding="utf-8")
    _fails("registry_digest_mismatch", lambda: ReadOnlyPrincipalRevocationRegistry.load(path, expected_registry_version=1, expected_registry_digest=digest))
    path.write_text(json.dumps({**body, "registry_digest": digest}), encoding="utf-8")
    _fails("unexpected_registry_digest", lambda: ReadOnlyPrincipalRevocationRegistry.load(path, expected_registry_version=1, expected_registry_digest="sha256:" + "3" * 64))
    _fails("unexpected_registry_version", lambda: ReadOnlyPrincipalRevocationRegistry.load(path, expected_registry_version=2, expected_registry_digest=digest))


@pytest.mark.parametrize(("change", "code"), [
    ({"principal_id": "bad"}, "invalid_revoked_principal_id"),
    ({"principal_binding_digest": "bad"}, "invalid_revoked_principal_binding_digest"),
    ({"issuer_id": "*"}, "invalid_revoked_issuer_id"), ({"epoch": 0}, "invalid_revoked_epoch"),
    ({"revoked_at": "tomorrow"}, "invalid_revoked_at"),
])
def test_malformed_revocation_identity_fails(tmp_path: Path, change: dict[str, object], code: str) -> None:
    principal, _, _ = _authenticated(tmp_path)
    body = {"schema": REGISTRY_SCHEMA, "registry_version": 1, "generated_at": ISSUED, "valid_until": EXPIRES,
            "revoked_principals": [_entry(principal, **change)]}  # type: ignore[arg-type]
    digest = registry_digest_for(body); path = tmp_path / "bad-registry.json"
    path.write_text(json.dumps({**body, "registry_digest": digest}), encoding="utf-8")
    _fails(code, lambda: ReadOnlyPrincipalRevocationRegistry.load(path, expected_registry_version=1, expected_registry_digest=digest))


@pytest.mark.parametrize(("change", "code"), [
    ({"principal_binding_digest": "sha256:" + "3" * 64}, "revocation_principal_binding_mismatch"),
    ({"issuer_id": "different-issuer"}, "revocation_issuer_mismatch"), ({"epoch": 2}, "revocation_epoch_mismatch"),
])
def test_matching_principal_id_cannot_evade_by_substitution(tmp_path: Path, change: dict[str, object], code: str) -> None:
    principal, authenticated, _ = _authenticated(tmp_path)
    registry = _registry(tmp_path, principal, entries=[_entry(principal, **change)])  # type: ignore[arg-type]
    _fails(code, lambda: PrincipalCurrentnessVerifier().verify(principal, authenticated, registry, current_time=NOW))


def test_authenticated_evidence_cross_binding_and_caller_smuggling_fail(tmp_path: Path) -> None:
    principal, authenticated, _ = _authenticated(tmp_path)
    registry = _registry(tmp_path, principal)
    for field, code in (("principal_id", "authenticated_principal_id_mismatch"),
                        ("principal_binding_digest", "authenticated_principal_binding_mismatch"),
                        ("issuer_id", "authenticated_issuer_mismatch")):
        altered = replace(authenticated, **{field: ("crp-sha256:" if field == "principal_id" else "sha256:") + "4" * 64 if field != "issuer_id" else "different-issuer"})
        def verify_altered(evidence: AuthenticatedRootPrincipalEvidence = altered) -> object:
            return PrincipalCurrentnessVerifier().verify(principal, evidence, registry, current_time=NOW)
        _fails(code, verify_altered)
    assert not hasattr(CurrentAuthenticatedRootPrincipalEvidence, "from_mapping")
    _fails("currentness_evidence_verifier_required", lambda: CurrentAuthenticatedRootPrincipalEvidence(
        _token=object(), principal_id=principal.principal_id, principal_binding_digest=principal.binding_digest,
        issuer_id=principal.issuer_id, epoch=1, provenance_digest=authenticated.provenance_digest,
        revocation_registry_version=1, revocation_registry_digest=registry.registry_digest,
        registry_generated_at=registry.generated_at, registry_valid_until=registry.valid_until, checked_at=NOW))


def test_stale_absence_and_structural_non_authority(tmp_path: Path) -> None:
    principal, authenticated, _ = _authenticated(tmp_path)
    stale = _registry(tmp_path, principal, valid_until=NOW)
    _fails("registry_stale", lambda: PrincipalCurrentnessVerifier().verify(principal, authenticated, stale, current_time=NOW))
    assert {f.name for f in fields(CurrentAuthenticatedRootPrincipalEvidence)}.isdisjoint(
        {"allocation", "entitlement", "admission", "effect_grant", "quota", "signing_key_id", "public_key", "trust_store_path"})
    source = Path(currentness.__file__).read_text(encoding="utf-8"); tree = ast.parse(source)
    public_classes = {node.name.lower() for node in tree.body if isinstance(node, ast.ClassDef)}
    assert all(not any(word in name for word in ("allocator", "entitlement", "admission", "signer", "issuer", "writer", "administrator")) for name in public_classes)
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert calls.isdisjoint({"allocate", "entitle", "admit", "grant", "sign", "mint", "issue", "write_text", "request", "post", "put"})
    registry_fields = {"schema", "registry_version", "generated_at", "valid_until", "revoked_principals", "registry_digest"}
    assert registry_fields.isdisjoint({"allocation", "entitlement", "effect", "permission", "resource_amount"})
