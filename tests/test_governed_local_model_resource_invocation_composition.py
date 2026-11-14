# mypy: ignore-errors
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentientos.causal_resource_principal import RootPrincipalIssuer, VerifiedOperatorSponsorship
from sentientos.causal_resource_principal_authentication import RootIssuerProvenanceVerifier, RootPrincipalIssuerProvenance
from sentientos.causal_resource_principal_currentness import PrincipalCurrentnessVerifier, ReadOnlyPrincipalRevocationRegistry, REGISTRY_SCHEMA, registry_digest_for
from sentientos.causal_resource_principal_trust_catalog import CATALOG_SCHEMA, ReadOnlyTrustedIssuerCatalog, catalog_digest_for
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import (AdmissionOutcome, AuthorityClass,
    ControlActionRequest, ControlPlaneKernel, LifecyclePhase)
from sentientos.game_performance_bridge import VerifiedGamePerformanceObservation
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, GovernedLocalModelResourceInvocationContext, LocalModelInvocationBudget
from sentientos.governed_local_model_invocation import LocalModelInvocationDeferred
from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceAllocator, GovernedLocalModelResourceBounds, GovernedLocalModelResourceLedger, GovernedLocalModelResourcePolicy
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import (HostObservationCollectorSpec,
    HostResourceRuntimeCoordinator, build_observation_plan, validate_evaluation)
from sentientos.local_model_authority import build_local_model_authority_map, digest_payload
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionError, _resource_linkage_fields,
)
from sentientos.runtime_governor import RuntimeGovernor

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

def setup(tmp_path: Path, *, calls=2, model=None, kernel=None, cpu_ceiling=None,
          max_input_chars=100):
    tmp_path.mkdir(parents=True, exist_ok=True)
    public = bytes(range(32)); key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest(); issuer = "issuer"
    issuance = RootPrincipalIssuer(issuer_id=issuer, sponsorship_verifier=Sponsor(), provenance_signer=Signer(key_id)).mint_root_with_provenance(sponsorship_evidence={}, subject_binding_digest="sha256:" + "2" * 64, epoch=7, issued_at="2026-09-21T08:00:00Z", expires_at="2026-09-21T10:00:00Z", signed_at="2026-09-21T08:10:00Z")
    catalog_body = {"schema": CATALOG_SCHEMA, "catalog_version": 1, "entries": [{"issuer_id": issuer, "signing_key_id": key_id, "algorithm": "ed25519", "public_key": base64.urlsafe_b64encode(public).decode().rstrip("="), "valid_from": "2026-09-21T07:00:00Z", "valid_until": "2026-09-21T11:00:00Z", "revocation_status": "active"}]}
    cd = catalog_digest_for(catalog_body); cp = tmp_path / "catalog.json"; cp.write_text(json.dumps({**catalog_body, "catalog_digest": cd}))
    auth = RootIssuerProvenanceVerifier(trust_store=ReadOnlyTrustedIssuerCatalog.load(cp, expected_catalog_version=1, expected_catalog_digest=cd), signature_verifier=SignatureVerifier()).verify(issuance.principal, issuance.provenance, current_time=NOW)
    registry_body = {"schema": REGISTRY_SCHEMA, "registry_version": 1, "generated_at": "2026-09-21T08:00:00Z", "valid_until": "2026-09-21T09:30:00Z", "revoked_principals": []}
    rd = registry_digest_for(registry_body); rp = tmp_path / "registry.json"; rp.write_text(json.dumps({**registry_body, "registry_digest": rd}))
    current = PrincipalCurrentnessVerifier().verify(issuance.principal, auth, ReadOnlyPrincipalRevocationRegistry.load(rp, expected_registry_version=1, expected_registry_digest=rd), current_time=NOW)
    bounds = GovernedLocalModelResourceBounds(max_input_chars, 200, 20, 5.0, calls,
        cpu_ceiling)
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




