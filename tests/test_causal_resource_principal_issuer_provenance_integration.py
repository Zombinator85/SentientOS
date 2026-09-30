from __future__ import annotations

import ast
import base64
from dataclasses import FrozenInstanceError, asdict, fields, replace
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import sentientos.causal_resource_principal as principal_module
from sentientos.causal_resource_principal import (
    CausalResourcePrincipal,
    CausalResourcePrincipalError,
    RootPrincipalIssuance,
    RootPrincipalIssuer,
    VerifiedOperatorSponsorship,
)
from sentientos.causal_resource_principal_authentication import (
    AuthenticatedRootPrincipalEvidence,
    RootIssuerProvenanceError,
    RootIssuerProvenanceSigner,
    RootIssuerProvenanceVerifier,
    RootPrincipalIssuerProvenance,
)
from sentientos.causal_resource_principal_ed25519 import CryptographyEd25519RootIssuerSignatureVerifier
from sentientos.causal_resource_principal_provenance_signer import CryptographyEd25519RootIssuerProvenanceSigner
from sentientos.causal_resource_principal_signer_custody import (
    RootIssuerPrivateKeyBackend,
    RootIssuerPrivateKeyCustody,
    RootIssuerSigningKeyReference,
)
from sentientos.causal_resource_principal_trust_catalog import (
    CATALOG_SCHEMA,
    ReadOnlyTrustedIssuerCatalog,
    catalog_digest_for,
)

pytestmark = pytest.mark.no_legacy_skip
ISSUER = "resource-principal-issuer"
SEED = bytes(range(32))
SPONSOR = "sha256:" + "1" * 64
SUBJECT = "sha256:" + "2" * 64
ISSUED_AT = "2026-09-21T08:00:00Z"
SIGNED_AT = "2026-09-21T08:10:00Z"
EXPIRES_AT = "2026-09-21T09:00:00Z"


class Sponsor:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.calls = 0

    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        self.calls += 1
        if self.reject:
            raise ValueError("rejected")
        return VerifiedOperatorSponsorship(SPONSOR)


class Backend:
    def __init__(self) -> None:
        self.calls = 0

    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        self.calls += 1
        return bytearray(base64.urlsafe_b64encode(SEED).rstrip(b"="))


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def public_key() -> bytes:
    return Ed25519PrivateKey.from_private_bytes(SEED).public_key().public_bytes_raw()


def key_id() -> str:
    return "ed25519-sha256:" + hashlib.sha256(public_key()).hexdigest()


def production_signer(backend: Backend | None = None) -> CryptographyEd25519RootIssuerProvenanceSigner:
    reference = RootIssuerSigningKeyReference(
        issuer_id=ISSUER, signing_key_id=key_id(), algorithm="ed25519", key_reference="operator-key-v1"
    )
    custody = RootIssuerPrivateKeyCustody(
        reference=reference, backend=cast(RootIssuerPrivateKeyBackend, backend or Backend())
    )
    return CryptographyEd25519RootIssuerProvenanceSigner(reference=reference, custody=custody)


def issuer(sponsor: Sponsor | None = None, signer: RootIssuerProvenanceSigner | None = None,
           *, issuer_id: str = ISSUER) -> RootPrincipalIssuer:
    return RootPrincipalIssuer(
        issuer_id=issuer_id, sponsorship_verifier=sponsor or Sponsor(), provenance_signer=signer
    )


def arguments(**changes: object) -> dict[str, object]:
    result: dict[str, object] = {
        "sponsorship_evidence": {"operator": "signed"}, "subject_binding_digest": SUBJECT,
        "epoch": 1, "issued_at": ISSUED_AT, "expires_at": EXPIRES_AT,
    }
    result.update(changes)
    return result


def paired(instance: RootPrincipalIssuer, **changes: object) -> RootPrincipalIssuance:
    return instance.mint_root_with_provenance(**arguments(**changes), signed_at=SIGNED_AT)  # type: ignore[arg-type]


def verifier(tmp_path: Path) -> RootIssuerProvenanceVerifier:
    body = {
        "schema": CATALOG_SCHEMA, "catalog_version": 1,
        "entries": [{"issuer_id": ISSUER, "signing_key_id": key_id(), "algorithm": "ed25519",
                     "public_key": encoded(public_key()), "valid_from": "2026-09-21T07:00:00Z",
                     "valid_until": "2026-09-21T10:00:00Z", "revocation_status": "active"}],
    }
    digest = catalog_digest_for(body)
    path = tmp_path / "trusted-root-issuers.json"
    path.write_text(json.dumps({**body, "catalog_digest": digest}), encoding="utf-8")
    catalog = ReadOnlyTrustedIssuerCatalog.load(path, expected_catalog_version=1, expected_catalog_digest=digest)
    return RootIssuerProvenanceVerifier(
        trust_store=catalog, signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier()
    )


def test_real_operator_sponsorship_issuance_signing_and_independent_ed25519_verification(tmp_path: Path) -> None:
    sponsor = Sponsor()
    result = paired(issuer(sponsor, production_signer()))
    authenticated = verifier(tmp_path).verify(result.principal, result.provenance, current_time=SIGNED_AT)
    assert sponsor.calls == 1
    assert isinstance(authenticated, AuthenticatedRootPrincipalEvidence)
    assert authenticated.principal_id == result.principal.principal_id == result.provenance.principal_id
    assert authenticated.principal_binding_digest == result.principal.binding_digest == result.provenance.principal_binding_digest
    assert authenticated.issuer_id == result.principal.issuer_id == result.provenance.issuer_id


