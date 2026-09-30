from __future__ import annotations

import ast
import base64
from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import sentientos.causal_resource_principal_provenance_signer as signer_module
from sentientos.causal_resource_principal import (
    CausalResourcePrincipal,
    RootPrincipalIssuer,
    VerifiedOperatorSponsorship,
)
from sentientos.causal_resource_principal_authentication import (
    AuthenticatedRootPrincipalEvidence,
    RootIssuerProvenanceError,
    RootIssuerProvenanceVerifier,
    RootPrincipalIssuerProvenance,
)
from sentientos.causal_resource_principal_ed25519 import (
    CryptographyEd25519RootIssuerSignatureVerifier,
)
from sentientos.causal_resource_principal_provenance_signer import (
    CryptographyEd25519RootIssuerProvenanceSigner,
    RootIssuerProvenanceSigningError,
)
from sentientos.causal_resource_principal_signer_custody import (
    RootIssuerPrivateKeyCustody,
    RootIssuerPrivateKeyBackend,
    RootIssuerPrivateKeyCustodyError,
    RootIssuerSigningKeyReference,
)
from sentientos.causal_resource_principal_trust_catalog import (
    CATALOG_SCHEMA,
    ReadOnlyTrustedIssuerCatalog,
    catalog_digest_for,
)

pytestmark = pytest.mark.no_legacy_skip
SEED = bytes(range(32))
ISSUER = "resource-principal-issuer"
SIGNED_AT = "2026-09-21T08:10:00Z"


class Sponsor:
    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        return VerifiedOperatorSponsorship("sha256:" + "1" * 64)


class Backend:
    def __init__(self, material: bytes | None = None) -> None:
        raw = material if material is not None else SEED
        self.encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
        self.calls = 0
        self.returned: list[bytearray] = []

    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        self.calls += 1
        result = bytearray(self.encoded)
        self.returned.append(result)
        return result


class UnavailableBackend:
    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        raise RootIssuerPrivateKeyCustodyError("signer_key_custody_secret_missing")


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def public_raw(seed: bytes = SEED) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()


def key_id(seed: bytes = SEED) -> str:
    return "ed25519-sha256:" + hashlib.sha256(public_raw(seed)).hexdigest()


def reference(**changes: str) -> RootIssuerSigningKeyReference:
    values = {
        "issuer_id": ISSUER,
        "signing_key_id": key_id(),
        "algorithm": "ed25519",
        "key_reference": "operator-key-v1",
    }
    values.update(changes)
    return RootIssuerSigningKeyReference(**values)


def principal(*, issuer: str = ISSUER, epoch: int = 1) -> CausalResourcePrincipal:
    return RootPrincipalIssuer(issuer_id=issuer, sponsorship_verifier=Sponsor()).mint_root(
        sponsorship_evidence={},
        subject_binding_digest="sha256:" + "2" * 64,
        epoch=epoch,
        issued_at="2026-09-21T08:00:00Z",
        expires_at="2026-09-21T09:00:00Z",
    )


def signer(
    backend: object | None = None,
    *,
    signer_reference: RootIssuerSigningKeyReference | None = None,
    custody_reference: RootIssuerSigningKeyReference | None = None,
    loader: Callable[[], Any] | None = None,
) -> CryptographyEd25519RootIssuerProvenanceSigner:
    signer_ref = signer_reference or reference()
    custody_ref = custody_reference or signer_ref
    custody = RootIssuerPrivateKeyCustody(
        reference=custody_ref,
        backend=cast(RootIssuerPrivateKeyBackend, backend or Backend()),
    )
    if loader is None:
        return CryptographyEd25519RootIssuerProvenanceSigner(
            reference=signer_ref, custody=custody
        )
    return CryptographyEd25519RootIssuerProvenanceSigner(
        reference=signer_ref, custody=custody, private_key_type_loader=loader
    )


def catalog(tmp_path: Path) -> ReadOnlyTrustedIssuerCatalog:
    body = {
        "schema": CATALOG_SCHEMA,
        "catalog_version": 1,
        "entries": [{
            "issuer_id": ISSUER,
            "signing_key_id": key_id(),
            "algorithm": "ed25519",
            "public_key": encoded(public_raw()),
            "valid_from": "2026-09-21T07:00:00Z",
            "valid_until": "2026-09-21T10:00:00Z",
            "revocation_status": "active",
        }],
    }
    digest = catalog_digest_for(body)
    value = {**body, "catalog_digest": digest}
    path = tmp_path / "trusted-root-issuers.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return ReadOnlyTrustedIssuerCatalog.load(
        path, expected_catalog_version=1, expected_catalog_digest=digest
    )