def test_cancelled_worker_sample_reconciles_reserved_cpu_entitlement(tmp_path):
    started = threading.Event()
    cancelled = threading.Event()

    class SampledCancellationModel(Model):
        supports_per_invocation_thread_limit = True

        def generate_governed_with_metadata(self, prompt, **kwargs):
            started.set()
            if not cancelled.wait(2):
                raise AssertionError("test cancellation was not delivered")
            raise RuntimeError("worker_terminated_for_game_priority")

        def cancel_pending_generation(self):
            cancelled.set()
            return True

        def take_cancelled_generation_resource_observation(self):
            return {
                "schema_version":
                    "sentientos.governed_local_model_backend_resource_observation:v1",
                "backend": "llama_cpp",
                "observation_source": "parent_sampled_exact_runtime_worker",
                "user_cpu_seconds": 0.6,
                "system_cpu_seconds": 0.15,
                "wall_seconds": 0.8,
                "process_peak_rss_bytes": None,
            }

    model, invoker, _, context, ledger = setup(tmp_path, model=SampledCancellationModel(),
        cpu_ceiling=20.0)
    request = invoker.build_request(purpose="local_user_chat", prompt="wait",
        caller="test", correlation_id="cancelled-cpu-accounting",
        budget=LocalModelInvocationBudget(100, 200, 20, 5.0, 2),
        linkage={"max_backend_threads": 2})
    result = []
    worker = threading.Thread(target=lambda: result.append(
        invoker.invoke(request, resource_context=context)))
    worker.start()
    assert started.wait(2)
    active_reference = invoker.active_invocation_request_reference()
    assert active_reference is not None
    kernel = invoker.kernel
    decision = kernel._finalize(ControlActionRequest(
        action_kind="local_model_inference_preemption",
        authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
        actor="production_chat_game_workload_governor",
        target_subsystem="governed_local_model_invocation",
        requested_phase=LifecyclePhase.RUNTIME,
        metadata={"correlation_id": "active-inference-preemption:"
            + digest_payload(dict(active_reference)) + ":cancelled-cpu-test"}),
        AdmissionOutcome.ALLOW, ["admitted"], {})
    assert invoker.cancel_pending_generation(reason="workload_transition",
        cancellation_admission_decision=decision) is True
    worker.join(2)

    assert not worker.is_alive()
    receipt = result[0]
    assert receipt.status == "cancelled"
    assert receipt.schema_version == "sentientos.local_model_invocation_receipt:v5"
    assert receipt.cancellation_resource_observation["user_cpu_seconds"] == 0.6
    assert ledger._state["receipts"][-2]["resource_specific_measurement"][
        "backend_resource_observation"] == receipt.cancellation_resource_observation
    assert ledger.cpu_seconds_used(context.allocation.allocation_id) == 0.75
    recovered = GovernedLocalModelResourceLedger(ledger.path)
    assert recovered.cpu_seconds_used(context.allocation.allocation_id) == 0.75
    from sentientos.governed_local_model_invocation import validate_receipt
    assert validate_receipt(receipt.to_dict())[0]
    from sentientos.host_resource_runtime import resource_consumption_world_state_records
    projected = resource_consumption_world_state_records(
        ledger=ledger, invocation_receipts=[receipt.to_dict()],
        verified_inference_admission_decisions=[{
            "schema_version": "sentientos.resource_bound_inference_admission_witness:v1",
            "invocation_receipt_id": receipt.receipt_id,
            "invocation_receipt_digest": receipt.receipt_digest,
            "request_id": receipt.request["request_id"],
            "request_digest": receipt.request["request_digest"],
            "admission_decision_ref": receipt.admission_decision_ref,
            "correlation_id": receipt.request["correlation_id"],
            "resource_allocation_binding": {
                "schema_version": (
                    "sentientos.governed_local_model_resource_allocation_admission_context:v1"),
                "allocation_id": context.allocation.allocation_id,
                "allocation_digest": context.allocation.allocation_digest,
                "allocator_id": context.allocation.allocator_id,
                "resource_kind": context.allocation.resource_kind,
                "policy_digest": context.allocation.policy_digest,
                "policy_epoch": context.allocation.epoch,
                "principal_binding_digest": context.allocation.principal_binding_digest,
            },
        }])[0]
    assert projected["disposition"] == "recorded"
    assert not any(finding.startswith(
        "backend_resource_observation_receipt_mismatch:")
        for finding in projected["payload"]["lineage_findings"])

    unlinked_v5 = receipt.to_dict()
    for field in ("resource_allocation_digest", "resource_attempt_id",
            "resource_consumption_receipt_digests", "resource_linkage_digest"):
        unlinked_v5.pop(field)
    incomplete_lineage = resource_consumption_world_state_records(
        ledger=ledger, invocation_receipts=[unlinked_v5])[0]
    assert incomplete_lineage["disposition"] == "degraded"
    assert any(finding.startswith("invocation_resource_linkage_missing:")
        for finding in incomplete_lineage["payload"]["lineage_findings"])


