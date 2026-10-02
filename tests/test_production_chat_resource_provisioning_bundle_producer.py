from __future__ import annotations

import base64
import hashlib
import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentientos.causal_resource_principal import RootPrincipalIssuer, VerifiedOperatorSponsorship
from sentientos.causal_resource_principal_provenance_signer import CryptographyEd25519RootIssuerProvenanceSigner
from sentientos.causal_resource_principal_signer_custody import RootIssuerPrivateKeyBackend, RootIssuerPrivateKeyCustody, RootIssuerSigningKeyReference
from sentientos.causal_resource_principal_trust_catalog import CATALOG_SCHEMA, catalog_digest_for
from sentientos.causal_resource_principal_currentness import REGISTRY_SCHEMA, registry_digest_for
from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceBounds, GovernedLocalModelResourceLedger, GovernedLocalModelResourcePolicy
from sentientos.installation_state import InstallationIdentity, InstallationStateHandle, InstallationStateRegistry
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from sentientos.production_chat_resource_provisioning_bundle_producer import ProductionChatResourceProvisioningBundleProducerError, produce_production_chat_resource_provisioning_bundle

pytestmark = pytest.mark.no_legacy_skip
NOW = "2026-09-21T08:30:00Z"

class Sponsor:
    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        return VerifiedOperatorSponsorship("sha256:" + "1" * 64)

class Backend:
    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        return bytearray(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"="))

def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

def inputs(tmp_path: Path, *, calls: int = 2):
    registry = InstallationStateRegistry(tmp_path / "state", _test_only=True)
    handle = registry.open(InstallationIdentity.parse("production"), create=True)
    seed = bytes(range(32)); public = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest(); issuer = "issuer"
    reference = RootIssuerSigningKeyReference(issuer_id=issuer, signing_key_id=key_id, algorithm="ed25519", key_reference="key")
    signer = CryptographyEd25519RootIssuerProvenanceSigner(reference=reference, custody=RootIssuerPrivateKeyCustody(reference=reference, backend=cast(RootIssuerPrivateKeyBackend, Backend())))
    issuance = RootPrincipalIssuer(issuer_id=issuer, sponsorship_verifier=Sponsor(), provenance_signer=signer).mint_root_with_provenance(
        sponsorship_evidence={}, subject_binding_digest="sha256:" + "2" * 64, epoch=1,
        issued_at="2026-09-21T08:00:00Z", expires_at="2026-09-21T10:00:00Z", signed_at="2026-09-21T08:10:00Z")
    cb = {"schema": CATALOG_SCHEMA, "catalog_version": 1, "entries": [{"issuer_id": issuer, "signing_key_id": key_id, "algorithm": "ed25519", "public_key": base64.urlsafe_b64encode(public).decode().rstrip("="), "valid_from": "2026-09-21T07:00:00Z", "valid_until": "2026-09-21T11:00:00Z", "revocation_status": "active"}]}
    rb = {"schema": REGISTRY_SCHEMA, "registry_version": 1, "generated_at": "2026-09-21T08:00:00Z", "valid_until": "2026-09-21T09:30:00Z", "revoked_principals": []}
    bounds = GovernedLocalModelResourceBounds(100, 200, 20, 5.0, calls)
    policy = GovernedLocalModelResourcePolicy.create(epoch=1, max_resource_specific_bounds=bounds, not_before="2026-09-21T08:00:00Z", valid_until="2026-09-21T09:15:00Z")
    kwargs = dict(principal_artifact=encoded(issuance.principal.to_dict()), provenance_artifact=encoded(issuance.provenance.to_dict()), trusted_issuer_catalog_artifact=encoded({**cb, "catalog_digest": catalog_digest_for(cb)}), principal_revocation_registry_artifact=encoded({**rb, "registry_digest": registry_digest_for(rb)}), resource_policy_artifact=encoded(policy.to_dict()), requested_bounds=bounds, requested_not_before="2026-09-21T08:00:00Z", requested_not_after="2026-09-21T09:00:00Z", clock=lambda: NOW)
    return handle, kwargs

def test_producer_publishes_manifest_last_and_existing_consumer_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle, kwargs = inputs(tmp_path); order = []; issue_calls = 0
    original = InstallationStateHandle.durable_create
    from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceAllocator
    original_issue = GovernedLocalModelResourceAllocator.issue
    def counted_issue(self, **values):
        nonlocal issue_calls
        issue_calls += 1
        return original_issue(self, **values)
    def observed(self, obj, data, **options):
        order.append(obj.relative.parts[-1]); return original(self, obj, data, **options)
    monkeypatch.setattr(InstallationStateHandle, "durable_create", observed)
    monkeypatch.setattr(GovernedLocalModelResourceAllocator, "issue", counted_issue)
    result = produce_production_chat_resource_provisioning_bundle(handle, "primary", **kwargs)
    assert order == ["root-principal.json", "root-principal-provenance.json", "trusted-issuer-catalog.json", "principal-revocation-registry.json", "resource-policy.json", "manifest.json"]
    owner = load_production_chat_resource_context_owner(handle, "primary", clock=lambda: NOW, nonce_source=lambda: "nonce")
    assert (owner.principal.principal_id, owner.allocation.allocation_id, owner.policy.policy_digest) == (result.principal_id, result.allocation_id, result.resource_policy_digest)
    assert owner.allocator.ledger.snapshot_counts() == (1, 0, 0)
    assert owner.allocator.ledger.remaining_calls(result.allocation_id) == 2
    assert issue_calls == 1

