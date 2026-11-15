# mypy: ignore-errors
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from threading import Event, Lock, Thread

import pytest

from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceError
from sentientos.governed_local_model_resource_allocation import (
    GovernedLocalModelResourceAllocator, GovernedLocalModelResourceBounds,
    GovernedLocalModelResourceLedger, GovernedLocalModelResourcePolicy,
)
from sentientos.governed_local_model_invocation import (
    LocalModelInvocationBudget, validate_receipt,
)
from sentientos.control_plane_kernel import AuthorityClass, ControlPlaneKernel
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import (
    HostObservationCollectorSpec, HostResourceRuntimeCoordinator,
    build_observation_plan, resource_consumption_world_state_records,
)
from sentientos.canonical_memory import CanonicalMemoryStore
import sentientos.chat_service as chat_service
from sentientos.chat_service import PersistentConversationService
from sentientos.conversation_session import ConversationSessionStore
from sentientos.local_model_serving_inference import ProductionServingInferenceController
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.production_chat_resource_context import (
    ProductionChatResourceContextOwner,
    ResourceBackedProductionChatInference,
)
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from sentientos.production_chat_resource_observation import (
    ProductionChatResourceObservationOwner,
)
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    produce_production_chat_resource_provisioning_bundle,
)
from tests.test_governed_local_model_resource_invocation_composition import NOW, setup
from tests.test_local_model_serving_inference import setup as serving_setup
from tests.test_production_chat_resource_provisioning_bundle_producer import (
    encoded, inputs as provisioning_inputs,
)
from sentientos.runtime_governor import RuntimeGovernor
from sentientos.game_performance_bridge import VerifiedGamePerformanceObservation
from sentientos.foreground_game_detection import ForegroundGameObservation

pytestmark = pytest.mark.no_legacy_skip


def owner(tmp_path, *, calls=2, nonces=None, clock=lambda: NOW,
        ledger_owner_lock=None):
    model, invoker, request, context, ledger = setup(tmp_path, calls=calls)
    values = iter(nonces or ["nonce-one", "nonce-two", "nonce-three"])
    result = ProductionChatResourceContextOwner(
        allocator=context.allocator,
        allocation=context.allocation,
        principal=context.principal,
        authenticated=context.authenticated,
        current=context.current,
        policy=context.policy,
        installation_identity="test-install",
        provisioning_id="test-resource.v1",
        nonce_source=lambda: next(values),
        clock=clock,
        ledger_owner_lock=ledger_owner_lock,
    )
    return result, model, invoker, request, ledger


def test_owner_uses_exact_preexisting_objects_and_zero_argument_fresh_nonce(tmp_path):
    custody, _, _, _, _ = owner(tmp_path)
    with pytest.raises(GovernedLocalModelResourceError,
                       match="resource_ledger_process_owner_required"):
        custody.recover_orphaned_provisional_attempts()
    first = custody.next_context()
    second = custody.next_context()
    assert first is not second
    assert first.allocator is second.allocator is custody.allocator
    assert first.allocation is second.allocation is custody.allocation
    assert first.principal is second.principal is custody.principal
    assert first.authenticated is second.authenticated is custody.authenticated
    assert first.current is second.current is custody.current
    assert first.policy is second.policy is custody.policy
    assert (first.durable_attempt_nonce, second.durable_attempt_nonce) == ("nonce-one", "nonce-two")
    assert first.clock is second.clock


def test_owner_rejects_substitutes_bad_nonce_and_cross_binding(tmp_path):
    custody, _, _, _, _ = owner(tmp_path)
    with pytest.raises(TypeError, match="exact_production_chat_resource_types_required"):
        ProductionChatResourceContextOwner(
            allocator=object(), allocation=custody.allocation, principal=custody.principal,
            authenticated=custody.authenticated, current=custody.current, policy=custody.policy,
            installation_identity="test-install", provisioning_id="test-resource.v1",
            nonce_source=lambda: "n", clock=lambda: NOW)
    with pytest.raises(GovernedLocalModelResourceError, match="owner_allocation_not_exactly_stored"):
        ProductionChatResourceContextOwner(
            allocator=custody.allocator,
            allocation=replace(custody.allocation, principal_id="forged"),
            principal=custody.principal, authenticated=custody.authenticated,
            current=custody.current, policy=custody.policy,
            installation_identity="test-install", provisioning_id="test-resource.v1",
            nonce_source=lambda: "n", clock=lambda: NOW)
    custody._nonce_source = lambda: ""  # type: ignore[attr-defined]
    with pytest.raises(GovernedLocalModelResourceError, match="invalid_durable_attempt_nonce"):
        custody.next_context()


def test_closed_owner_cannot_issue_context_or_serving_entitlement(tmp_path, monkeypatch):
    # This test exercises only the owner's lifecycle guard. The repository's
    # durable directory-fsync implementation is POSIX-only, so keep this small
    # object-lifecycle fixture independent of host filesystem capabilities.
    monkeypatch.setattr(
        GovernedLocalModelResourceLedger, "_persist_candidate",
        lambda self, candidate: setattr(self, "_state", candidate))
    custody, model, invoker, request, _ = owner(tmp_path)
    class ProcessCustodyLock:
        released = False

        def __exit__(self, *_args):
            self.released = True

    process_lock = ProcessCustodyLock()
    custody._ledger_owner_lock = process_lock
    issued_context = custody.next_context()
    custody.begin_close()
    assert custody.has_single_process_custody
    with pytest.raises(GovernedLocalModelResourceError,
                       match="resource_context_owner_closed"):
        custody.next_context()
    with pytest.raises(GovernedLocalModelResourceError,
                       match="resource_context_owner_closed"):
        custody.serving_admission_entitlement_binding()
    with pytest.raises(GovernedLocalModelResourceError,
                       match="resource_context_owner_closed"):
        invoker.invoke(request, resource_context=issued_context)
    assert model.calls == 0
    custody.close()
    assert not custody.has_single_process_custody
    assert process_lock.released