def test_inference_admission_records_exact_preflighted_resource_allocation(
        tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.0")
    decisions_path = tmp_path / "kernel-decisions.jsonl"
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        phase=LifecyclePhase.RUNTIME, decisions_path=decisions_path)
    _, invoker, request, context, ledger = setup(tmp_path / "resource",
        kernel=kernel)

    receipt = invoker.invoke(request, resource_context=context)

    assert receipt.status == "admitted_completed"
    assert receipt.resource_allocation_digest == context.allocation.allocation_digest
    decisions = [json.loads(line) for line in decisions_path.read_text(
        encoding="utf-8").splitlines()]
    decision = next(item for item in decisions
        if item.get("action_kind") == "local_model_inference")
    binding = decision["delegated_outcomes"]["runtime_governor"][
        "evidence_refs"]["resource_allocation_binding"]
    assert binding == {
        "schema_version": (
            "sentientos.governed_local_model_resource_allocation_admission_context:v1"),
        "allocation_id": context.allocation.allocation_id,
        "allocation_digest": context.allocation.allocation_digest,
        "allocator_id": context.allocation.allocator_id,
        "resource_kind": context.allocation.resource_kind,
        "policy_digest": context.allocation.policy_digest,
        "policy_epoch": context.allocation.epoch,
        "principal_binding_digest": context.allocation.principal_binding_digest,
    }
    assert ledger._state["receipts"][-1]["effect_receipt_digest"] == (
        receipt.receipt_digest)


