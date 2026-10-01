from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any, cast

import pytest
from sentientos.causal_resource_principal import RootPrincipalIssuer, VerifiedOperatorSponsorship
from sentientos.causal_resource_principal_authentication import RootIssuerProvenanceVerifier, RootPrincipalIssuerProvenance
from sentientos.causal_resource_principal_currentness import PrincipalCurrentnessVerifier, ReadOnlyPrincipalRevocationRegistry, REGISTRY_SCHEMA, registry_digest_for
from sentientos.causal_resource_principal_trust_catalog import CATALOG_SCHEMA, ReadOnlyTrustedIssuerCatalog, catalog_digest_for
from sentientos.governed_local_model_resource_allocation import *

pytestmark = pytest.mark.no_legacy_skip
NOW = "2026-09-21T08:30:00Z"


class Sponsor:
    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        return VerifiedOperatorSponsorship("sha256:" + "1" * 64)


class Signer:
    def __init__(self, key_id: str) -> None: self.key_id = key_id
    def authenticate_root_provenance(self, principal: Any, *, signed_at: str) -> RootPrincipalIssuerProvenance:
        return RootPrincipalIssuerProvenance.create(principal_id=principal.principal_id,
            principal_binding_digest=principal.binding_digest, issuer_id=principal.issuer_id,
            signing_key_id=self.key_id, algorithm="ed25519", signed_at=signed_at,
            signature=base64.urlsafe_b64encode(b"s" * 64).decode().rstrip("="))


class Verifier:
    def verify(self, *, algorithm: str, public_key: str, payload: bytes, signature: str) -> bool: return True


def context(tmp_path: Path) -> tuple[Any, ...]:
    public = bytes(range(32))
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest()
    issuer = "resource-principal-issuer"
    issuance = RootPrincipalIssuer(issuer_id=issuer, sponsorship_verifier=Sponsor(), provenance_signer=Signer(key_id)).mint_root_with_provenance(
        sponsorship_evidence={}, subject_binding_digest="sha256:" + "2" * 64, epoch=7,
        issued_at="2026-09-21T08:00:00Z", expires_at="2026-09-21T10:00:00Z", signed_at="2026-09-21T08:10:00Z")
    body = {"schema": CATALOG_SCHEMA, "catalog_version": 1, "entries": [{"issuer_id": issuer, "signing_key_id": key_id,
        "algorithm": "ed25519", "public_key": base64.urlsafe_b64encode(public).decode().rstrip("="), "valid_from": "2026-09-21T07:00:00Z",
        "valid_until": "2026-09-21T11:00:00Z", "revocation_status": "active"}]}
    digest = catalog_digest_for(body); path = tmp_path / "catalog.json"; path.write_text(json.dumps({**body, "catalog_digest": digest}))
    catalog = ReadOnlyTrustedIssuerCatalog.load(path, expected_catalog_version=1, expected_catalog_digest=digest)
    authenticated = RootIssuerProvenanceVerifier(trust_store=catalog, signature_verifier=Verifier()).verify(
        issuance.principal, issuance.provenance, current_time=NOW)
    registry_body = {"schema": REGISTRY_SCHEMA, "registry_version": 1, "generated_at": "2026-09-21T08:00:00Z", "valid_until": "2026-09-21T09:30:00Z", "revoked_principals": []}
    rd = registry_digest_for(registry_body); rp = tmp_path / "registry.json"; rp.write_text(json.dumps({**registry_body, "registry_digest": rd}))
    registry = ReadOnlyPrincipalRevocationRegistry.load(rp, expected_registry_version=1, expected_registry_digest=rd)
    current = PrincipalCurrentnessVerifier().verify(issuance.principal, authenticated, registry, current_time=NOW)
    bounds = GovernedLocalModelResourceBounds(100, 200, 20, 5.0, 2)
    policy = GovernedLocalModelResourcePolicy.create(epoch=11, max_resource_specific_bounds=bounds,
        not_before="2026-09-21T08:00:00Z", valid_until="2026-09-21T09:15:00Z")
    ledger = GovernedLocalModelResourceLedger(tmp_path / "ledger.json")
    allocator = GovernedLocalModelResourceAllocator(policy=policy, ledger=ledger)
    allocation = allocator.issue(principal=issuance.principal, authenticated=authenticated, current=current,
        requested_bounds=bounds, requested_not_before="2026-09-21T08:00:00Z", requested_not_after="2026-09-21T10:00:00Z", current_time=NOW)
    return issuance.principal, authenticated, current, policy, ledger, allocator, allocation