def test_owner_close_waits_for_previously_issued_context_lease(tmp_path, monkeypatch):
    monkeypatch.setattr(
        GovernedLocalModelResourceLedger, "_persist_candidate",
        lambda self, candidate: setattr(self, "_state", candidate))
    custody, model, invoker, request, ledger = owner(tmp_path)
    released = Event()

    class ProcessCustodyLock:
        exit_calls = 0

        def __exit__(self, *_args):
            self.exit_calls += 1
            released.set()

    process_lock = ProcessCustodyLock()
    custody._ledger_owner_lock = process_lock
    context = custody.next_context()
    backend_started = Event()
    finish_backend = Event()
    invocation_finished = Event()
    result = {}

    def blocked_generation(*_args, **_kwargs):
        model.calls += 1
        backend_started.set()
        if not finish_backend.wait(timeout=5):
            raise AssertionError("fixture_backend_not_released")
        return "answer"

    model.generate = blocked_generation

    def invoke():
        result["receipt"] = invoker.invoke(request, resource_context=context)
        invocation_finished.set()

    invocation = Thread(target=invoke)
    invocation.start()
    assert backend_started.wait(timeout=2)
    close_finished = Event()
    close_started = Event()

    def close_owner():
        close_started.set()
        custody.close()
        close_finished.set()

    closer = Thread(target=close_owner)
    close_finished_second = Event()
    close_started_second = Event()

    def close_owner_again():
        close_started_second.set()
        custody.close()
        close_finished_second.set()

    second_closer = Thread(target=close_owner_again)
    closer.start()
    second_closer.start()
    try:
        assert close_started.wait(timeout=2)
        assert close_started_second.wait(timeout=2)
        assert not close_finished.wait(timeout=0.05)
        assert not close_finished_second.wait(timeout=0.05)
        assert custody.has_single_process_custody
        assert not released.is_set()
    finally:
        finish_backend.set()
    assert invocation_finished.wait(timeout=2)
    invocation.join(timeout=2)
    assert not invocation.is_alive()
    receipt = result["receipt"]
    assert receipt.status == "admitted_completed"
    assert model.calls == 1
    assert [item["state"] for item in ledger._state["receipts"]] == [
        "attempt_begun", "measured_completed", "reconciled"]
    assert close_finished.wait(timeout=2)
    assert close_finished_second.wait(timeout=2)
    closer.join(timeout=2)
    second_closer.join(timeout=2)
    assert not closer.is_alive()
    assert not second_closer.is_alive()
    assert not custody.has_single_process_custody
    assert released.is_set()
    assert process_lock.exit_calls == 1


def test_production_chat_rejects_resource_owner_from_another_installation(
        monkeypatch, tmp_path):
    installation, artifacts = provisioning_inputs(tmp_path)
    produce_production_chat_resource_provisioning_bundle(
        installation, "chat-resource", **artifacts)
    custody = load_production_chat_resource_context_owner(
        installation, "chat-resource", clock=lambda: NOW,
        nonce_source=lambda: "owner-nonce")
    assert custody.installation_identity == installation.identity.value
    assert custody.provisioning_id == "chat-resource"
    monkeypatch.setattr(chat_service, "open_chat_process_handoff",
        lambda **_kwargs: pytest.fail("process handoff opened for foreign resource owner"))
    try:
        with pytest.raises(ValueError,
                           match="resource_context_owner_installation_identity_mismatch"):
            chat_service.configure_production_chat(
                installation_identity="other-installation",
                serving_operation_id="serve-foreign-owner",
                runtime_handoff_id="handoff-foreign-owner",
                resource_context_owner=custody)
    finally:
        custody.close()


def test_restart_reconciles_orphaned_provisional_resource_attempt(
        tmp_path):
    installation, artifacts = provisioning_inputs(tmp_path, calls=3)
    bundle = produce_production_chat_resource_provisioning_bundle(
        installation, "chat-resource", **artifacts)
    first_owner = load_production_chat_resource_context_owner(
        installation, "chat-resource", clock=lambda: NOW,
        nonce_source=lambda: "first-process-nonce")
    attempt_id = first_owner.allocator.final_gate(
        allocation=first_owner.allocation,
        principal=first_owner.principal,
        authenticated=first_owner.authenticated,
        current=first_owner.current,
        policy=first_owner.policy,
        current_time=NOW,
        durable_attempt_nonce="crash-before-backend-entry")
    assert first_owner.allocator.ledger.remaining_calls(
        bundle.allocation_id) == 2
    begun_attempt_id = first_owner.allocator.final_gate(
        allocation=first_owner.allocation,
        principal=first_owner.principal,
        authenticated=first_owner.authenticated,
        current=first_owner.current,
        policy=first_owner.policy,
        current_time=NOW,
        durable_attempt_nonce="backend-entry-before-crash")
    first_owner.allocator.record_backend_entry(first_owner.allocation,
        begun_attempt_id, observed_at=NOW)
    assert first_owner.allocator.ledger.remaining_calls(
        bundle.allocation_id) == 1
    first_owner.close()

    recovered_owner = load_production_chat_resource_context_owner(
        installation, "chat-resource", clock=lambda: NOW,
        nonce_source=lambda: "recovered-process-nonce")
    try:
        ledger = recovered_owner.allocator.ledger
        assert ledger._state["attempts"][attempt_id]["status"] == "restored"
        recovery_receipt = next(receipt for receipt in ledger._state["receipts"]
            if receipt["attempt_id"] == attempt_id)
        assert recovery_receipt["state"] == "attempted_not_begun"
        assert recovery_receipt["resource_specific_measurement"][
            "generation_attempted"] is False
        assert recovery_receipt["resource_specific_measurement"][
            "call_units_consumed"] == 0
        assert recovery_receipt["resource_specific_measurement"][
            "invocation_outcome"] == "recovered_before_backend_entry"
        assert ledger._state["attempts"][begun_attempt_id]["status"] == "begun"
        assert any(receipt["attempt_id"] == begun_attempt_id
            and receipt["state"] == "attempt_begun"
            for receipt in ledger._state["receipts"])
        assert ledger.remaining_calls(bundle.allocation_id) == 2
    finally:
        recovered_owner.close()