def test_exact_backend_resource_observation_flows_into_governed_allocation_receipt(tmp_path):
    class MeasuredModel(Model):
        supports_per_invocation_thread_limit = True

        def generate_governed_with_metadata(self, prompt, **kwargs):
            self.calls += 1
            ceiling = kwargs.get("max_backend_threads")
            control = {
                "schema_version": "sentientos.llama_cpp_backend_thread_limit_control:v1",
                "requested_ceiling": ceiling,
                "setter_function": "llama_set_n_threads" if ceiling is not None else None,
                "n_threads_argument": min(2, ceiling) if ceiling is not None else None,
                "n_threads_batch_argument": min(2, ceiling) if ceiling is not None else None,
            }
            return self.text, {
                "schema_version": "sentientos.llama_cpp_completion_observation:v3",
                "backend": "llama_cpp", "finish_reason": "unknown",
                "completion_tokens": None, "prompt_tokens": None,
                "token_limit_reached": None,
                "invocation_resources": {
                    "schema_version": "sentientos.llama_cpp_invocation_resource_observation:v1",
                    "user_cpu_seconds": 0.14, "system_cpu_seconds": 0.02,
                    "wall_seconds": 0.18, "process_peak_rss_bytes": 7_340_032,
                },
                "backend_thread_limit_control": control,
            }

    model, invoker, _, context, ledger = setup(tmp_path, model=MeasuredModel())
    request = invoker.build_request(purpose="local_user_chat", prompt="hello",
        caller="test", correlation_id="observed-backend-resources",
        budget=LocalModelInvocationBudget(100, 200, 20, 5.0, 2),
        linkage={"max_backend_threads": 2})

    receipt = invoker.invoke(request, resource_context=context)

    assert receipt.status == "admitted_completed" and model.calls == 1
    observation = ledger._state["receipts"][-2]["resource_specific_measurement"][
        "backend_resource_observation"]
    assert observation == {
        "schema_version": "sentientos.governed_local_model_backend_resource_observation:v1",
        "backend": "llama_cpp", "observation_source": "exact_runtime_worker_process",
        "user_cpu_seconds": 0.14, "system_cpu_seconds": 0.02,
        "wall_seconds": 0.18, "process_peak_rss_bytes": 7_340_032,
    }
    assert ledger._state["receipts"][-1]["effect_receipt_digest"] == receipt.receipt_digest
    from sentientos.host_resource_runtime import resource_consumption_world_state_records

    projected = resource_consumption_world_state_records(
        ledger=ledger, invocation_receipts=[receipt.to_dict()],
        verified_inference_admission_decisions=[{
            "schema_version": "sentientos.resource_bound_inference_admission_witness:v1",
            "invocation_receipt_id": receipt.receipt_id,
            "invocation_receipt_digest": receipt.receipt_digest,
            "request_id": receipt.request["request_id"],
            "request_digest": receipt.request["request_digest"],
            "admission_decision_ref": receipt.admission_decision_ref,
            "correlation_id": receipt.request["correlation_id"],
            "resource_allocation_binding": {
                "schema_version": (
                    "sentientos.governed_local_model_resource_allocation_admission_context:v1"),
                "allocation_id": context.allocation.allocation_id,
                "allocation_digest": context.allocation.allocation_digest,
                "allocator_id": context.allocation.allocator_id,
                "resource_kind": context.allocation.resource_kind,
                "policy_digest": context.allocation.policy_digest,
                "policy_epoch": context.allocation.epoch,
                "principal_binding_digest": context.allocation.principal_binding_digest,
            },
        }])[0]
    assert projected["disposition"] == "recorded"
    assert projected["payload"]["lineage_posture"] == "verified"
    assert projected["payload"]["inference_admission_decision_posture"] == "verified"
    assert projected["payload"]["invocation_receipts"][0][
        "admission_decision_ref"] == receipt.admission_decision_ref

    missing_admission = resource_consumption_world_state_records(
        ledger=ledger, invocation_receipts=[receipt.to_dict()],
        verified_inference_admission_decisions=[])[0]
    assert missing_admission["disposition"] == "degraded"
    assert missing_admission["payload"]["inference_admission_decision_posture"] == "degraded"

    substituted_admission = {
        "schema_version": "sentientos.resource_bound_inference_admission_witness:v1",
        "invocation_receipt_id": receipt.receipt_id,
        "invocation_receipt_digest": receipt.receipt_digest,
        "request_id": receipt.request["request_id"],
        "request_digest": receipt.request["request_digest"],
        "admission_decision_ref": receipt.admission_decision_ref,
        "correlation_id": receipt.request["correlation_id"],
        "resource_allocation_binding": {
            "schema_version": (
                "sentientos.governed_local_model_resource_allocation_admission_context:v1"),
            "allocation_id": "lmalloc-000000000000000000000000",
            "allocation_digest": context.allocation.allocation_digest,
            "allocator_id": context.allocation.allocator_id,
            "resource_kind": context.allocation.resource_kind,
            "policy_digest": context.allocation.policy_digest,
            "policy_epoch": context.allocation.epoch,
            "principal_binding_digest": context.allocation.principal_binding_digest,
        },
    }
    substituted_projection = resource_consumption_world_state_records(
        ledger=ledger, invocation_receipts=[receipt.to_dict()],
        verified_inference_admission_decisions=[substituted_admission])[0]
    assert substituted_projection["disposition"] == "degraded"
    assert any(finding.startswith("inference_admission_linkage_missing_or_mismatched:")
        for finding in substituted_projection["payload"]["lineage_findings"])

    substituted = receipt.to_dict()
    substituted["backend_completion"]["invocation_resources"][
        "user_cpu_seconds"] = 0.15
    degraded = resource_consumption_world_state_records(
        ledger=ledger, invocation_receipts=[substituted])[0]
    assert degraded["disposition"] == "degraded"
    assert any(finding.startswith("backend_resource_observation_receipt_mismatch:")
        for finding in degraded["payload"]["lineage_findings"])


