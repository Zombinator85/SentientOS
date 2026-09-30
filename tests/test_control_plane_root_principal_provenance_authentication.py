from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from codex.proof_budget_governor import GovernorConfig, PressureState
from sentientos.causal_resource_principal import RootPrincipalIssuance, RootPrincipalIssuer, VerifiedOperatorSponsorship
from sentientos.causal_resource_principal_authentication import RootIssuerProvenanceVerifier
from sentientos.causal_resource_principal_currentness import PrincipalCurrentnessVerifier, ReadOnlyPrincipalRevocationRegistry
from sentientos.causal_resource_principal_ed25519 import CryptographyEd25519RootIssuerSignatureVerifier
from sentientos.causal_resource_principal_provenance_signer import CryptographyEd25519RootIssuerProvenanceSigner
from sentientos.causal_resource_principal_signer_custody import (
    RootIssuerPrivateKeyBackend,
    RootIssuerPrivateKeyCustody,
    RootIssuerSigningKeyReference,
)
from sentientos.causal_resource_principal_trust_catalog import CATALOG_SCHEMA, ReadOnlyTrustedIssuerCatalog, catalog_digest_for
from sentientos.control_plane_kernel import AuthorityClass, ControlActionDecision, ControlActionRequest, ControlPlaneKernel, LifecyclePhase
from sentientos.runtime_governor import GovernorDecision, PressureSnapshot

SEED = bytes(range(32))
ISSUER = "control-plane-test-issuer"
NOW = "2026-09-21T08:10:00Z"
pytestmark = pytest.mark.no_legacy_skip


class _Sponsor:
    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        return VerifiedOperatorSponsorship("sha256:" + "1" * 64)


class _KeyBackend:
    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        return bytearray(base64.urlsafe_b64encode(SEED).rstrip(b"="))


class _AllowGovernor:
    def admit_action(self, action_type: str, actor: str, correlation_id: str, metadata: object = None) -> GovernorDecision:
        return GovernorDecision(action_class=action_type, allowed=True, mode="enforce", reason="allowed", subject="proof", scope="local", origin=actor, sampled_pressure=PressureSnapshot(cpu=.1, io=.1, thermal=.1, gpu=.1, composite=.1, sampled_at=NOW), reason_hash="hash", correlation_id=correlation_id, action_priority=0, action_family="control")


def _kernel(
    tmp_path: Path,
    name: str,
    verifier: RootIssuerProvenanceVerifier | None = None,
    *,
    principal_currentness_verifier: PrincipalCurrentnessVerifier | None = None,
    principal_revocation_registry: ReadOnlyPrincipalRevocationRegistry | None = None,
) -> ControlPlaneKernel:
    return ControlPlaneKernel(runtime_governor=_AllowGovernor(), phase=LifecyclePhase.MAINTENANCE, decisions_path=tmp_path / name, clock=lambda: 1789978200, root_issuer_provenance_verifier=verifier, principal_currentness_verifier=principal_currentness_verifier, principal_revocation_registry=principal_revocation_registry)  # type: ignore[arg-type]


def _issuance() -> tuple[RootPrincipalIssuance, bytes, str]:
    public = Ed25519PrivateKey.from_private_bytes(SEED).public_key().public_bytes_raw()
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest()
    reference = RootIssuerSigningKeyReference(issuer_id=ISSUER, signing_key_id=key_id, algorithm="ed25519", key_reference="test-key")
    signer = CryptographyEd25519RootIssuerProvenanceSigner(
        reference=reference,
        custody=RootIssuerPrivateKeyCustody(reference=reference, backend=cast(RootIssuerPrivateKeyBackend, _KeyBackend())),
    )
    issuance = RootPrincipalIssuer(issuer_id=ISSUER, sponsorship_verifier=_Sponsor(), provenance_signer=signer).mint_root_with_provenance(
        sponsorship_evidence={}, subject_binding_digest="sha256:" + "2" * 64, epoch=7,
        issued_at="2026-09-21T08:00:00Z", expires_at="2026-09-21T09:00:00Z", signed_at=NOW,
    )
    return issuance, public, key_id