def test_adapter_forwards_exact_context_and_ordinary_chat_arguments(monkeypatch, tmp_path):
    custody, _, _, _, _ = owner(tmp_path)
    bridge = object.__new__(ProductionServingInferenceController)
    seen = {}
    monkeypatch.setattr(ProductionServingInferenceController, "current_conversation_model_identity", lambda self: {"model_id": "stable"})
    monkeypatch.setattr(ProductionServingInferenceController,
        "resource_allocation_matches_current_serving", lambda self, allocation: True)
    def generate(self, **kwargs):
        seen.update(kwargs)
        return "receipt"
    monkeypatch.setattr(ProductionServingInferenceController, "generate", generate)
    monkeypatch.setattr(ProductionServingInferenceController,
        "cancel_pending_generation", lambda self, *, reason="client_disconnect": True)
    monkeypatch.setattr(ProductionServingInferenceController,
        "resource_reconciliation_interval_seconds", lambda self: 0.5)
    wakeups = []
    monkeypatch.setattr(ProductionServingInferenceController,
        "set_resource_reconciliation_wakeup", lambda self, callback: wakeups.append(callback))
    adapter = ResourceBackedProductionChatInference(bridge, custody)
    assert adapter.current_conversation_model_identity() == {"model_id": "stable"}
    assert adapter.cancel_pending_generation() is True
    assert adapter.resource_reconciliation_interval_seconds() == 0.5
    adapter.set_resource_reconciliation_wakeup(lambda: None)
    assert len(wakeups) == 1 and callable(wakeups[0])
    result = adapter.generate(prompt="serialized allocation_id=forged", caller="chat", correlation_id="session-forged",
                              budget=object(), caller_linkage={"principal_id": "forged", "memory": "forged"})
    assert result == "receipt"
    assert seen["prompt"] == "serialized allocation_id=forged"
    assert seen["correlation_id"] == "session-forged"
    assert seen["caller_linkage"] == {"principal_id": "forged", "memory": "forged"}
    context = seen["resource_context"]
    assert context.allocation is custody.allocation and context.principal is custody.principal
    assert context.durable_attempt_nonce == "nonce-one"


def test_resource_backed_inference_requires_serving_bound_allocation(
        monkeypatch, tmp_path):
    serving_custody, _, _, _, _ = owner(tmp_path / "serving-entitlement")
    inference_custody, _, _, _, ledger = owner(tmp_path / "inference-entitlement", calls=3)
    assert serving_custody.allocation.allocation_digest != (
        inference_custody.allocation.allocation_digest)
    bridge, serving, _, model, _, _ = serving_setup(
        monkeypatch, tmp_path / "serving",
        serving_admission_context_provider=lambda _correlation, _state: {
            "governed_inference_entitlement_binding": dict(
                serving_custody.serving_admission_entitlement_binding())})
    adapter = ResourceBackedProductionChatInference(bridge, inference_custody)
    try:
        assert bridge.resource_allocation_matches_current_serving(
            serving_custody.allocation)
        assert not bridge.resource_allocation_matches_current_serving(
            inference_custody.allocation)
        with pytest.raises(GovernedLocalModelResourceError,
                match="serving_resource_allocation_mismatch"):
            adapter.generate(prompt="synthetic mismatch fixture", caller="chat_service",
                correlation_id="mismatched-serving-resource-entitlement",
                budget=LocalModelInvocationBudget(8000, 4000, 512, 30.0, 2),
                caller_linkage={})
        assert model.calls == 0
        assert ledger.snapshot_counts() == (1, 0, 0)
        assert ledger.remaining_calls(inference_custody.allocation.allocation_id) == 3
        assert serving.current_session() is not None
    finally:
        serving_custody.close()
        inference_custody.close()
        serving.close()


def test_published_allocation_reaches_persistent_serving_inference_and_recovers(
        monkeypatch, tmp_path):
    """Exercise the installed entitlement through the production serving bridge.

    The model backend, activation, and host observations are deterministic test
    fixtures. This proves software admission/custody/debit linkage, not hardware
    scheduling, GPU control, or observed host pressure.
    """
    installation, artifacts = provisioning_inputs(tmp_path / "provisioning")
    produced = produce_production_chat_resource_provisioning_bundle(
        installation, "runtime-invocation", **artifacts)
    resource_owner = load_production_chat_resource_context_owner(
        installation, "runtime-invocation", clock=lambda: NOW,
        nonce_source=lambda: "runtime-invocation-attempt")
    bridge = serving = None
    try:
        bridge, serving, session, model, kernel, _ = serving_setup(
            monkeypatch, tmp_path / "serving",
            installation_identity=installation.identity.value,
            state_root=tmp_path / "serving-state",
            serving_admission_context_provider=lambda _correlation, _activation: {
                "governed_inference_entitlement_binding": dict(
                    resource_owner.serving_admission_entitlement_binding())})
        inference = ResourceBackedProductionChatInference(bridge, resource_owner)
        receipt = inference.generate(
            prompt="synthetic persistent chat request",
            caller="persistent_chat_service",
            correlation_id="published-runtime-resource-call",
            budget=LocalModelInvocationBudget(100, 200, 8, 5.0, 2),
            caller_linkage={},
        )

        assert receipt.status == "admitted_completed"
        assert receipt.output_text == "answer"
        assert model.calls == 1
        assert receipt.resource_allocation_digest == resource_owner.allocation.allocation_digest
        assert receipt.request["linkage"]["serving_session_id"] == session.session_id
        valid, findings = validate_receipt(receipt.to_dict())
        assert valid, findings
        admitted_classes = [request.authority_class for request in kernel.requests]
        assert AuthorityClass.MODEL_SERVING in admitted_classes
        assert admitted_classes[-1] == AuthorityClass.LOCAL_MODEL_INFERENCE
        assert resource_owner.allocator.ledger.snapshot_counts() == (1, 1, 3)
        assert resource_owner.allocator.ledger.remaining_calls(produced.allocation_id) == 1

        durable = bridge._serving._handle.read_regular_bounded(
            bridge._serving._handle.fixed_object(
                f"local-model/inference/receipts/{receipt.receipt_id}.json"),
            max_bytes=1_048_576)
        durable_receipt = json.loads(durable.decode("utf-8"))
        assert durable_receipt["receipt_digest"] == receipt.receipt_digest
        assert durable_receipt["resource_allocation_digest"] == (
            produced.allocation_digest)

        resource_owner.close()
        recovered_owner = load_production_chat_resource_context_owner(
            installation, "runtime-invocation", clock=lambda: NOW,
            nonce_source=lambda: "recovered-runtime-attempt")
        try:
            assert recovered_owner.allocation.allocation_digest == (
                produced.allocation_digest)
            assert recovered_owner.allocator.ledger.snapshot_counts() == (1, 1, 3)
            assert recovered_owner.allocator.ledger.remaining_calls(
                produced.allocation_id) == 1
            records = resource_consumption_world_state_records(
                ledger=recovered_owner.allocator.ledger,
                invocation_receipts=(durable_receipt,))
            assert len(records) == 1
            assert not records[0]["payload"]["lineage_findings"]
        finally:
            recovered_owner.close()
    finally:
        resource_owner.close()
        if serving is not None:
            serving.close()