def test_canonical_only_mint_remains_signer_free_and_has_no_crypto_side_effect() -> None:
    sponsor = Sponsor()
    root = issuer(sponsor).mint_root(**arguments())  # type: ignore[arg-type]
    assert type(root) is CausalResourcePrincipal
    assert sponsor.calls == 1


def test_paired_result_is_immutable_exact_and_contains_no_authority_or_secrets() -> None:
    result = paired(issuer(signer=production_signer()))
    with pytest.raises(FrozenInstanceError):
        result.principal = result.principal  # type: ignore[misc]
    assert {field.name for field in fields(RootPrincipalIssuance)} == {"principal", "provenance"}
    serialized = json.dumps(asdict(result), sort_keys=True)
    forbidden = ("private_key", "raw_seed", "key_reference", '"verified"', "allocation", "entitlement",
                 "admission", "effect_grant", "operator_approval")
    assert all(word not in serialized.lower() for word in forbidden)


def test_missing_signer_fails_before_sponsorship_verification() -> None:
    sponsor = Sponsor()
    with pytest.raises(CausalResourcePrincipalError, match="^provenance_signer_required$"):
        paired(issuer(sponsor))
    assert sponsor.calls == 0


class RecordingSigner:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[CausalResourcePrincipal] = []
        self.failure = failure

    def authenticate_root_provenance(self, principal: CausalResourcePrincipal, *, signed_at: str) -> RootPrincipalIssuerProvenance:
        self.calls.append(principal)
        if self.failure is not None:
            raise self.failure
        return RootPrincipalIssuerProvenance.create(
            principal_id=principal.principal_id, principal_binding_digest=principal.binding_digest,
            issuer_id=principal.issuer_id, signing_key_id="ed25519-sha256:" + "3" * 64,
            algorithm="ed25519", signed_at=signed_at, signature=encoded(bytes(64)),
        )


def test_sponsorship_and_principal_construction_failures_never_call_signer() -> None:
    signer = RecordingSigner()
    with pytest.raises(CausalResourcePrincipalError, match="^operator_sponsorship_not_verified$"):
        paired(issuer(Sponsor(reject=True), signer))
    assert signer.calls == []
    with pytest.raises(CausalResourcePrincipalError, match="^invalid_subject_binding_digest$"):
        paired(issuer(signer=signer), subject_binding_digest="bad")
    assert signer.calls == []


def test_signer_receives_the_exact_returned_object_once_and_is_not_retried() -> None:
    signer = RecordingSigner()
    result = paired(issuer(signer=signer))
    assert len(signer.calls) == 1 and signer.calls[0] is result.principal
    failing = RecordingSigner(failure=RuntimeError("signing failed"))
    with pytest.raises(RuntimeError, match="signing failed"):
        paired(issuer(signer=failing))
    assert len(failing.calls) == 1


def test_signer_output_issuer_or_identity_mismatch_fails_closed() -> None:
    class SubstitutingSigner(RecordingSigner):
        def authenticate_root_provenance(self, principal: CausalResourcePrincipal, *, signed_at: str) -> RootPrincipalIssuerProvenance:
            claim = super().authenticate_root_provenance(principal, signed_at=signed_at)
            return replace(claim, principal_id="crp-sha256:" + "4" * 64)
    with pytest.raises(CausalResourcePrincipalError, match="^provenance_principal_binding_mismatch$"):
        paired(issuer(signer=SubstitutingSigner()))
    with pytest.raises(Exception):
        paired(issuer(signer=production_signer(), issuer_id="different-issuer"))


@pytest.mark.parametrize("signed_at", ["bad", "2026-09-21T08:10:00+00:00", "2026-09-21T07:59:59Z", EXPIRES_AT])
def test_invalid_noncanonical_or_out_of_window_signing_time_fails_closed(signed_at: str) -> None:
    with pytest.raises(Exception):
        issuer(signer=production_signer()).mint_root_with_provenance(**arguments(), signed_at=signed_at)  # type: ignore[arg-type]


def test_provenance_and_principal_substitution_fail_independent_verification(tmp_path: Path) -> None:
    first = paired(issuer(signer=production_signer()))
    second = issuer(signer=production_signer()).mint_root_with_provenance(
        **arguments(epoch=2), signed_at=SIGNED_AT  # type: ignore[arg-type]
    )
    with pytest.raises(RootIssuerProvenanceError):
        verifier(tmp_path).verify(first.principal, second.provenance, current_time=SIGNED_AT)
    with pytest.raises(RootIssuerProvenanceError):
        verifier(tmp_path).verify(second.principal, first.provenance, current_time=SIGNED_AT)


def test_integration_has_no_authority_trust_mutation_or_consumer_composition() -> None:
    source = Path(principal_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    public_types = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert public_types.isdisjoint({"ResourceAllocation", "ResourceEntitlement", "ResourceScheduler",
                                    "AdmissionGrant", "EffectGrant", "TrustCatalogWriter", "KeyAdministrator"})
    calls = {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
             for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))}
    assert calls.isdisjoint({"allocate", "entitle", "admit", "grant", "enroll", "rotate", "revoke", "set_status"})
    assert "GenesisForge" not in source and "ControlPlaneKernel" not in source