def test_exact_worker_cpu_overrun_denies_later_generation_through_invoker(tmp_path):
    class OverrunMeasuredModel(Model):
        supports_per_invocation_thread_limit = True

        def generate_governed_with_metadata(self, prompt, **kwargs):
            self.calls += 1
            ceiling = kwargs.get("max_backend_threads")
            return self.text, {
                "schema_version": "sentientos.llama_cpp_completion_observation:v3",
                "backend": "llama_cpp", "finish_reason": "unknown",
                "completion_tokens": None, "prompt_tokens": None,
                "token_limit_reached": None,
                "invocation_resources": {
                    "schema_version": "sentientos.llama_cpp_invocation_resource_observation:v1",
                    "user_cpu_seconds": 0.9, "system_cpu_seconds": 0.0,
                    "wall_seconds": 0.3, "process_peak_rss_bytes": 7_340_032,
                },
                "backend_thread_limit_control": {
                    "schema_version": "sentientos.llama_cpp_backend_thread_limit_control:v1",
                    "requested_ceiling": ceiling, "setter_function": "llama_set_n_threads",
                    "n_threads_argument": min(2, ceiling),
                    "n_threads_batch_argument": min(2, ceiling),
                },
            }

    model, invoker, _, context, ledger = setup(
        tmp_path, model=OverrunMeasuredModel(), cpu_ceiling=1.6)
    request = invoker.build_request(purpose="local_user_chat", prompt="hello",
        caller="test", correlation_id="cpu-budget-feedback",
        budget=LocalModelInvocationBudget(100, 200, 20, 0.4, 2),
        linkage={"max_backend_threads": 2})

    first = invoker.invoke(request, resource_context=context)
    assert first.status == "admitted_completed" and model.calls == 1
    assert ledger.cpu_seconds_used(context.allocation.allocation_id) == 0.9

    second_request = invoker.build_request(purpose="local_user_chat", prompt="hello",
        caller="test", correlation_id="cpu-budget-feedback-second",
        budget=LocalModelInvocationBudget(100, 200, 20, 0.4, 2),
        linkage={"max_backend_threads": 2})
    second = invoker.invoke(second_request, resource_context=replace(
        context, durable_attempt_nonce="cpu-budget-feedback-second"))
    assert second.status == "resource_denied", second.reason_codes
    assert any(reason.endswith("cpu_seconds_entitlement_exhausted")
        for reason in second.reason_codes)
    assert second.effects["local_model_inference"] is False
    assert model.calls == 1
    assert len(ledger._state["attempts"]) == 1


def test_resource_admission_guard_defers_without_backend_entry_or_debit(tmp_path):
    model, invoker, request, context, ledger = setup(tmp_path, calls=1)

    def defer_for_game_pressure():
        raise LocalModelInvocationDeferred("vram_pressure")

    receipt = invoker.invoke(request, resource_context=context,
        pre_effect_guard=defer_for_game_pressure)

    assert receipt.status == "deferred"
    assert receipt.reason_codes == (
        "runtime_resource_admission_deferred", "vram_pressure")
    assert receipt.effects["local_model_inference"] is False
    assert model.calls == 0
    assert ledger.remaining_calls(context.allocation.allocation_id) == 1
    assert states(ledger) == ["attempted_not_begun"]


