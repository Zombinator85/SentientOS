"""Tests for root issuer provenance using a deterministic fake backend.

TEST ONLY.  NOT ED25519.  NOT PRODUCTION SECURITY.
"""
from __future__ import annotations

import base64
from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import inspect
from pathlib import Path
from typing import Mapping

import pytest

from sentientos.causal_resource_principal import (
    CausalResourcePrincipal,
    RootPrincipalIssuer,
    VerifiedOperatorSponsorship,
)
import sentientos.causal_resource_principal_authentication as authentication
from sentientos.causal_resource_principal_authentication import (
    AuthenticatedRootPrincipalEvidence,
    ED25519_ALGORITHM,
    PROVENANCE_SCHEMA,
    RootIssuerProvenanceError,
    RootIssuerProvenanceSigner,
    RootIssuerProvenanceVerifier,
    RootIssuerTrustStore,
    RootPrincipalIssuerProvenance,
    SIGNING_DOMAIN,
    TrustedRootIssuerKey,
    canonical_root_provenance_payload,
)

pytestmark = pytest.mark.no_legacy_skip

ISSUED = "2026-09-21T08:00:00Z"
SIGNED = "2026-09-21T08:10:00Z"
CURRENT = "2026-09-21T08:30:00Z"
EXPIRES = "2026-09-21T09:00:00Z"
PUBLIC_RAW = bytes(range(32))
PUBLIC_KEY = base64.urlsafe_b64encode(PUBLIC_RAW).decode().rstrip("=")
KEY_ID = "ed25519-sha256:" + hashlib.sha256(PUBLIC_RAW).hexdigest()


class Sponsor:
    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        return VerifiedOperatorSponsorship("sha256:" + "1" * 64)


def mint(*, issuer_id: str = "resource-principal-issuer", epoch: int = 1) -> CausalResourcePrincipal:
    return RootPrincipalIssuer(issuer_id=issuer_id, sponsorship_verifier=Sponsor()).mint_root(
        sponsorship_evidence={"operator": "signed"},
        subject_binding_digest="sha256:" + "2" * 64,
        epoch=epoch,
        issued_at=ISSUED,
        expires_at=EXPIRES,
    )


def fake_signature(public_key: str, payload: bytes) -> str:
    """TEST ONLY; NOT ED25519; NOT PRODUCTION SECURITY."""
    raw = base64.urlsafe_b64decode(public_key + "==")
    return base64.urlsafe_b64encode(hashlib.sha512(raw + payload).digest()).decode().rstrip("=")


class DeterministicTestVerifier:
    """TEST ONLY; NOT ED25519; NOT PRODUCTION SECURITY."""

    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable

    def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool:
        if self.unavailable:
            raise RuntimeError("test backend unavailable")
        return algorithm == ED25519_ALGORITHM and signature == fake_signature(public_key, payload)


class StaticTestTrustStore:
    def __init__(self, entry: TrustedRootIssuerKey | None) -> None:
        self.entry = entry

    def lookup(self, *, issuer_id: str, signing_key_id: str, algorithm: str) -> TrustedRootIssuerKey | None:
        return self.entry


def trusted(**changes: object) -> TrustedRootIssuerKey:
    values: dict[str, object] = {
        "issuer_id": "resource-principal-issuer",
        "signing_key_id": KEY_ID,
        "algorithm": ED25519_ALGORITHM,
        "public_key": PUBLIC_KEY,
        "valid_from": "2026-09-21T07:00:00Z",
        "valid_until": "2026-09-21T10:00:00Z",
        "revocation_status": "active",
    }
    values.update(changes)
    return TrustedRootIssuerKey(**values)  # type: ignore[arg-type]


def claim(principal: CausalResourcePrincipal | None = None, **changes: object) -> RootPrincipalIssuerProvenance:
    principal = principal or mint()
    values: dict[str, object] = {
        "principal_id": principal.principal_id,
        "principal_binding_digest": principal.binding_digest,
        "issuer_id": principal.issuer_id,
        "signing_key_id": KEY_ID,
        "algorithm": ED25519_ALGORITHM,
        "signed_at": SIGNED,
    }
    values.update(changes)
    payload = canonical_root_provenance_payload(**values)  # type: ignore[arg-type]
    signature = fake_signature(PUBLIC_KEY, payload)
    return RootPrincipalIssuerProvenance.create(**values, signature=signature)  # type: ignore[arg-type]


