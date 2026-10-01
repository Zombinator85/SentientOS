# mypy: ignore-errors
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentientos.causal_resource_principal import RootPrincipalIssuer, VerifiedOperatorSponsorship
from sentientos.causal_resource_principal_authentication import RootIssuerProvenanceVerifier, RootPrincipalIssuerProvenance
from sentientos.causal_resource_principal_currentness import PrincipalCurrentnessVerifier, ReadOnlyPrincipalRevocationRegistry, REGISTRY_SCHEMA, registry_digest_for
from sentientos.causal_resource_principal_trust_catalog import CATALOG_SCHEMA, ReadOnlyTrustedIssuerCatalog, catalog_digest_for
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import AdmissionOutcome, ControlPlaneKernel, LifecyclePhase
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, GovernedLocalModelResourceInvocationContext, LocalModelInvocationBudget
from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceAllocator, GovernedLocalModelResourceBounds, GovernedLocalModelResourceLedger, GovernedLocalModelResourcePolicy
from sentientos.local_model_authority import build_local_model_authority_map

pytestmark = pytest.mark.no_legacy_skip
NOW = "2026-09-21T08:30:00Z"

class Sponsor:
    def verify(self, evidence): return VerifiedOperatorSponsorship("sha256:" + "1" * 64)
class Signer:
    def __init__(self, key_id): self.key_id = key_id
    def authenticate_root_provenance(self, principal, *, signed_at):
        return RootPrincipalIssuerProvenance.create(principal_id=principal.principal_id, principal_binding_digest=principal.binding_digest, issuer_id=principal.issuer_id, signing_key_id=self.key_id, algorithm="ed25519", signed_at=signed_at, signature=base64.urlsafe_b64encode(b"s" * 64).decode().rstrip("="))
class SignatureVerifier:
    def verify(self, **kwargs): return True
class Model:
    def __init__(self, text="answer", error=False, delay=0): self.text, self.error, self.delay, self.calls = text, error, delay, 0
    def generate(self, prompt, **kwargs):
        self.calls += 1
        if self.delay: time.sleep(self.delay)
        if self.error: raise RuntimeError("secret backend details")
        return self.text
class DenyingKernel:
    phase = LifecyclePhase.RUNTIME
    def admit(self, request):
        return SimpleNamespace(allowed=False, outcome=AdmissionOutcome.DENY, reason_codes=("test_denial",), admission_decision_ref=None, to_dict=lambda: {"outcome": "deny"})