def test_resource_receipt_linkage_is_projection_ready_without_inventing_measurements(tmp_path):
    model, invoker, request, context, ledger = setup(tmp_path)
    receipt = invoker.invoke(request, resource_context=context)
    projection = _resource_linkage_fields(receipt)
    actual = ledger._state["receipts"][-2:]
    assert projection["resource_allocation_digest"] == context.allocation.allocation_digest
    assert projection["resource_attempt_id"] == actual[0]["attempt_id"]
    assert projection["resource_consumption_receipt_digests"] == tuple(
        item["receipt_digest"] for item in actual)
    assert actual[-1]["effect_receipt_digest"] == receipt.receipt_digest
    assert projection["resource_linkage_digest"] == receipt.resource_linkage_digest
    with pytest.raises(ResidentDevelopmentalCognitionError,
            match="cognition_resource_linkage_digest_mismatch"):
        _resource_linkage_fields(replace(receipt,
            resource_consumption_receipt_digests=("0" * 64, "1" * 64)))

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

def test_rejected_concurrent_invocation_does_not_consume_resource_entitlement(tmp_path):
    started = threading.Event()
    release = threading.Event()
    model = Model()

    def generate_while_blocked(_prompt, **_kwargs):
        model.calls += 1
        started.set()
        if not release.wait(timeout=5):
            raise AssertionError("fixture backend was not released")
        return "first"

    model.generate = generate_while_blocked
    model.cancel_pending_generation = lambda: False
    model, invoker, _, context, ledger = setup(tmp_path, calls=2, model=model)
    first_request = invoker.build_request(purpose="local_user_chat", prompt="first",
        caller="test", correlation_id="lingering-first",
        budget=LocalModelInvocationBudget(100, 200, 20, 0.02, 2))
    first = invoker.invoke(first_request, resource_context=context)

    assert started.is_set()
    assert first.status == "timeout"
    assert len(ledger._state["attempts"]) == 1
    assert ledger.remaining_calls(context.allocation.allocation_id) == 1

    second_request = invoker.build_request(purpose="local_user_chat", prompt="second",
        caller="test", correlation_id="lingering-second",
        budget=LocalModelInvocationBudget(100, 200, 20, 0.02, 2))
    second_context = replace(context, durable_attempt_nonce="nonce-second")
    second = invoker.invoke(second_request, resource_context=second_context)

    assert second.status == "backend_failure"
    assert second.effects["local_model_inference"] is False
    assert model.calls == 1
    assert len(ledger._state["attempts"]) == 1
    assert ledger.remaining_calls(context.allocation.allocation_id) == 1
    release.set()

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


def test_background_inference_defers_then_recovers_with_measured_effect_receipts(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.1")
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor, phase=LifecyclePhase.RUNTIME,
        decisions_path=tmp_path / "decisions.jsonl")
    model, invoker, _, context, ledger = setup(tmp_path, kernel=kernel)
    request = invoker.build_request(purpose="resident_developmental_interpretation", prompt="background work",
        caller="maintenance", correlation_id="background-retry", budget=LocalModelInvocationBudget(100, 200, 20, 5.0, 2))

    deferred = invoker.invoke(request, resource_context=context)
    assert deferred.status == "deferred"
    assert deferred.effects["local_model_inference"] is False
    assert model.calls == 0 and ledger._state["receipts"] == []

    def collect(name: str, **values: object) -> HostCollectorResult:
        return HostCollectorResult(name, "available", "2026-11-02T00:00:00+00:00", "fixture", values=values)

    specs = (
        HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
            lambda observed_at=None: collect("cpu", utilization_percent=20.0)),
        HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
            lambda observed_at=None: collect("memory", used_percent=50.0)),
        HostObservationCollectorSpec("disk", True, ("linux", "unknown"), 3,
            lambda observed_at=None: collect("disk", used_percent=20.0, free_bytes=1000)),
    )
    kernel.set_phase(LifecyclePhase.MAINTENANCE)
    evaluation = HostResourceRuntimeCoordinator(kernel=kernel, runtime_state_root=tmp_path / "observation",
        plan=build_observation_plan(specs=specs)).run_cycle(correlation_id="recovery-observation")
    assert evaluation is not None
    assert evaluation.policy_decision.status == "host_resource_policy_nominal"
    kernel.set_phase(LifecyclePhase.RUNTIME)

    completed = invoker.invoke(request, resource_context=context)
    assert completed.status == "admitted_completed", completed.reason_codes
    assert completed.effects["local_model_inference"] is True
    assert completed.latency_ms >= 0 and model.calls == 1
    assert [item["state"] for item in ledger._state["receipts"]] == [
        "attempt_begun", "measured_completed", "reconciled"]
    assert ledger._state["receipts"][-1]["effect_receipt_digest"] == completed.receipt_digest