def verifier(tmp_path: Path) -> RootIssuerProvenanceVerifier:
    return RootIssuerProvenanceVerifier(
        trust_store=catalog(tmp_path),
        signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier(),
    )


def test_real_custody_signer_catalog_and_verifier_chain(tmp_path: Path) -> None:
    backend = Backend()
    root = principal()
    provenance = signer(backend).authenticate_root_provenance(root, signed_at=SIGNED_AT)
    evidence = verifier(tmp_path).verify(
        root, provenance, current_time="2026-09-21T08:30:00Z"
    )
    assert evidence == AuthenticatedRootPrincipalEvidence(
        principal_id=root.principal_id,
        principal_binding_digest=root.binding_digest,
        provenance_digest=provenance.provenance_digest,
        issuer_id=ISSUER,
        signing_key_id=key_id(),
        algorithm="ed25519",
        signed_at=SIGNED_AT,
    )
    assert backend.calls == 1
    assert backend.returned == [bytearray(len(backend.encoded))]


@pytest.mark.parametrize(
    ("root", "signer_ref", "message"),
    [
        (principal(issuer="other-issuer"), reference(), "root_principal_not_signable"),
        (principal(), reference(algorithm="hmac-test"), "root_provenance_algorithm_unsupported"),
    ],
)
def test_issuer_and_algorithm_mismatch_fail_before_custody(
    root: CausalResourcePrincipal,
    signer_ref: RootIssuerSigningKeyReference,
    message: str,
) -> None:
    backend = Backend()
    with pytest.raises(RootIssuerProvenanceSigningError, match=f"^{message}$"):
        signer(backend, signer_reference=signer_ref).authenticate_root_provenance(root, signed_at=SIGNED_AT)
    assert backend.calls == 0


def test_signer_and_custody_key_binding_mismatch_fails_before_secret_read() -> None:
    backend = Backend()
    other = "ed25519-sha256:" + "0" * 64
    with pytest.raises(RootIssuerProvenanceSigningError, match="^signer_key_custody_binding_mismatch$"):
        signer(backend, custody_reference=reference(signing_key_id=other)).authenticate_root_provenance(
            principal(), signed_at=SIGNED_AT
        )
    assert backend.calls == 0


@pytest.mark.parametrize("signed_at", ["2026-09-21T08:10:00+00:00", "2026-09-21T08:10:00.000Z", "bad"])
def test_noncanonical_signed_at_is_rejected_without_custody(signed_at: str) -> None:
    backend = Backend()
    with pytest.raises(RootIssuerProvenanceSigningError, match="^root_principal_not_signable$"):
        signer(backend).authenticate_root_provenance(principal(), signed_at=signed_at)
    assert backend.calls == 0


@pytest.mark.parametrize("signed_at", ["2026-09-21T07:59:59Z", "2026-09-21T09:00:00Z"])
def test_not_current_principal_is_rejected_without_custody(signed_at: str) -> None:
    backend = Backend()
    with pytest.raises(RootIssuerProvenanceSigningError, match="^root_principal_not_signable$"):
        signer(backend).authenticate_root_provenance(principal(), signed_at=signed_at)
    assert backend.calls == 0


def test_only_exact_canonical_principal_is_accepted() -> None:
    root = principal()
    with pytest.raises(RootIssuerProvenanceSigningError, match="^root_principal_not_canonical$"):
        signer().authenticate_root_provenance(root.to_dict(), signed_at=SIGNED_AT)  # type: ignore[arg-type]
    malformed = replace(root, binding_digest="sha256:" + "0" * 64)
    with pytest.raises(RootIssuerProvenanceSigningError, match="^root_principal_not_signable$"):
        signer().authenticate_root_provenance(malformed, signed_at=SIGNED_AT)


def test_custody_unavailable_and_malformed_material_are_bounded() -> None:
    with pytest.raises(RootIssuerProvenanceSigningError, match="^signer_key_custody_secret_missing$"):
        signer(UnavailableBackend()).authenticate_root_provenance(principal(), signed_at=SIGNED_AT)
    malformed = Backend(b"short")
    with pytest.raises(RootIssuerProvenanceSigningError, match="^signer_key_custody_material_invalid$"):
        signer(malformed).authenticate_root_provenance(principal(), signed_at=SIGNED_AT)
    assert malformed.returned == [bytearray(len(malformed.encoded))]
    wrong_key = Backend(bytes(reversed(range(32))))
    with pytest.raises(RootIssuerProvenanceSigningError, match="^signer_key_custody_key_id_mismatch$"):
        signer(wrong_key).authenticate_root_provenance(principal(), signed_at=SIGNED_AT)


