"""Real-cryptography tests for the optional Ed25519 verification backend."""
from __future__ import annotations

import ast
import base64
import hashlib
import importlib
import inspect
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentientos.causal_resource_principal import RootPrincipalIssuer, VerifiedOperatorSponsorship
from sentientos.causal_resource_principal_authentication import (
    AuthenticatedRootPrincipalEvidence,
    ED25519_ALGORITHM,
    RootIssuerProvenanceVerifier,
    RootPrincipalIssuerProvenance,
    TrustedRootIssuerKey,
    canonical_root_provenance_payload,
)
import sentientos.causal_resource_principal_ed25519 as backend
from sentientos.causal_resource_principal_ed25519 import (
    CryptographyEd25519RootIssuerSignatureVerifier,
    Ed25519VerificationBackendUnavailable,
)

pytestmark = pytest.mark.no_legacy_skip

# RFC 8032 section 7.1, test vector 1 (empty message).
RFC_PUBLIC = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
RFC_SIGNATURE = (
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)


def encoded(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def verifier() -> CryptographyEd25519RootIssuerSignatureVerifier:
    return CryptographyEd25519RootIssuerSignatureVerifier()


def rfc_material() -> tuple[str, str]:
    return encoded(bytes.fromhex(RFC_PUBLIC)), encoded(bytes.fromhex(RFC_SIGNATURE))


def test_rfc8032_known_valid_ed25519_vector_verifies() -> None:
    public_key, signature = rfc_material()
    assert verifier().verify(algorithm="ed25519", public_key=public_key, payload=b"", signature=signature)


def test_changed_payload_and_signature_fail_without_backend_unavailability() -> None:
    public_key, signature = rfc_material()
    assert verifier().verify(algorithm="ed25519", public_key=public_key, payload=b"changed", signature=signature) is False
    changed = bytearray(bytes.fromhex(RFC_SIGNATURE)); changed[0] ^= 1
    assert verifier().verify(algorithm="ed25519", public_key=public_key, payload=b"", signature=encoded(bytes(changed))) is False


def test_changed_public_key_and_unsupported_algorithms_fail() -> None:
    public_key, signature = rfc_material()
    changed = bytearray(bytes.fromhex(RFC_PUBLIC)); changed[0] ^= 1
    assert verifier().verify(algorithm="ed25519", public_key=encoded(bytes(changed)), payload=b"", signature=signature) is False
    for algorithm in ("auto", "Ed25519", "ED25519", "ssh-ed25519"):
        assert verifier().verify(algorithm=algorithm, public_key=public_key, payload=b"", signature=signature) is False


@pytest.mark.parametrize("field", ["public_key", "signature"])
@pytest.mark.parametrize("contaminant", ["=", "+", "/", " ", "\t", "\n"])
def test_noncanonical_base64url_material_fails_closed(field: str, contaminant: str) -> None:
    public_key, signature = rfc_material()
    values = {"public_key": public_key, "signature": signature}
    values[field] += contaminant
    assert verifier().verify(algorithm="ed25519", payload=b"", **values) is False


@pytest.mark.parametrize(
    ("public_key", "signature"),
    [("!", rfc_material()[1]), (rfc_material()[0], "!"), (encoded(b"x" * 31), rfc_material()[1]),
     (rfc_material()[0], encoded(b"x" * 63))],
)
def test_malformed_or_wrong_length_material_is_verification_failure(public_key: str, signature: str) -> None:
    assert verifier().verify(algorithm="ed25519", public_key=public_key, payload=b"", signature=signature) is False


def test_backend_unavailability_is_bounded_and_distinct() -> None:
    public_key, signature = rfc_material()

    def unavailable() -> tuple[object, object]:
        raise Ed25519VerificationBackendUnavailable("ed25519_verification_backend_unavailable")

    unavailable_verifier = CryptographyEd25519RootIssuerSignatureVerifier(backend_loader=unavailable)
    with pytest.raises(Ed25519VerificationBackendUnavailable, match="^ed25519_verification_backend_unavailable$"):
        unavailable_verifier.verify(algorithm="ed25519", public_key=public_key, payload=b"", signature=signature)
    assert verifier().verify(algorithm="ed25519", public_key=public_key, payload=b"wrong", signature=signature) is False
    assert verifier().verify(algorithm="ed25519", public_key="bad", payload=b"", signature=signature) is False


def test_dependency_loading_seam_classifies_genuine_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", missing)
    with pytest.raises(Ed25519VerificationBackendUnavailable, match="^ed25519_verification_backend_unavailable$"):
        backend._load_cryptography()


def test_backend_surface_has_no_signing_secret_custody_or_fallback() -> None:
    instance = verifier()
    assert not hasattr(instance, "sign")
    source = Path(backend.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint({"nacl.signing", "keyring", "Ed25519PrivateKey", "SshStrategicSigner", "HmacTestStrategicSigner"})
    called = {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
              for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))}
    assert called.isdisjoint({"sign", "generate", "getenv", "environ"})


def test_core_authentication_import_surface_remains_crypto_independent() -> None:
    core = importlib.import_module("sentientos.causal_resource_principal_authentication")
    source = inspect.getsource(core)
    assert "cryptography" not in source
    assert "causal_resource_principal_ed25519" not in source


class Sponsor:
    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        return VerifiedOperatorSponsorship("sha256:" + "1" * 64)


class TrustStore:
    def __init__(self, key: TrustedRootIssuerKey) -> None:
        self.key = key

    def lookup(self, *, issuer_id: str, signing_key_id: str, algorithm: str) -> TrustedRootIssuerKey | None:
        return self.key


def test_root_issuer_provenance_verifier_succeeds_with_real_ed25519() -> None:
    principal = RootPrincipalIssuer(issuer_id="resource-principal-issuer", sponsorship_verifier=Sponsor()).mint_root(
        sponsorship_evidence={}, subject_binding_digest="sha256:" + "2" * 64, epoch=1,
        issued_at="2026-09-21T08:00:00Z", expires_at="2026-09-21T09:00:00Z")
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public_raw = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = "ed25519-sha256:" + hashlib.sha256(public_raw).hexdigest()
    signed_at = "2026-09-21T08:10:00Z"
    payload = canonical_root_provenance_payload(
        principal_id=principal.principal_id, principal_binding_digest=principal.binding_digest,
        issuer_id=principal.issuer_id, signing_key_id=key_id, algorithm=ED25519_ALGORITHM, signed_at=signed_at)
    provenance = RootPrincipalIssuerProvenance.create(
        principal_id=principal.principal_id, principal_binding_digest=principal.binding_digest,
        issuer_id=principal.issuer_id, signing_key_id=key_id, algorithm=ED25519_ALGORITHM,
        signed_at=signed_at, signature=encoded(private_key.sign(payload)))
    trusted = TrustedRootIssuerKey(
        issuer_id=principal.issuer_id, signing_key_id=key_id, algorithm=ED25519_ALGORITHM,
        public_key=encoded(public_raw), valid_from="2026-09-21T07:00:00Z",
        valid_until="2026-09-21T10:00:00Z", revocation_status="active")
    result = RootIssuerProvenanceVerifier(
        trust_store=TrustStore(trusted), signature_verifier=verifier()).verify(
            principal, provenance, current_time="2026-09-21T08:30:00Z")
    assert result == AuthenticatedRootPrincipalEvidence(
        principal_id=principal.principal_id, principal_binding_digest=principal.binding_digest,
        provenance_digest=provenance.provenance_digest, issuer_id=principal.issuer_id,
        signing_key_id=key_id, algorithm=ED25519_ALGORITHM, signed_at=signed_at)