def test_real_principal_durable_debit_receipt_chain_and_restart(tmp_path: Path) -> None:
    principal, authenticated, current, policy, ledger, allocator, allocation = context(tmp_path)
    assert allocation.principal_epoch == 7 and allocation.epoch == 11
    attempt = allocator.final_gate(allocation=allocation, principal=principal, authenticated=authenticated, current=current,
        policy=policy, current_time=NOW, durable_attempt_nonce="one")
    begun = allocator.record_backend_entry(allocation, attempt, observed_at=NOW)
    completed = allocator.append_receipt(allocation, attempt, state="measured_completed", observed_at="2026-09-21T08:30:01Z",
        measurement=allocator.measurement(allocation, generation_attempted=True, call_units_consumed=1,
            generated_output_size_bytes=4, returned_output_size_bytes=4, latency_ms=10, invocation_outcome="completed"))
    reconciled = allocator.append_receipt(allocation, attempt, state="reconciled", observed_at="2026-09-21T08:30:02Z",
        measurement=allocator.measurement(allocation, generation_attempted=True, call_units_consumed=1,
            generated_output_size_bytes=4, returned_output_size_bytes=4, latency_ms=10, invocation_outcome="completed"),
        effect_receipt_digest="a" * 64)
    assert completed.previous_receipt_digest == begun.receipt_digest
    assert reconciled.previous_receipt_digest == completed.receipt_digest
    restarted = GovernedLocalModelResourceLedger(ledger.path)
    assert restarted.remaining_calls(allocation.allocation_id) == 1
    assert reconciled.resource_specific_measurement["actual_token_count"] is None
    assert set(reconciled.resource_specific_measurement) == {"generation_attempted", "call_units_consumed", "generated_output_size_bytes", "returned_output_size_bytes", "output_truncated", "latency_ms", "configured_bounds", "invocation_outcome", "actual_token_count"}


def test_provisional_restore_survives_restart_and_entry_is_irrevocable(tmp_path: Path) -> None:
    p, auth, current, policy, ledger, allocator, allocation = context(tmp_path)
    attempt = allocator.final_gate(allocation=allocation, principal=p, authenticated=auth, current=current, policy=policy, current_time=NOW, durable_attempt_nonce="restore")
    allocator.reconcile_not_begun(allocation, attempt, observed_at=NOW)
    assert GovernedLocalModelResourceLedger(ledger.path).remaining_calls(allocation.allocation_id) == 2
    begun = allocator.final_gate(allocation=allocation, principal=p, authenticated=auth, current=current, policy=policy, current_time=NOW, durable_attempt_nonce="begun")
    allocator.record_backend_entry(allocation, begun, observed_at=NOW)
    with pytest.raises(GovernedLocalModelResourceError, match="backend_entry_already_recorded"):
        allocator.reconcile_not_begun(allocation, begun, observed_at=NOW)