def _verifier(tmp_path: Path, *, status: str = "active", public: bytes | None = None, valid_from: str = "2026-09-21T07:00:00Z", valid_until: str = "2026-09-21T10:00:00Z") -> RootIssuerProvenanceVerifier:
    _, actual_public, key_id = _issuance()
    public = actual_public if public is None else public
    body = {"schema": CATALOG_SCHEMA, "catalog_version": 1, "entries": [{
        "issuer_id": ISSUER, "signing_key_id": key_id, "algorithm": "ed25519",
        "public_key": base64.urlsafe_b64encode(public).decode().rstrip("="),
        "valid_from": valid_from, "valid_until": valid_until, "revocation_status": status,
    }]}
    digest = catalog_digest_for(body)
    path = tmp_path / f"catalog-{status}-{valid_from[-9:-1]}.json"
    path.write_text(json.dumps({**body, "catalog_digest": digest}), encoding="utf-8")
    catalog = ReadOnlyTrustedIssuerCatalog.load(path, expected_catalog_version=1, expected_catalog_digest=digest)
    return RootIssuerProvenanceVerifier(trust_store=catalog, signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier())


def _request(principal: object | None, provenance: object | None, correlation: str = "root-auth") -> ControlActionRequest:
    context = {"config": GovernorConfig(configured_k=3, configured_m=2, max_k=9, escalation_enabled=True, mode="normal", admissible_collapse_runs=2, min_m=1, diagnostics_k=4), "pressure_state": PressureState(consecutive_no_admissible=0, recent_runs=[]), "run_context": {"pipeline": "genesis", "router_attempt": 1}}
    if principal is not None:
        context["causal_resource_principal"] = principal
    if provenance is not None:
        context["causal_resource_principal_provenance"] = provenance
    return ControlActionRequest(action_kind="proposal_eval", authority_class=AuthorityClass.PROPOSAL_EVALUATION, actor="forge", target_subsystem="proof", requested_phase=LifecyclePhase.MAINTENANCE, metadata={"correlation_id": correlation}, proof_budget_context=context)


def _attribution(kernel: ControlPlaneKernel, request: ControlActionRequest) -> tuple[ControlActionDecision, dict[str, object]]:
    decision = kernel.admit(request)
    return decision, decision.delegated_outcomes["proof_budget_context"]["causal_attribution"]