def setup(tmp_path: Path, *, calls=2, model=None, kernel=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    public = bytes(range(32)); key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest(); issuer = "issuer"
    issuance = RootPrincipalIssuer(issuer_id=issuer, sponsorship_verifier=Sponsor(), provenance_signer=Signer(key_id)).mint_root_with_provenance(sponsorship_evidence={}, subject_binding_digest="sha256:" + "2" * 64, epoch=7, issued_at="2026-09-21T08:00:00Z", expires_at="2026-09-21T10:00:00Z", signed_at="2026-09-21T08:10:00Z")
    catalog_body = {"schema": CATALOG_SCHEMA, "catalog_version": 1, "entries": [{"issuer_id": issuer, "signing_key_id": key_id, "algorithm": "ed25519", "public_key": base64.urlsafe_b64encode(public).decode().rstrip("="), "valid_from": "2026-09-21T07:00:00Z", "valid_until": "2026-09-21T11:00:00Z", "revocation_status": "active"}]}
    cd = catalog_digest_for(catalog_body); cp = tmp_path / "catalog.json"; cp.write_text(json.dumps({**catalog_body, "catalog_digest": cd}))
    auth = RootIssuerProvenanceVerifier(trust_store=ReadOnlyTrustedIssuerCatalog.load(cp, expected_catalog_version=1, expected_catalog_digest=cd), signature_verifier=SignatureVerifier()).verify(issuance.principal, issuance.provenance, current_time=NOW)
    registry_body = {"schema": REGISTRY_SCHEMA, "registry_version": 1, "generated_at": "2026-09-21T08:00:00Z", "valid_until": "2026-09-21T09:30:00Z", "revoked_principals": []}
    rd = registry_digest_for(registry_body); rp = tmp_path / "registry.json"; rp.write_text(json.dumps({**registry_body, "registry_digest": rd}))
    current = PrincipalCurrentnessVerifier().verify(issuance.principal, auth, ReadOnlyPrincipalRevocationRegistry.load(rp, expected_registry_version=1, expected_registry_digest=rd), current_time=NOW)
    bounds = GovernedLocalModelResourceBounds(100, 200, 20, 5.0, calls)
    policy = GovernedLocalModelResourcePolicy.create(epoch=11, max_resource_specific_bounds=bounds, not_before="2026-09-21T08:00:00Z", valid_until="2026-09-21T09:15:00Z")
    ledger = GovernedLocalModelResourceLedger(tmp_path / "ledger.json"); allocator = GovernedLocalModelResourceAllocator(policy=policy, ledger=ledger)
    allocation = allocator.issue(principal=issuance.principal, authenticated=auth, current=current, requested_bounds=bounds, requested_not_before="2026-09-21T08:00:00Z", requested_not_after="2026-09-21T10:00:00Z", current_time=NOW)
    artifact = tmp_path / "model.gguf"; artifact.write_bytes(b"model")
    authority = build_local_model_authority_map(ModelConfig([ModelCandidate(artifact, "llama_cpp", "m")], generation=GenerationConfig(max_new_tokens=8)), allowed_roots=[tmp_path])
    backend = model or Model(); invoker = GovernedLocalModelInvoker(model=backend, authority_map=authority, kernel=kernel or ControlPlaneKernel(phase=LifecyclePhase.RUNTIME, decisions_path=tmp_path / "decisions.jsonl"), runtime_root=tmp_path / "runtime")
    context = GovernedLocalModelResourceInvocationContext(allocator, allocation, issuance.principal, auth, current, policy, "nonce", lambda: NOW)
    request = invoker.build_request(purpose="local_user_chat", prompt="hello", caller="test", correlation_id="correlation", budget=LocalModelInvocationBudget(100, 200, 20, 5.0, calls))
    return backend, invoker, request, context, ledger

def states(ledger): return [item["state"] for item in ledger._state["receipts"]]

def test_resource_backed_completion_cross_links_exact_effect_receipt_and_survives_restart(tmp_path):
    model, invoker, request, context, ledger = setup(tmp_path)
    receipt = invoker.invoke(request, resource_context=context)
    assert receipt.status == "admitted_completed" and receipt.output_text == "answer" and model.calls == 1
    assert states(ledger) == ["attempt_begun", "measured_completed", "reconciled"]
    assert ledger._state["receipts"][-1]["effect_receipt_digest"] == receipt.receipt_digest
    assert ledger.remaining_calls(context.allocation.allocation_id) == 1
    assert GovernedLocalModelResourceLedger(ledger.path).remaining_calls(context.allocation.allocation_id) == 1

def test_serving_guard_rejection_restores_only_pre_entry_debit(tmp_path):
    model, invoker, request, context, ledger = setup(tmp_path)
    receipt = invoker.invoke(request, resource_context=context, pre_effect_guard=lambda: (_ for _ in ()).throw(ValueError("stale")))
    assert receipt.status == "backend_failure" and model.calls == 0
    assert states(ledger) == ["attempted_not_begun"] and ledger.remaining_calls(context.allocation.allocation_id) == 2

def test_timeout_and_backend_failure_consume_and_reconcile(tmp_path):
    for name, backend, expected in [("timeout", Model(delay=.02), "measured_timeout"), ("failure", Model(error=True), "measured_backend_failure")]:
        root = tmp_path / name; model, invoker, request, context, ledger = setup(root, model=backend)
        if name == "timeout": request = invoker.build_request(purpose="local_user_chat", prompt="hello", caller="test", correlation_id="c", budget=LocalModelInvocationBudget(100, 200, 20, .001, 2))
        receipt = invoker.invoke(request, resource_context=context)
        assert model.calls == 1 and states(ledger) == ["attempt_begun", expected, "reconciled"]
        assert ledger.remaining_calls(context.allocation.allocation_id) == 1
        assert ledger._state["receipts"][-1]["effect_receipt_digest"] == receipt.receipt_digest

def test_preflight_and_denied_admission_never_debit(tmp_path):
    model, invoker, request, context, ledger = setup(tmp_path / "wide")
    wide = invoker.build_request(purpose="local_user_chat", prompt="hello", caller="test", correlation_id="wide", budget=LocalModelInvocationBudget(101, 200, 20, 5, 2))
    assert invoker.invoke(wide, resource_context=context).status == "blocked_invalid"
    assert model.calls == 0 and not ledger._state["attempts"]
    model, invoker, request, context, ledger = setup(tmp_path / "deny", kernel=DenyingKernel())
    assert invoker.invoke(request, resource_context=context).status == "denied"
    assert model.calls == 0 and not ledger._state["attempts"]

def test_duplicate_nonce_exhaustion_and_correlation_rollover_do_not_replenish(tmp_path):
    model, invoker, request, context, ledger = setup(tmp_path, calls=1)
    assert invoker.invoke(request, resource_context=context).status == "admitted_completed"
    request2 = invoker.build_request(purpose="local_user_chat", prompt="hello", caller="test", correlation_id="new-correlation", budget=request.budget)
    duplicate = invoker.invoke(request2, resource_context=context)
    assert duplicate.status == "resource_denied" and "resource_gate:duplicate_attempt_id" in duplicate.reason_codes and model.calls == 1
    fresh = GovernedLocalModelResourceInvocationContext(context.allocator, context.allocation, context.principal, context.authenticated, context.current, context.policy, "fresh", context.clock)
    request3 = invoker.build_request(purpose="local_user_chat", prompt="hello", caller="test", correlation_id="third", budget=request.budget)
    assert invoker.invoke(request3, resource_context=fresh).status == "resource_denied" and model.calls == 1

def test_serialized_smuggling_does_not_activate_resource_gate(tmp_path):
    model, invoker, _, context, ledger = setup(tmp_path)
    request = invoker.build_request(purpose="local_user_chat", prompt="hello", caller="test", correlation_id="smuggle", upstream_evidence={"resource_context": context.allocation.to_dict(), "attempt_id": "forged"}, linkage={"principal_currentness": "forged", "call_entitlement": True})
    receipt = invoker.invoke(request)
    assert receipt.status == "admitted_completed" and model.calls == 1 and not ledger._state["attempts"]
    assert "resource_context" in receipt.request["upstream_evidence"]

def test_post_effect_guard_failure_consumes_and_cross_links_in_memory_receipt(tmp_path):
    model, invoker, request, context, ledger = setup(tmp_path)
    receipt = invoker.invoke(request, resource_context=context, persist=False,
        post_effect_guard=lambda: (_ for _ in ()).throw(ValueError("stale")))
    assert model.calls == 1 and receipt.status == "serving_lifetime_stale_after_generation"
    assert receipt.output_text is None and receipt.effects["local_model_inference"] is True
    assert ledger.remaining_calls(context.allocation.allocation_id) == 1
    assert states(ledger) == ["attempt_begun", "measured_completed", "reconciled"]
    assert ledger._state["receipts"][-1]["effect_receipt_digest"] == receipt.receipt_digest
    assert not (invoker.runtime_root / "receipts" / f"{receipt.receipt_id}.json").exists()