def test_fail_closed_substitution_exhaustion_and_attempt_uniqueness(tmp_path: Path) -> None:
    p, auth, current, policy, ledger, allocator, allocation = context(tmp_path)
    kwargs = dict(allocation=allocation, principal=p, authenticated=auth, current=current, policy=policy, current_time=NOW)
    allocator.final_gate(**kwargs, durable_attempt_nonce="same")
    with pytest.raises(GovernedLocalModelResourceError, match="duplicate_attempt_id"):
        allocator.final_gate(**kwargs, durable_attempt_nonce="same")
    allocator.final_gate(**kwargs, durable_attempt_nonce="two")
    with pytest.raises(GovernedLocalModelResourceError, match="call_entitlement_exhausted"):
        allocator.final_gate(**kwargs, durable_attempt_nonce="three")
    with pytest.raises(GovernedLocalModelResourceError, match="policy_substitution"):
        allocator.final_gate(**{**kwargs, "policy": GovernedLocalModelResourcePolicy.create(epoch=12,
            max_resource_specific_bounds=policy.max_resource_specific_bounds, not_before=policy.not_before, valid_until=policy.valid_until)}, durable_attempt_nonce="x")
    with pytest.raises(FrozenInstanceError):
        allocation.epoch = 12


@pytest.mark.parametrize("bad", [True, 0, -1])
def test_integer_bounds_reject_bool_and_nonpositive(bad: object) -> None:
    with pytest.raises(GovernedLocalModelResourceError):
        GovernedLocalModelResourceBounds(bad, 1, 1, 1.0, 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0])
def test_timeout_rejects_nonfinite_and_nonpositive(bad: float) -> None:
    with pytest.raises(GovernedLocalModelResourceError): GovernedLocalModelResourceBounds(1, 1, 1, bad, 1)


def test_policy_loader_is_exact_digest_bound_and_closed(tmp_path: Path) -> None:
    policy = GovernedLocalModelResourcePolicy.create(epoch=1, max_resource_specific_bounds=GovernedLocalModelResourceBounds(1, 1, 1, 1.0, 1),
        not_before="2026-09-21T08:00:00Z", valid_until="2026-09-21T09:00:00Z")
    path = tmp_path / "policy.json"; path.write_text(json.dumps(policy.to_dict()))
    assert GovernedLocalModelResourcePolicy.load(path, expected_policy_digest=policy.policy_digest) == policy
    with pytest.raises(GovernedLocalModelResourceError, match="unexpected_policy_digest"):
        GovernedLocalModelResourcePolicy.load(path, expected_policy_digest="0" * 64)
    malformed = policy.to_dict(); malformed["extra"] = True; path.write_text(json.dumps(malformed))
    with pytest.raises(GovernedLocalModelResourceError, match="policy_fields_not_exact"):
        GovernedLocalModelResourcePolicy.load(path, expected_policy_digest=policy.policy_digest)


def test_broader_request_stale_currentness_and_caller_id_fail(tmp_path: Path) -> None:
    p, auth, current, policy, _, allocator, allocation = context(tmp_path)
    with pytest.raises(GovernedLocalModelResourceError, match="requested_bounds_exceed_policy"):
        allocator.issue(principal=p, authenticated=auth, current=current, requested_bounds=GovernedLocalModelResourceBounds(101, 200, 20, 5, 2), requested_not_before=NOW, requested_not_after="2026-09-21T09:00:00Z", current_time=NOW)
    with pytest.raises(GovernedLocalModelResourceError, match="currentness_stale"):
        allocator.final_gate(allocation=allocation, principal=p, authenticated=auth, current=current, policy=policy,
            current_time=current.registry_valid_until, durable_attempt_nonce="late")
    forged = allocation.to_dict(); forged["allocation_id"] = "lmalloc-" + "0" * 24
    with pytest.raises(GovernedLocalModelResourceError, match="allocation_id_mismatch"):
        GovernedLocalModelResourceAllocation.from_mapping(forged)


def test_module_has_no_effect_or_serving_authority_surface() -> None:
    import sentientos.governed_local_model_resource_allocation as module
    forbidden = {"issue_admission", "load_model", "select_model", "activate_serving", "issue_principal", "issue_grant", "write_policy"}
    assert forbidden.isdisjoint(vars(module))