def test_duplicate_nonce_and_exhaustion_fail_without_retry_or_backend_generation(tmp_path):
    custody, model, invoker, request, ledger = owner(tmp_path, calls=2, nonces=["same", "same"])
    first = invoker.invoke(request, resource_context=custody.next_context())
    request2 = invoker.build_request(purpose="local_user_chat", prompt="different", caller="test",
                                     correlation_id="different-correlation", budget=request.budget)
    second = invoker.invoke(request2, resource_context=custody.next_context())
    assert first.status == "admitted_completed"
    assert second.status == "resource_denied"
    assert "resource_gate:duplicate_attempt_id" in second.reason_codes
    assert model.calls == 1 and ledger.remaining_calls(custody.allocation.allocation_id) == 1


def test_entitlement_observation_is_owner_minted_current_and_kernel_retained(
        monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    ledger_owner_lock = Lock()
    ledger_owner_lock.__enter__()
    custody, model, invoker, request, ledger = owner(tmp_path, calls=1,
        ledger_owner_lock=ledger_owner_lock)
    fixed_now = datetime.fromisoformat(NOW.replace("Z", "+00:00"))
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    monkeypatch.setattr("sentientos.runtime_governor.datetime", FixedDateTime)
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    try:
        assert invoker.invoke(request, resource_context=custody.next_context()).status == (
            "admitted_completed")
        assert ledger.remaining_calls(custody.allocation.allocation_id) == 0
        observation = custody.current_entitlement_observation()
        assert observation.remaining_call_entitlement == 0
        assert custody.verifies_current_entitlement_observation(observation)
        assert governor.observe_governed_local_model_resource_entitlement(observation)
        assert kernel.observe_governed_local_model_resource_entitlement(
            custody, observation) is True
        assert kernel.observe_governed_local_model_resource_entitlement(
            custody, replace(observation)) is False
        newer = custody.current_entitlement_observation()
        assert kernel.observe_governed_local_model_resource_entitlement(
            custody, observation) is False
        assert kernel.observe_governed_local_model_resource_entitlement(
            custody, newer) is True
        session_id = "serving-session-" + "a" * 24
        binding = {key: getattr(newer, key) for key in (
            "allocation_id", "allocation_digest", "allocator_id", "resource_kind",
            "policy_digest", "policy_epoch", "principal_binding_digest")}
        binding["binding_scope"] = "inference_call_entitlement"
        release_metadata = {
            "purpose": "local_model_resource_release",
            "reason_code": "governed_call_entitlement_exhausted",
            "target_subsystem": "production_chat",
            "serving_session_id": session_id,
            "model_identity_digest": "d" * 64,
            "serving_entitlement_binding": binding,
            "resource_observation": {
                "schema_version": (
                    "sentientos.production_local_model_resource_entitlement_release_evidence:v2"),
                "serving_session_id": session_id,
                "resource_entitlement_observation": newer.to_dict(),
            },
        }
        release = governor._admit_local_model_resource_release(
            actor="production_chat_resource_entitlement_governor",
            subject="production_chat_resource_entitlement_governor",
            correlation_id="resource-entitlement-exhausted-" + newer.observation_id,
            metadata=release_metadata)
        assert release.allowed is True
        forged_release = dict(release_metadata)
        forged_release["resource_observation"][
            "resource_entitlement_observation"] = {
                **newer.to_dict(), "remaining_call_entitlement": 1}
        forged = governor._admit_local_model_resource_release(
            actor="production_chat_resource_entitlement_governor",
            subject="production_chat_resource_entitlement_governor",
            correlation_id="forged-entitlement-release", metadata=forged_release)
        assert forged.allowed is False
        assert model.calls == 1
    finally:
        custody.close()


@pytest.mark.parametrize(("calls", "release_time", "expected_trigger", "expected_status",
    "expected_invalidation"), [
    (1, NOW, "call_entitlement_exhausted", "exhausted", None),
    (2, "2026-09-21T09:00:00Z", "resource_entitlement_invalidated",
        "invalidated", "allocation_expired"),
    (2, "2026-09-21T09:16:00Z", "resource_entitlement_invalidated",
        "invalidated", "policy_expired"),
    (2, "2026-09-21T09:30:00Z", "resource_entitlement_invalidated",
        "invalidated", "currentness_stale"),
])
def test_governed_entitlement_release_closes_idle_session_through_runtime(
        monkeypatch, tmp_path, calls, release_time, expected_trigger, expected_status,
        expected_invalidation):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    fixed_now = datetime.fromisoformat(NOW.replace("Z", "+00:00"))

    current_time = {"value": NOW}

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime.fromisoformat(current_time["value"].replace("Z", "+00:00"))
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr("sentientos.runtime_governor.datetime", FixedDateTime)
    installation, artifacts = provisioning_inputs(tmp_path / "serving", calls=calls)
    bounds = GovernedLocalModelResourceBounds(8000, 4000, 512, 30.0, calls)
    policy = GovernedLocalModelResourcePolicy.create(
        epoch=1, max_resource_specific_bounds=bounds,
        not_before="2026-09-21T08:00:00Z", valid_until="2026-09-21T09:15:00Z")
    artifacts["requested_bounds"] = bounds
    artifacts["resource_policy_artifact"] = encoded(policy.to_dict())
    bundle = produce_production_chat_resource_provisioning_bundle(
        installation, "entitlement-release", **artifacts)
    custody = load_production_chat_resource_context_owner(
        installation, "entitlement-release", clock=lambda: current_time["value"],
        nonce_source=lambda: "one-entitled-call")
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    bridge, serving, _, model, _, _ = serving_setup(
        monkeypatch, tmp_path / "serving", installation_identity="production",
        kernel_override=kernel,
        preflight_clock=lambda: current_time["value"],
        serving_admission_context_provider=lambda _correlation, _state: {
            "governed_inference_entitlement_binding":
                dict(custody.serving_admission_entitlement_binding())})
    inference = ResourceBackedProductionChatInference(bridge, custody)
    try:
        receipt = inference.generate(prompt="synthetic fixture prompt",
            caller="chat_service", correlation_id="entitlement-release-call",
            budget=LocalModelInvocationBudget(8000, 4000, 512, 30.0, calls),
            caller_linkage={})
        assert receipt.status == "admitted_completed"
        assert model.calls == 1
        assert custody.allocator.ledger.remaining_calls(bundle.allocation_id) == calls - 1

        current_time["value"] = release_time
        if expected_trigger == "resource_entitlement_invalidated":
            invalidation = custody.current_entitlement_observation()
            assert invalidation.entitlement_status == "invalidated"
            assert invalidation.invalidation_reason_code == expected_invalidation
            assert kernel.observe_governed_local_model_resource_entitlement(
                custody, invalidation) is True
            assert kernel.observe_governed_local_model_resource_entitlement(
                custody, replace(invalidation, invalidation_reason_code="forged")) is False

        released = inference.reconcile_workload_state()

        assert released["status"] == "worker_closed", released
        assert released["trigger_kind"] == expected_trigger
        assert serving.current_session() is None
        assert model.closed is True
        assert model.calls == 1
        receipt_path = (tmp_path / "serving" / "state" / "installations" / "production"
            / "state" / "local-model" / "serving" / "resource-release-receipts")
        release_receipts = list(receipt_path.glob("*.json"))
        assert len(release_receipts) == 1
        import json
        release = json.loads(release_receipts[0].read_text(encoding="utf-8"))
        assert release["resource_observation"][
            "resource_entitlement_observation"]["entitlement_status"] == expected_status
        assert release["resource_observation"][
            "resource_entitlement_observation"]["invalidation_reason_code"] == (
                expected_invalidation)
        assert release["resource_observation"]["host_telemetry_used_for_admission"] is False
        assert release["inference_performed"] is False
        assert release["host_mutation_performed"] is False
        observation_registry = InstallationStateRegistry(
            tmp_path / "serving" / "state", _test_only=True)
        read_only = observation_registry.open_read_only(
            InstallationIdentity.parse("production"))
        observed = ProductionChatResourceObservationOwner(
            read_only, "entitlement-release").observe()
        assert observed.verified_resource_release_receipts[0]["trigger_kind"] == (
            expected_trigger)
        assert observed.verified_resource_release_receipts[0]["resource_observation"][
            "resource_entitlement_observation"]["entitlement_status"] == expected_status
        serving_receipt_path = (tmp_path / "serving" / "state" / "installations"
            / "production" / "state" / "local-model" / "serving" / "receipts")
        serving_record = json.loads(next(serving_receipt_path.glob("*.json")).read_text(
            encoding="utf-8"))
        # Model the linkage fields added by the independent recovery observer.
        release.update({
            "serving_receipt_linkage_posture": "verified",
            "serving_receipt_id": serving_record["receipt_id"],
            "serving_receipt_semantic_digest": serving_record[
                "receipt_semantic_digest"],
            "invocation_linkage_posture": "not_required",
        })
        projected = resource_consumption_world_state_records(
            ledger=custody.allocator.ledger,
            verified_resource_release_receipts=[release])[0]
        projected_release = projected["payload"]["resource_release_receipts"][0]
        assert projected_release["resource_observation"][
            "resource_entitlement_observation"]["observation_id"] == (
                release["resource_observation"][
                    "resource_entitlement_observation"]["observation_id"])
        if expected_trigger == "call_entitlement_exhausted":
            from sentientos.local_model_authority import digest_payload

            legacy_release = json.loads(release_receipts[0].read_text(
                encoding="utf-8"))
            current_entitlement = legacy_release["resource_observation"][
                "resource_entitlement_observation"]
            legacy_entitlement = {key: current_entitlement[key] for key in (
                "allocation_id", "allocation_digest", "allocator_id", "resource_kind",
                "policy_digest", "policy_epoch", "principal_binding_digest",
                "remaining_call_entitlement", "checked_at")}
            legacy_entitlement["schema_version"] = (
                "sentientos.governed_local_model_resource_entitlement_observation:v1")
            legacy_digest = digest_payload(legacy_entitlement)
            legacy_entitlement["observation_id"] = "lmentitlement-" + legacy_digest[:24]
            legacy_entitlement["observation_digest"] = legacy_digest
            legacy_release["resource_observation"][
                "resource_entitlement_observation"] = legacy_entitlement
            admission_evidence = legacy_release["release_admission_record"][
                "delegated_outcomes"]["runtime_governor"]["evidence_refs"][
                    "resource_observation_evidence"]
            admission_evidence["resource_entitlement_observation"] = legacy_entitlement
            legacy_body = dict(legacy_release)
            legacy_body.pop("receipt_id", None)
            legacy_body.pop("receipt_semantic_digest", None)
            legacy_receipt_id = "serving-resource-release-" + hashlib.sha256(
                json.dumps(legacy_body, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()[:24]
            legacy_release["receipt_id"] = legacy_receipt_id
            legacy_release.pop("receipt_semantic_digest", None)
            legacy_release["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
                legacy_release, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
            legacy_path = receipt_path / (legacy_receipt_id + ".json")
            legacy_path.write_text(json.dumps(legacy_release, sort_keys=True,
                separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n",
                encoding="utf-8")
            legacy_snapshot = ProductionChatResourceObservationOwner(
                observation_registry.open_read_only(
                    InstallationIdentity.parse("production")),
                "entitlement-release").observe()
            recovered_legacy = next(item for item in
                legacy_snapshot.verified_resource_release_receipts
                if item["receipt_id"] == legacy_receipt_id)
            assert recovered_legacy["resource_observation"][
                "resource_entitlement_observation"]["schema_version"] == (
                    "sentientos.governed_local_model_resource_entitlement_observation:v1")
            legacy_projection_input = dict(recovered_legacy)
            legacy_projection_input.update({
                "serving_receipt_linkage_posture": "verified",
                "serving_receipt_id": serving_record["receipt_id"],
                "serving_receipt_semantic_digest": serving_record[
                    "receipt_semantic_digest"],
                "invocation_linkage_posture": "not_required",
            })
            legacy_projection = resource_consumption_world_state_records(
                ledger=custody.allocator.ledger,
                verified_resource_release_receipts=[legacy_projection_input])[0]
            assert legacy_projection["payload"]["resource_release_receipts"][0][
                "resource_observation"]["resource_entitlement_observation"][
                    "schema_version"] == (
                        "sentientos.governed_local_model_resource_entitlement_observation:v1")
    finally:
        custody.close()
        serving.close()


@pytest.mark.parametrize("workload_mode", ["normal", "automatic"])
def test_invalidated_entitlement_preempts_exact_active_invocation(
        monkeypatch, tmp_path, workload_mode):
    import json

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    current_time = {"value": NOW}

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime.fromisoformat(current_time["value"].replace("Z", "+00:00"))
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr("sentientos.runtime_governor.datetime", FixedDateTime)
    installation, artifacts = provisioning_inputs(tmp_path / "serving", calls=2)
    bounds = GovernedLocalModelResourceBounds(8000, 4000, 512, 30.0, 2)
    policy = GovernedLocalModelResourcePolicy.create(
        epoch=1, max_resource_specific_bounds=bounds,
        not_before="2026-09-21T08:00:00Z", valid_until="2026-09-21T09:15:00Z")
    artifacts["requested_bounds"] = bounds
    artifacts["resource_policy_artifact"] = encoded(policy.to_dict())
    bundle = produce_production_chat_resource_provisioning_bundle(
        installation, "active-entitlement-revoke", **artifacts)
    custody = load_production_chat_resource_context_owner(
        installation, "active-entitlement-revoke",
        clock=lambda: current_time["value"],
        nonce_source=lambda: "active-entitled-call")
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    started = Event()
    finish = Event()
    invocation_result = {}

    def active_generation():
        started.set()
        if not finish.wait(timeout=5):
            raise AssertionError("invalidated allocation did not preempt active worker")
        raise RuntimeError("fixture_generation_stopped_after_entitlement_invalidation")

    class NoGameDetector:
        def observe(self, _process_names):
            return ForegroundGameObservation("available", False, "a" * 64, NOW,
                game_process_running=False, running_process_name_digests=())

    bridge, serving, session, model, _, _ = serving_setup(
        monkeypatch, tmp_path / "serving", installation_identity="production",
        kernel_override=kernel, on_generate=active_generation,
        preflight_clock=lambda: current_time["value"],
        foreground_game_detector=NoGameDetector() if workload_mode == "automatic" else None,
        serving_admission_context_provider=lambda _correlation, _state: {
            "governed_inference_entitlement_binding":
                dict(custody.serving_admission_entitlement_binding())})
    model.cancel_pending_generation = lambda: (finish.set() or True)
    inference = ResourceBackedProductionChatInference(bridge, custody)
    if workload_mode == "automatic":
        inference.set_workload_mode("automatic", ["ExampleGame.exe"])

    def invoke():
        invocation_result["receipt"] = inference.generate(
            prompt="synthetic active entitlement fixture",
            caller="chat_service", correlation_id="active-entitlement-revocation",
            budget=LocalModelInvocationBudget(8000, 4000, 512, 30.0, 2),
            caller_linkage={})

    invocation_thread = Thread(target=invoke)
    try:
        invocation_thread.start()
        assert started.wait(timeout=5)
        assert bridge._active_invoker is not None
        assert bridge._active_invoker.backend_work_pending()

        # The call was already admitted and debited. Revoking the allocation
        # while its worker is still active should cancel that exact worker,
        # without releasing the resident serving session or another process.
        current_time["value"] = "2026-09-21T09:00:00Z"
        invalidation = custody.current_entitlement_observation()
        assert invalidation.entitlement_status == "invalidated"
        assert invalidation.invalidation_reason_code == "allocation_expired"
        reconciled = inference.reconcile_workload_state()
        assert reconciled["status"] == "preempted", reconciled
        assert reconciled["trigger_kind"] == (
            "resource_entitlement_invalidated_active_inference_preemption")
        assert reconciled["active_inference_cancellation_confirmed"] is True
        invocation_thread.join(timeout=5)
        assert not invocation_thread.is_alive()

        receipt = invocation_result["receipt"]
        assert receipt.status == "cancelled"
        assert receipt.cancellation_preemption_ref is not None
        assert receipt.cancellation_admission_decision is not None
        assert receipt.cancellation_admission_decision["actor"] == (
            "production_chat_resource_entitlement_governor")
        assert receipt.cancellation_admission_decision["delegated_outcomes"][
            "runtime_governor"]["reason"] == (
                "allowed_resource_entitlement_invalidation_inference_preemption")
        assert receipt.cancellation_admission_decision["delegated_outcomes"][
            "runtime_governor"]["evidence_refs"]["resource_entitlement_evidence"][
                "observation_digest"] == invalidation.observation_digest
        from sentientos.control_plane_kernel import (
            AuthorityClass, ControlActionRequest, LifecyclePhase,
        )
        active_reference = {key: receipt.request[key] for key in (
            "request_id", "request_digest", "correlation_id")}
        forged_preemption = dict(receipt.cancellation_admission_decision[
            "delegated_outcomes"]["runtime_governor"]["evidence_refs"][
                "active_inference_preemption"])
        forged_preemption["resource_entitlement_observation_digest"] = "0" * 64
        reference_digest = hashlib.sha256(json.dumps(active_reference,
            sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8")).hexdigest()
        forged_decision = kernel.admit(ControlActionRequest(
            action_kind="local_model_inference_preemption",
            authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE,
            actor="production_chat_resource_entitlement_governor",
            target_subsystem="governed_local_model_invocation",
            requested_phase=LifecyclePhase.RUNTIME,
            metadata={"correlation_id": "active-inference-preemption:"
                + reference_digest + ":forged-entitlement-digest",
                "purpose": "local_user_chat",
                "resource_entitlement_observation_id": invalidation.observation_id,
                "active_inference_preemption": forged_preemption,
                "active_inference_request_reference": active_reference}))
        assert forged_decision.allowed is False
        assert forged_decision.delegated_outcomes["runtime_governor"]["reason"] == (
            "deferred_active_inference_preemption_game_evidence_unavailable")
        assert validate_receipt(receipt.to_dict())[0] is True
        assert serving.current_session() == session
        assert model.calls == 1 and model.closed is False
        assert custody.allocator.ledger.remaining_calls(bundle.allocation_id) == 1
        attempts = list(custody.allocator.ledger._state["attempts"].values())
        assert len(attempts) == 1
        assert [item["state"] for item in custody.allocator.ledger._state["receipts"]] == [
            "attempt_begun", "measured_cancelled", "reconciled"]
        durable_path = (serving._handle.root / "local-model" / "inference"
            / "receipts" / f"{receipt.receipt_id}.json")
        durable = json.loads(durable_path.read_text(encoding="utf-8"))
        assert durable["cancellation_preemption_ref"] == dict(
            receipt.cancellation_preemption_ref)
        observed = ProductionChatResourceObservationOwner(
            InstallationStateRegistry(tmp_path / "serving" / "state",
                _test_only=True).open_read_only(
                    InstallationIdentity.parse("production")),
            "active-entitlement-revoke").observe()
        assert observed.invocation_receipts[0]["cancellation_preemption_ref"] == dict(
            receipt.cancellation_preemption_ref)
        projected = resource_consumption_world_state_records(
            ledger=custody.allocator.ledger,
            invocation_receipts=observed.invocation_receipts)[0]
        projected_invocation = projected["payload"]["invocation_receipts"][0]
        assert projected_invocation["receipt_id"] == receipt.receipt_id
        assert projected_invocation["cancellation_preemption_ref"] == dict(
            receipt.cancellation_preemption_ref)
        assert projected_invocation["workload_preemption_admission_posture"] == (
            "verified_receipt_bound_kernel_record")
        assert not any(finding.startswith((
            "workload_preemption_admission_linkage_missing:",
            "workload_preemption_admission_decision_unverified:"))
            for finding in projected["payload"]["lineage_findings"])
        released = inference.reconcile_workload_state()
        assert released["status"] == "worker_closed", released
        assert released["trigger_kind"] == "resource_entitlement_invalidated"
        assert serving.current_session() is None
        assert model.closed is True
        release_observation = ProductionChatResourceObservationOwner(
            InstallationStateRegistry(tmp_path / "serving" / "state",
                _test_only=True).open_read_only(
                    InstallationIdentity.parse("production")),
            "active-entitlement-revoke").observe()
        release = release_observation.verified_resource_release_receipts[0]
        release_entitlement = release["resource_observation"][
            "resource_entitlement_observation"]
        cancellation_evidence = receipt.cancellation_admission_decision[
            "delegated_outcomes"]["runtime_governor"]["evidence_refs"][
                "resource_entitlement_evidence"]
        assert release_entitlement["observation_id"] == invalidation.observation_id
        assert release_entitlement["observation_digest"] == invalidation.observation_digest
        assert cancellation_evidence["observation_digest"] == (
            release_entitlement["observation_digest"])
        release_projection = resource_consumption_world_state_records(
            ledger=custody.allocator.ledger,
            invocation_receipts=release_observation.invocation_receipts,
            verified_resource_release_receipts=(
                release_observation.verified_resource_release_receipts))[0]
        projected_release = release_projection["payload"][
            "resource_release_receipts"][0]
        assert projected_release["entitlement_preemption_linkage_posture"] == (
            "verified")
        assert projected_release["entitlement_preemption_invocation_receipt_id"] == (
            receipt.receipt_id)
        assert projected_release["entitlement_preemption_invocation_receipt_digest"] == (
            receipt.receipt_digest)
        assert projected_release["entitlement_preemption_ref"] == dict(
            receipt.cancellation_preemption_ref)
        assert not any(finding.startswith(
            "resource_release_entitlement_preemption_")
            for finding in release_projection["payload"]["lineage_findings"])
    finally:
        finish.set()
        invocation_thread.join(timeout=5)
        custody.close()
        serving.close()


def test_two_contexts_conserve_one_allocation_and_stale_currentness_fails_closed(tmp_path):
    custody, model, invoker, request, ledger = owner(tmp_path / "two", calls=2)
    assert invoker.invoke(request, resource_context=custody.next_context()).status == "admitted_completed"
    request2 = invoker.build_request(purpose="local_user_chat", prompt="second", caller="test",
                                     correlation_id="second-correlation", budget=request.budget)
    assert invoker.invoke(request2, resource_context=custody.next_context()).status == "admitted_completed"
    attempts = tuple(ledger._state["attempts"])
    assert len(attempts) == 2 and attempts[0] != attempts[1]
    assert ledger.remaining_calls(custody.allocation.allocation_id) == 0 and model.calls == 2

    stale, stale_model, stale_invoker, stale_request, stale_ledger = owner(
        tmp_path / "stale", clock=lambda: "2026-09-21T09:31:00Z")
    receipt = stale_invoker.invoke(stale_request, resource_context=stale.next_context())
    assert receipt.status == "resource_denied" and stale_model.calls == 0
    assert not stale_ledger._state["attempts"]


def test_persistent_chat_two_turns_use_one_preissued_allocation_without_storage_contamination(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime.fromisoformat(NOW.replace("Z", "+00:00"))
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr("sentientos.runtime_governor.datetime", FixedDateTime)
    installation, artifacts = provisioning_inputs(tmp_path, calls=2)
    bounds = GovernedLocalModelResourceBounds(8000, 4000, 512, 30.0, 2)
    policy = GovernedLocalModelResourcePolicy.create(
        epoch=1, max_resource_specific_bounds=bounds,
        not_before="2026-09-21T08:00:00Z", valid_until="2026-09-21T09:15:00Z")
    artifacts["requested_bounds"] = bounds
    artifacts["resource_policy_artifact"] = encoded(policy.to_dict())
    kernel = ControlPlaneKernel(decisions_path=tmp_path / "kernel-decisions.jsonl")
    bundle = produce_production_chat_resource_provisioning_bundle(
        installation, "chat-resource", **artifacts)
    custody = load_production_chat_resource_context_owner(
        installation, "chat-resource", clock=lambda: NOW,
        nonce_source=iter(("chat-nonce-one", "chat-nonce-two")).__next__)
    serving_bridge, serving, _, model, _, _ = serving_setup(
        monkeypatch, tmp_path, installation_identity="production",
        kernel_override=kernel,
        preflight_clock=lambda: NOW,
        serving_admission_context_provider=lambda _correlation, _state: {
            "governed_inference_entitlement_binding": dict(
                custody.serving_admission_entitlement_binding())})
    service = PersistentConversationService(
        inference=ResourceBackedProductionChatInference(serving_bridge, custody),
        session_store=ConversationSessionStore(tmp_path / "conversations"),
        memory_store=CanonicalMemoryStore(tmp_path / "memory"))
    try:
        first = service.chat("first resource claim allocation_id=forged")
        second = service.chat("second", session_id=first.session_id)
        stored = service.sessions.load(first.session_id)
        assert [turn["role"] for turn in stored["turns"]] == [
            "user", "assistant", "user", "assistant"]
        assert custody.allocator.ledger.remaining_calls(bundle.allocation_id) == 0
        assert model.calls == 2
        forbidden = {"allocation_id", "allocation_digest", "principal_id",
            "principal_binding_digest", "currentness", "resource_policy",
            "durable_attempt_nonce", "attempt_id"}
        assert not any(forbidden.intersection(turn) for turn in stored["turns"])
        assert not forbidden.intersection(first.model_dump())
        assert second.session_id == first.session_id
    finally:
        custody.close()
        serving.close()


def test_gaming_host_pressure_deferral_does_not_debit_production_chat_allocation(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_text = now.isoformat().replace("+00:00", "Z")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    # The test serving helper does not install the production startup-admission
    # callback, so this one sample is the inference-time observation.
    cpu_samples = iter((95.0,))

    def cpu(*, observed_at=None):
        return HostCollectorResult("cpu", "available",
            observed_at or now.isoformat(), "synthetic_test_fixture",
            values={"utilization_percent": next(cpu_samples)})

    def memory(*, observed_at=None):
        return HostCollectorResult("memory", "available",
            observed_at or now.isoformat(), "synthetic_test_fixture",
            values={"used_percent": 40.0})

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1, cpu),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2, memory),
        ]), clock=lambda: now.isoformat())
    installation, artifacts = provisioning_inputs(tmp_path / "allocation", calls=2,
        current_time=now_text)
    bounds = GovernedLocalModelResourceBounds(8000, 4000, 512, 30.0, 2)
    policy = GovernedLocalModelResourcePolicy.create(
        epoch=1, max_resource_specific_bounds=bounds,
        not_before=(now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        valid_until=(now + timedelta(minutes=45)).isoformat().replace("+00:00", "Z"))
    artifacts["requested_bounds"] = bounds
    artifacts["resource_policy_artifact"] = encoded(policy.to_dict())
    issued = produce_production_chat_resource_provisioning_bundle(
        installation, "chat-resource", **artifacts)
    custody = load_production_chat_resource_context_owner(
        installation, "chat-resource", clock=lambda: now_text,
        nonce_source=lambda: "gaming-pressure-call")
    serving_bridge, serving, _, backend, _, _ = serving_setup(
        monkeypatch, tmp_path / "serving", kernel_override=kernel,
        host_resource_observation_owner=host_owner,
        serving_admission_context_provider=lambda _correlation, _state: {
            "governed_inference_entitlement_binding": dict(
                custody.serving_admission_entitlement_binding())})
    adapter = ResourceBackedProductionChatInference(serving_bridge, custody)
    service = PersistentConversationService(
        inference=adapter,
        session_store=ConversationSessionStore(tmp_path / "conversations"),
        memory_store=CanonicalMemoryStore(tmp_path / "memory"))
    serving_bridge.set_workload_mode("gaming")

    try:
        response = service.chat("hello")

        assert response.context["response_origin"] == "deterministic_grounding_policy"
        assert "selected gaming workload profile" in response.response
        assert "no model reply was generated" in response.response
        assert backend.calls == 0
        assert custody.allocator.ledger.remaining_calls(issued.allocation_id) == 2
        stored = service.sessions.load(response.session_id)
        assistant = next(turn for turn in stored["turns"]
            if turn.get("turn_id") == response.turn_id)
        decision = assistant["linkage"]["policy_decision"]["payload"]
        assert decision["policy_id"] == "governed_model_resource_policy:v1"
        assert decision["reason_code"] == (
            "deferred_local_model_inference_under_host_pressure_in_gaming_mode")
        resource_evidence = decision["evidence"]["governed_resource_admission"]
        assert resource_evidence["status"] == "deferred_before_model_effect"
        assert resource_evidence["model_inference_performed"] is False
        assert resource_evidence["host_resource_observation"]["pressure_labels"] == [
            "cpu_pressure"]
        assert resource_evidence["host_resource_observation"]["no_effect_authority"] is True
    finally:
        custody.close()
        serving.close()


def test_game_frame_pressure_defers_production_chat_without_debit_then_recovers(
        monkeypatch, tmp_path):
    """Carry verified game pacing through serving admission and the resource ledger."""
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_text = now.isoformat().replace("+00:00", "Z")

    def collector(collector_id, values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", {"utilization_percent": 20.0})),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", {"used_percent": 40.0})),
        ]), clock=lambda: now.isoformat())
    installation, artifacts = provisioning_inputs(tmp_path / "allocation", calls=2,
        current_time=now_text)
    bounds = GovernedLocalModelResourceBounds(8000, 4000, 512, 30.0, 2)
    policy = GovernedLocalModelResourcePolicy.create(
        epoch=1, max_resource_specific_bounds=bounds,
        not_before=(now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        valid_until=(now + timedelta(minutes=45)).isoformat().replace("+00:00", "Z"))
    artifacts["requested_bounds"] = bounds
    artifacts["resource_policy_artifact"] = encoded(policy.to_dict())
    issued = produce_production_chat_resource_provisioning_bundle(
        installation, "chat-resource", **artifacts)
    custody = load_production_chat_resource_context_owner(
        installation, "chat-resource", clock=lambda: now_text,
        nonce_source=iter(("frame-pressure-call", "frame-recovery-call",
            "game-exit-call")).__next__)
    serving_bridge, serving, _, backend, _, _ = serving_setup(
        monkeypatch, tmp_path / "serving", kernel_override=kernel,
        host_resource_observation_owner=host_owner,
        serving_admission_context_provider=lambda _correlation, _state: {
            "governed_inference_entitlement_binding": dict(
                custody.serving_admission_entitlement_binding())})
    adapter = ResourceBackedProductionChatInference(serving_bridge, custody)
    serving_bridge.set_workload_mode("gaming")
    prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
        "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")

    def performance(sequence, message, p95, hitches):
        return VerifiedGamePerformanceObservation(
            "windows-edge", "windows-edge-generation-1", sequence, message * 64,
            ("a" if sequence == 1 else "b") * 64, now.isoformat(), "c" * 64,
            p95, hitches, 20.0, 4096, "available", now.isoformat())

    try:
        assert kernel.observe_verified_game_performance(
            performance(1, "d", 52.0, 1))
        deferred = adapter.generate(prompt=prompt, caller="chat_service",
            correlation_id="game-frame-pressure", budget=LocalModelInvocationBudget(),
            caller_linkage={})

        assert deferred.status == "deferred"
        assert deferred.effects["local_model_inference"] is False
        assert backend.calls == 0
        assert custody.allocator.ledger.remaining_calls(issued.allocation_id) == 2

        assert kernel.observe_verified_game_performance(
            performance(2, "e", 16.7, 0))
        # Better frame pacing does not mean optional inference may resume while
        # authenticated evidence still says the game is running. A newer
        # explicit game-exit observation from the same bridge generation does.
        game_exit_at = datetime.now(timezone.utc).isoformat()
        assert kernel.observe_verified_game_workload(ForegroundGameObservation(
            "available", False, "a" * 64, game_exit_at,
            game_process_running=False,
            transport_provenance={"message_id": "f" * 64,
                "source_id": "windows-edge", "session_id": "game-exit-session",
                "generation_id": "windows-edge-generation-1", "sequence": 1,
                "envelope_created_at": game_exit_at}))
        recovered = adapter.generate(prompt=prompt, caller="chat_service",
            correlation_id="game-frame-recovered", budget=LocalModelInvocationBudget(),
            caller_linkage={})

        assert recovered.status == "admitted_completed", recovered.reason_codes
        assert recovered.effects["local_model_inference"] is True
        assert backend.calls == 1
        assert custody.allocator.ledger.remaining_calls(issued.allocation_id) == 1
        admitted = recovered.request["linkage"]["host_resource_observation"]
        assert admitted["pressure_labels"] == ["nominal"]
    finally:
        custody.close()
        serving.close()