def verifier(entry: TrustedRootIssuerKey | None = None, *, unavailable: bool = False) -> RootIssuerProvenanceVerifier:
    return RootIssuerProvenanceVerifier(
        trust_store=StaticTestTrustStore(trusted() if entry is None else entry),
        signature_verifier=DeterministicTestVerifier(unavailable=unavailable),
    )


def assert_error(code: str, action: object) -> None:
    with pytest.raises(RootIssuerProvenanceError, match=f"^{code}$"):
        action()  # type: ignore[operator]


def test_deterministic_full_provenance_verification_returns_authenticated_evidence() -> None:
    principal = mint()
    provenance = claim(principal)
    result = verifier().verify(principal, provenance, current_time=CURRENT)
    assert result == AuthenticatedRootPrincipalEvidence(
        principal_id=principal.principal_id,
        principal_binding_digest=principal.binding_digest,
        provenance_digest=provenance.provenance_digest,
        issuer_id=principal.issuer_id,
        signing_key_id=KEY_ID,
        algorithm=ED25519_ALGORITHM,
        signed_at=SIGNED,
    )
    assert verifier().verify(principal, provenance, current_time=CURRENT) == result


def test_immutable_exact_round_trip_and_bounded_fields() -> None:
    provenance = claim()
    assert RootPrincipalIssuerProvenance.from_mapping(provenance.to_dict()) == provenance
    with pytest.raises(FrozenInstanceError):
        provenance.signature = "x"  # type: ignore[misc]
    assert {item.name for item in fields(provenance)} == authentication._FIELDS
    assert not hasattr(AuthenticatedRootPrincipalEvidence, "from_mapping")
    forbidden = {"authority", "capability", "grant", "admission", "allocation", "quota", "entitlement"}
    assert {item.name for item in fields(AuthenticatedRootPrincipalEvidence)}.isdisjoint(forbidden)


@pytest.mark.parametrize(
    "extra",
    [
        {"unknown": True},
        {"verified": True},
        {"public_key": PUBLIC_KEY},
        {"capability": "all"},
        {"admission": "approved"},
        {"quota": "unlimited"},
        {"allocation": {}},
        {"resource_limits": {"gpu": "all"}},
    ],
)
def test_serialized_verified_public_key_allocation_smuggling_fails(extra: dict[str, object]) -> None:
    assert_error("provenance_fields_not_exact", lambda: RootPrincipalIssuerProvenance.from_mapping(claim().to_dict() | extra))


def test_fixed_domain_canonical_payload_and_digest_vector() -> None:
    provenance = claim()
    expected = (
        b'{"algorithm":"ed25519","domain":"sentientos.causal_resource_principal.issuer_provenance:v1",'
        b'"issuer_id":"resource-principal-issuer","principal_binding_digest":"sha256:'
        b'5d3496cb6e888442d98c928cc64b2bfbb133ecd2ff7dd3878a94ac0b2a2987e7",'
        b'"principal_id":"crp-sha256:906b35862977e1ee004c33046e4e76f23c7be9beffc86af464ee28eb0e3fd8dd",'
        b'"schema":"sentientos.causal_resource_principal.issuer_provenance:v1",'
        b'"signed_at":"2026-09-21T08:10:00Z","signing_key_id":"' + KEY_ID.encode() + b'"}\n'
    )
    assert SIGNING_DOMAIN == PROVENANCE_SCHEMA
    assert canonical_root_provenance_payload(
        principal_id=provenance.principal_id,
        principal_binding_digest=provenance.principal_binding_digest,
        issuer_id=provenance.issuer_id,
        signing_key_id=provenance.signing_key_id,
        algorithm=provenance.algorithm,
        signed_at=provenance.signed_at,
    ) == expected
    assert provenance.provenance_digest == "sha256:1bc8b5a5f19ef697991446bb57e1c70b168c9947e42a6bf12f786984138078da"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("schema", "v2", "unsupported_schema"),
        ("principal_id", "root", "invalid_principal_id"),
        ("principal_binding_digest", "bad", "invalid_principal_binding_digest"),
        ("issuer_id", "*", "invalid_issuer_id"),
        ("signing_key_id", "key", "invalid_signing_key_id"),
        ("algorithm", "hmac-test", "unsupported_algorithm"),
        ("signed_at", "2026-09-21T08:10:00+00:00", "invalid_signed_at"),
        ("signature", "AAAA=", "invalid_signature_encoding"),
        ("signature", "AAAA", "invalid_signature_encoding"),
        ("provenance_digest", "sha256:" + "0" * 64, "invalid_provenance_digest"),
    ],
)
def test_claim_validation_has_bounded_errors(field: str, value: object, code: str) -> None:
    mapping = claim().to_dict()
    mapping[field] = value
    if field != "provenance_digest":
        mapping["provenance_digest"] = authentication.provenance_digest_for(mapping)
    assert_error(code, lambda: RootPrincipalIssuerProvenance.from_mapping(mapping))