def test_backend_unavailable_and_signing_failure_are_bounded_and_redacted() -> None:
    def unavailable() -> Any:
        raise RootIssuerProvenanceSigningError("root_provenance_signing_backend_unavailable")

    with pytest.raises(RootIssuerProvenanceSigningError, match="^root_provenance_signing_backend_unavailable$"):
        signer(loader=unavailable).authenticate_root_provenance(principal(), signed_at=SIGNED_AT)

    class BrokenKey:
        @classmethod
        def from_private_bytes(cls, value: bytes) -> Any:
            raise RuntimeError("secret detail")

    with pytest.raises(RootIssuerProvenanceSigningError, match="^root_provenance_signing_failed$") as caught:
        signer(loader=lambda: BrokenKey).authenticate_root_provenance(principal(), signed_at=SIGNED_AT)
    assert "secret detail" not in str(caught.value)


def test_every_signing_call_reacquires_custody() -> None:
    backend = Backend()
    instance = signer(backend)
    first = instance.authenticate_root_provenance(principal(), signed_at=SIGNED_AT)
    second = instance.authenticate_root_provenance(principal(), signed_at="2026-09-21T08:11:00Z")
    assert backend.calls == 2
    assert first.signature != second.signature
    assert all(item == bytearray(len(backend.encoded)) for item in backend.returned)
    assert SEED not in instance.__dict__.values()


@pytest.mark.parametrize("field", ["issuer_id", "signing_key_id", "signed_at", "signature"])
def test_signed_envelope_substitution_and_signature_mutation_fail_verification(tmp_path: Path, field: str) -> None:
    root = principal()
    provenance = signer().authenticate_root_provenance(root, signed_at=SIGNED_AT)
    changes = {
        "issuer_id": "other-issuer",
        "signing_key_id": "ed25519-sha256:" + "0" * 64,
        "signed_at": "2026-09-21T08:11:00Z",
        "signature": ("A" if provenance.signature[0] != "A" else "B") + provenance.signature[1:],
    }
    altered = RootPrincipalIssuerProvenance.create(
        principal_id=provenance.principal_id,
        principal_binding_digest=provenance.principal_binding_digest,
        issuer_id=changes[field] if field == "issuer_id" else provenance.issuer_id,
        signing_key_id=changes[field] if field == "signing_key_id" else provenance.signing_key_id,
        algorithm=provenance.algorithm,
        signed_at=changes[field] if field == "signed_at" else provenance.signed_at,
        signature=changes[field] if field == "signature" else provenance.signature,
    )
    with pytest.raises(RootIssuerProvenanceError):
        verifier(tmp_path).verify(root, altered, current_time="2026-09-21T08:30:00Z")


def test_principal_substitution_after_signing_fails_verification(tmp_path: Path) -> None:
    provenance = signer().authenticate_root_provenance(principal(), signed_at=SIGNED_AT)
    with pytest.raises(RootIssuerProvenanceError, match="^principal_binding_mismatch$"):
        verifier(tmp_path).verify(
            principal(epoch=2), provenance, current_time="2026-09-21T08:30:00Z"
        )


def test_signer_surface_is_purpose_scoped_and_non_authoritative() -> None:
    public_methods = {
        name for name, value in inspect.getmembers(
            CryptographyEd25519RootIssuerProvenanceSigner, inspect.isfunction
        ) if not name.startswith("_")
    }
    assert public_methods == {"authenticate_root_provenance"}
    source = Path(signer_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert calls.isdisjoint({
        "mint_root", "verify_sponsorship", "enroll", "rotate", "revoke", "allocate",
        "entitle", "admit", "grant", "set_status", "set_password", "delete_password",
    })
    assert "GenesisForge" not in source
    assert "ControlPlaneKernel" not in source
    assert "nacl.signing" not in source
    assert all(not hasattr(signer(), name) for name in (
        "sign", "sign_message", "sign_digest", "sign_arbitrary_payload", "mint_root",
        "allocate", "entitle", "admit", "grant", "enroll", "rotate", "revoke",
    ))