def test_game_host_pressure_defers_and_nominal_recovery_still_yields_to_game(
        tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_CPU", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_IO", "0.0")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_THERMAL", "0.0")
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        phase=LifecyclePhase.RUNTIME, decisions_path=tmp_path / "decisions.jsonl")
    model, invoker, request, context, ledger = setup(
        tmp_path / "allocation", kernel=kernel)

    def game_sample(sequence: int) -> VerifiedGamePerformanceObservation:
        return VerifiedGamePerformanceObservation(
            "windows-edge", "edge-generation-1", sequence,
            f"{sequence:064x}", f"{sequence + 1:064x}",
            datetime.now(timezone.utc).isoformat(), "f" * 64,
            16.7, 0, 20.0, 4096, "available")

    def resource_plan(gpu: float):
        def collect(name: str, **values: object) -> HostCollectorResult:
            return HostCollectorResult(name, "available",
                datetime.now(timezone.utc).isoformat(), "fixture", values=values)
        specs = (
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                lambda observed_at=None: collect("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                lambda observed_at=None: collect("memory", used_percent=40.0)),
            HostObservationCollectorSpec("disk", True, ("linux", "unknown"), 3,
                lambda observed_at=None: collect("disk", used_percent=30.0,
                    free_bytes=1000)),
            HostObservationCollectorSpec("nvidia_gpu", False,
                ("linux", "unknown"), 4, lambda observed_at=None: collect(
                    "nvidia_gpu", device_count=1, devices=[{
                        "index": 0, "gpu_utilization_percent": gpu,
                        "vram_utilization_percent": gpu}])),
        )
        return build_observation_plan(specs=specs)

    assert governor.observe_verified_game_performance(game_sample(1))
    pressured = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "pressure",
        plan=resource_plan(95.0)).run_cycle(correlation_id="gaming-pressure")
    assert pressured is not None and validate_evaluation(pressured).ok
    assert "gpu_pressure" in pressured.pressure_report.pressure_labels
    deferred = invoker.invoke(request, resource_context=context)
    assert deferred.status == "deferred"
    assert deferred.effects["local_model_inference"] is False
    assert model.calls == 0
    assert ledger._state["attempts"] == {}
    assert ledger._state["receipts"] == []
    assert ledger.remaining_calls(context.allocation.allocation_id) == 2

    assert governor.observe_verified_game_performance(game_sample(2))
    recovered_evaluation = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "recovery",
        plan=resource_plan(20.0)).run_cycle(correlation_id="gaming-recovered")
    assert recovered_evaluation is not None
    assert validate_evaluation(recovered_evaluation).ok
    completed = invoker.invoke(request, resource_context=context)
    assert completed.status == "deferred"
    assert completed.effects["local_model_inference"] is False
    assert model.calls == 0
    assert ledger._state["attempts"] == {}
    assert ledger._state["receipts"] == []
    assert ledger.remaining_calls(context.allocation.allocation_id) == 2