def test_principal_key_and_issuer_substitution_fails() -> None:
    principal = mint()
    other = mint(epoch=2)
    assert_error("principal_binding_mismatch", lambda: verifier().verify(other, claim(principal), current_time=CURRENT))
    issuer_claim = claim(principal).to_dict()
    issuer_claim["issuer_id"] = "another-issuer"
    issuer_claim["provenance_digest"] = authentication.provenance_digest_for(issuer_claim)
    assert_error("issuer_mismatch", lambda: verifier().verify(principal, issuer_claim, current_time=CURRENT))
    wrong_raw = b"z" * 32
    wrong_key = base64.urlsafe_b64encode(wrong_raw).decode().rstrip("=")
    assert_error(
        "trusted_key_binding_mismatch",
        lambda: verifier(trusted(public_key=wrong_key)).verify(principal, claim(principal), current_time=CURRENT),
    )


def test_untrusted_wrong_or_unusable_key_cannot_authenticate() -> None:
    principal = mint()
    provenance = claim(principal)
    missing = RootIssuerProvenanceVerifier(
        trust_store=StaticTestTrustStore(None), signature_verifier=DeterministicTestVerifier()
    )
    assert_error("trusted_key_not_found", lambda: missing.verify(principal, provenance, current_time=CURRENT))
    assert_error("trusted_key_not_yet_valid", lambda: verifier(trusted(valid_from="2026-09-21T08:11:00Z")).verify(principal, provenance, current_time=CURRENT))
    assert_error("trusted_key_expired", lambda: verifier(trusted(valid_until=SIGNED)).verify(principal, provenance, current_time=CURRENT))
    assert_error("trusted_key_revoked", lambda: verifier(trusted(revocation_status="revoked")).verify(principal, provenance, current_time=CURRENT))


def test_signature_mismatch_and_backend_failure_close() -> None:
    principal = mint()
    mapping = claim(principal).to_dict()
    mapping["signature"] = base64.urlsafe_b64encode(b"x" * 64).decode().rstrip("=")
    mapping["provenance_digest"] = authentication.provenance_digest_for(mapping)
    assert_error("signature_verification_failed", lambda: verifier().verify(principal, mapping, current_time=CURRENT))
    assert_error("signature_backend_unavailable", lambda: verifier(unavailable=True).verify(principal, claim(principal), current_time=CURRENT))


@pytest.mark.parametrize("signed_at", ["2026-09-21T07:59:59Z", EXPIRES, "2026-09-21T09:01:00Z"])
def test_signed_at_must_be_inside_principal_window(signed_at: str) -> None:
    principal = mint()
    assert_error("invalid_signed_at", lambda: verifier().verify(principal, claim(principal, signed_at=signed_at), current_time=CURRENT))


def test_principal_is_canonical_verified_first_and_must_be_current() -> None:
    principal = mint()
    malformed = replace(principal, binding_digest="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="binding_digest_mismatch"):
        verifier().verify(malformed, {"verified": True}, current_time=CURRENT)
    with pytest.raises(ValueError, match="principal_expired"):
        verifier().verify(principal, claim(principal), current_time=EXPIRES)


def test_protocol_surfaces_and_runtime_have_no_forbidden_capabilities() -> None:
    assert set(inspect.signature(RootIssuerProvenanceSigner.authenticate_root_provenance).parameters) == {"self", "principal", "signed_at"}
    assert not hasattr(RootIssuerProvenanceSigner, "sign")
    assert set(inspect.signature(RootIssuerTrustStore.lookup).parameters) == {"self", "issuer_id", "signing_key_id", "algorithm"}
    for operation in ("add", "update", "delete", "rotate", "revoke", "create"):
        assert not hasattr(RootIssuerTrustStore, operation)
    assert not hasattr(RootIssuerProvenanceVerifier, "sign")
    runtime = Path(authentication.__file__).read_text(encoding="utf-8")
    forbidden_imports = ("cryptography", "nacl.signing", "keyring", "subprocess", "HmacTestStrategicSigner", "SshStrategicSigner")
    assert not any(f"import {name}" in runtime or f"from {name}" in runtime for name in forbidden_imports)
    assert "DeterministicTestVerifier" not in runtime and "fake_signature" not in runtime