def test_real_ed25519_issuance_catalog_verification_upgrades_only_attribution(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    verifier = _verifier(tmp_path)
    authenticated_decision, observed = _attribution(_kernel(tmp_path, "auth.jsonl", verifier), _request(issuance.principal.to_dict(), issuance.provenance.to_dict()))
    expected = verifier.verify(issuance.principal, issuance.provenance, current_time=NOW)
    canonical_decision, canonical = _attribution(_kernel(tmp_path, "canonical.jsonl"), _request(issuance.principal.to_dict(), None, "canonical"))
    assert observed == {"status": "authenticated_root_issuer_provenance_verified", "principal_id": expected.principal_id, "root_principal_id": issuance.principal.root_principal_id, "principal_binding_digest": expected.principal_binding_digest, "issuer_id": expected.issuer_id, "epoch": issuance.principal.epoch, "provenance_authentication": "verified", "provenance_digest": expected.provenance_digest, "signing_key_id": expected.signing_key_id, "algorithm": expected.algorithm, "signed_at": expected.signed_at}
    assert canonical["status"] == "canonical_root_binding_verified"
    assert authenticated_decision.outcome == canonical_decision.outcome
    assert authenticated_decision.reason_codes == canonical_decision.reason_codes
    assert authenticated_decision.delegated_outcomes["proof_budget_governor"] == canonical_decision.delegated_outcomes["proof_budget_governor"]


def test_absent_or_unconfigured_provenance_degrades_to_canonical(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    for provenance, expected_posture in ((None, None), (issuance.provenance.to_dict(), "verifier_not_configured")):
        _, observed = _attribution(_kernel(tmp_path, f"{expected_posture}.jsonl"), _request(issuance.principal.to_dict(), provenance, str(expected_posture)))
        assert observed["status"] == "canonical_root_binding_verified"
        assert observed.get("provenance_authentication") == expected_posture


def test_invalid_provenance_is_bounded_and_policy_invariant(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    malformed = {"caller_public_key": "secret", "verified": True, "authenticated": True}
    kernel = _kernel(tmp_path, "bad.jsonl", _verifier(tmp_path))
    bad_decision, observed = _attribution(kernel, _request(issuance.principal.to_dict(), malformed))
    plain_decision, _ = _attribution(_kernel(tmp_path, "plain.jsonl"), _request(issuance.principal.to_dict(), None, "plain"))
    assert observed["status"] == "canonical_root_binding_verified"
    assert observed["provenance_authentication"] == "failed"
    assert observed["provenance_authentication_reason"] == "provenance_malformed"
    assert "caller_public_key" not in observed and bad_decision.outcome == plain_decision.outcome
    assert bad_decision.delegated_outcomes["proof_budget_governor"] == plain_decision.delegated_outcomes["proof_budget_governor"]


def test_mutation_binding_substitution_and_trust_failures_never_upgrade(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    mutations = [
        replace(issuance.provenance, signature=("A" if issuance.provenance.signature[0] != "A" else "B") + issuance.provenance.signature[1:]),
        replace(issuance.provenance, principal_id="crp-sha256:" + "4" * 64),
        replace(issuance.provenance, principal_binding_digest="sha256:" + "5" * 64),
        replace(issuance.provenance, issuer_id="substituted-issuer"),
        replace(issuance.provenance, signing_key_id="ed25519-sha256:" + "6" * 64),
    ]
    for index, provenance in enumerate(mutations):
        _, observed = _attribution(_kernel(tmp_path, f"mutation-{index}.jsonl", _verifier(tmp_path)), _request(issuance.principal.to_dict(), provenance.to_dict(), str(index)))
        assert observed["status"] == "canonical_root_binding_verified" and observed["provenance_authentication"] == "failed"


def test_untrusted_key_and_unavailable_crypto_never_upgrade(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()

    class _NoTrust:
        def lookup(self, *, issuer_id: str, signing_key_id: str, algorithm: str):  # type: ignore[no-untyped-def]
            return None

    class _UnavailableCrypto:
        def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool:
            raise RuntimeError("sensitive backend detail")

    trusted = _verifier(tmp_path)
    unavailable = RootIssuerProvenanceVerifier(
        trust_store=trusted._trust_store,  # type: ignore[attr-defined]
        signature_verifier=_UnavailableCrypto(),
    )
    untrusted = RootIssuerProvenanceVerifier(
        trust_store=_NoTrust(),  # type: ignore[arg-type]
        signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier(),
    )
    for name, verifier, reason in (
        ("untrusted", untrusted, "untrusted_issuer_key"),
        ("unavailable", unavailable, "cryptographic_backend_unavailable"),
    ):
        _, observed = _attribution(_kernel(tmp_path, f"{name}.jsonl", verifier), _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), name))
        assert observed["status"] == "canonical_root_binding_verified"
        assert observed["provenance_authentication_reason"] == reason
        assert "sensitive" not in str(observed)
    for index, verifier in enumerate((_verifier(tmp_path, status="revoked"), _verifier(tmp_path, valid_from="2026-09-21T08:20:00Z"), _verifier(tmp_path, valid_until="2026-09-21T08:05:00Z"))):
        _, observed = _attribution(_kernel(tmp_path, f"trust-{index}.jsonl", verifier), _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), f"trust-{index}"))
        assert observed["status"] == "canonical_root_binding_verified" and observed["provenance_authentication"] == "failed"


def test_provenance_without_root_and_run_context_claims_cannot_manufacture_attribution(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    request = _request(None, issuance.provenance.to_dict())
    assert request.proof_budget_context is not None
    request.proof_budget_context["run_context"].update({"causal_resource_principal": issuance.principal.to_dict(), "authenticated": True, "public_key": "attacker"})
    decision = _kernel(tmp_path, "none.jsonl", _verifier(tmp_path)).admit(request)
    assert "causal_attribution" not in decision.delegated_outcomes["proof_budget_context"]


def test_control_plane_has_verification_dependency_but_no_signing_or_authority_surface() -> None:
    forbidden = {"sign", "mint", "allocate", "entitle", "grant", "RootPrincipalIssuer", "private_key", "key_reference"}
    names = set(ControlPlaneKernel.__dict__)
    assert not any(any(word.lower() in name.lower() for word in forbidden) for name in names)