def test_same_id_rerun_rejects_before_second_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle, kwargs = inputs(tmp_path); result = produce_production_chat_resource_provisioning_bundle(handle, "once", **kwargs)
    path = handle.fixed_object("local-model/resource-provisioning/once/resource-ledger.json").path
    before = path.read_bytes(); calls = 0
    from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceAllocator
    original = GovernedLocalModelResourceAllocator.issue
    def counted(self, **values):
        nonlocal calls; calls += 1; return original(self, **values)
    monkeypatch.setattr(GovernedLocalModelResourceAllocator, "issue", counted)
    with pytest.raises(ProductionChatResourceProvisioningBundleProducerError, match="provisioning_destination_not_unused"):
        produce_production_chat_resource_provisioning_bundle(handle, "once", **kwargs)
    assert calls == 0 and path.read_bytes() == before
    assert GovernedLocalModelResourceLedger(path).snapshot_counts() == (1, 0, 0)
    assert result.allocation_id

def test_preflight_failure_does_not_mutate_or_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle, kwargs = inputs(tmp_path); calls = 0
    from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceAllocator
    monkeypatch.setattr(GovernedLocalModelResourceAllocator, "issue", lambda *a, **k: (_ for _ in ()).throw(AssertionError("issued")))
    bad = {**kwargs, "clock": lambda: "2026-09-21T09:15:00Z"}
    with pytest.raises(ProductionChatResourceProvisioningBundleProducerError, match="policy_not_current"):
        produce_production_chat_resource_provisioning_bundle(handle, "stale", **bad)
    assert not handle.fixed_object("local-model/resource-provisioning/stale/resource-ledger.json").path.exists()
    assert calls == 0

def test_partial_publication_is_burned_and_unloadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle, kwargs = inputs(tmp_path); original = InstallationStateHandle.durable_create
    def fail_policy(self, obj, data, **options):
        if obj.relative.parts[-1] == "resource-policy.json": raise OSError("injected")
        return original(self, obj, data, **options)
    monkeypatch.setattr(InstallationStateHandle, "durable_create", fail_policy)
    with pytest.raises(ProductionChatResourceProvisioningBundleProducerError, match="bundle_publication_failed"):
        produce_production_chat_resource_provisioning_bundle(handle, "partial", **kwargs)
    prefix = handle.fixed_object("local-model/resource-provisioning/partial")
    assert "resource-ledger.json" in handle.list_regular_names(prefix) and "manifest.json" not in handle.list_regular_names(prefix)
    with pytest.raises(Exception): load_production_chat_resource_context_owner(handle, "partial", clock=lambda: NOW)
    monkeypatch.setattr(InstallationStateHandle, "durable_create", original)
    with pytest.raises(ProductionChatResourceProvisioningBundleProducerError, match="provisioning_destination_not_unused"):
        produce_production_chat_resource_provisioning_bundle(handle, "partial", **kwargs)
    assert GovernedLocalModelResourceLedger(handle.fixed_object("local-model/resource-provisioning/partial/resource-ledger.json").path).snapshot_counts() == (1, 0, 0)

def test_concurrent_same_id_has_one_publication_and_one_allocation(tmp_path: Path) -> None:
    handle, kwargs = inputs(tmp_path)
    def run():
        try: return produce_production_chat_resource_provisioning_bundle(handle, "race", **kwargs)
        except ProductionChatResourceProvisioningBundleProducerError as exc: return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: run(), range(2)))
    assert sum(not isinstance(value, str) for value in results) == 1
    ledger = GovernedLocalModelResourceLedger(handle.fixed_object("local-model/resource-provisioning/race/resource-ledger.json").path)
    assert ledger.snapshot_counts() == (1, 0, 0)
    assert handle.list_regular_names(handle.fixed_object("local-model/resource-provisioning/race")).count("manifest.json") == 1

def test_restart_reloads_same_allocation_without_replenishing(tmp_path: Path) -> None:
    handle, kwargs = inputs(tmp_path, calls=2)
    result = produce_production_chat_resource_provisioning_bundle(handle, "restart", **kwargs)
    first = load_production_chat_resource_context_owner(
        handle, "restart", clock=lambda: NOW, nonce_source=lambda: "first")
    first.allocator.final_gate(
        allocation=first.allocation, principal=first.principal,
        authenticated=first.authenticated, current=first.current, policy=first.policy,
        current_time=NOW, durable_attempt_nonce="first")
    assert first.allocator.ledger.remaining_calls(result.allocation_id) == 1
    restarted = load_production_chat_resource_context_owner(
        handle, "restart", clock=lambda: NOW, nonce_source=lambda: "second")
    assert (restarted.allocation.allocation_id, restarted.allocation.allocation_digest) == (
        result.allocation_id, result.allocation_digest)
    assert restarted.allocator.ledger.remaining_calls(result.allocation_id) == 1
    restarted.allocator.final_gate(
        allocation=restarted.allocation, principal=restarted.principal,
        authenticated=restarted.authenticated, current=restarted.current, policy=restarted.policy,
        current_time=NOW, durable_attempt_nonce="second")
    assert restarted.allocator.ledger.remaining_calls(result.allocation_id) == 0

def test_public_api_has_no_paths_or_private_authority() -> None:
    import sentientos.production_chat_resource_provisioning_bundle_producer as module
    parameters = inspect.signature(module.produce_production_chat_resource_provisioning_bundle).parameters
    assert not {"principal_path", "provenance_path", "catalog_path", "registry_path", "policy_path", "destination_path", "state_root"}.intersection(parameters)
    source = inspect.getsource(module)
    for forbidden in ("RootPrincipalIssuer(", "PrivateKeyCustody", "ProvenanceSigner(", ".mint_root", "final_gate", "record_backend_entry", "durable_replace"):
        assert forbidden not in source
