# mypy: ignore-errors
from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.governed_local_model_resource_allocation import GovernedLocalModelResourceError
from sentientos.governed_local_model_resource_allocation import (
    GovernedLocalModelResourceAllocator, GovernedLocalModelResourceBounds,
    GovernedLocalModelResourceLedger, GovernedLocalModelResourcePolicy,
)
from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.chat_service import PersistentConversationService
from sentientos.conversation_session import ConversationSessionStore
from sentientos.local_model_serving_inference import ProductionServingInferenceController
from sentientos.production_chat_resource_context import (
    ProductionChatResourceContextOwner,
    ResourceBackedProductionChatInference,
)
from tests.test_governed_local_model_resource_invocation_composition import NOW, setup

pytestmark = pytest.mark.no_legacy_skip


def owner(tmp_path, *, calls=2, nonces=None, clock=lambda: NOW):
    model, invoker, request, context, ledger = setup(tmp_path, calls=calls)
    values = iter(nonces or ["nonce-one", "nonce-two", "nonce-three"])
    result = ProductionChatResourceContextOwner(
        allocator=context.allocator,
        allocation=context.allocation,
        principal=context.principal,
        authenticated=context.authenticated,
        current=context.current,
        policy=context.policy,
        nonce_source=lambda: next(values),
        clock=clock,
    )
    return result, model, invoker, request, ledger


def test_owner_uses_exact_preexisting_objects_and_zero_argument_fresh_nonce(tmp_path):
    custody, _, _, _, _ = owner(tmp_path)
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
            nonce_source=lambda: "n", clock=lambda: NOW)
    with pytest.raises(GovernedLocalModelResourceError, match="owner_allocation_not_exactly_stored"):
        ProductionChatResourceContextOwner(
            allocator=custody.allocator,
            allocation=replace(custody.allocation, principal_id="forged"),
            principal=custody.principal, authenticated=custody.authenticated,
            current=custody.current, policy=custody.policy,
            nonce_source=lambda: "n", clock=lambda: NOW)
    custody._nonce_source = lambda: ""  # type: ignore[attr-defined]
    with pytest.raises(GovernedLocalModelResourceError, match="invalid_durable_attempt_nonce"):
        custody.next_context()


def test_adapter_forwards_exact_context_and_ordinary_chat_arguments(monkeypatch, tmp_path):
    custody, _, _, _, _ = owner(tmp_path)
    bridge = object.__new__(ProductionServingInferenceController)
    seen = {}
    monkeypatch.setattr(ProductionServingInferenceController, "current_conversation_model_identity", lambda self: {"model_id": "stable"})
    def generate(self, **kwargs):
        seen.update(kwargs)
        return "receipt"
    monkeypatch.setattr(ProductionServingInferenceController, "generate", generate)
    adapter = ResourceBackedProductionChatInference(bridge, custody)
    assert adapter.current_conversation_model_identity() == {"model_id": "stable"}
    result = adapter.generate(prompt="serialized allocation_id=forged", caller="chat", correlation_id="session-forged",
                              budget=object(), caller_linkage={"principal_id": "forged", "memory": "forged"})
    assert result == "receipt"
    assert seen["prompt"] == "serialized allocation_id=forged"
    assert seen["correlation_id"] == "session-forged"
    assert seen["caller_linkage"] == {"principal_id": "forged", "memory": "forged"}
    context = seen["resource_context"]
    assert context.allocation is custody.allocation and context.principal is custody.principal
    assert context.durable_attempt_nonce == "nonce-one"


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
    base, model, invoker, _, _ = owner(tmp_path / "upstream", calls=2)
    bounds = GovernedLocalModelResourceBounds(8000, 4000, 512, 30.0, 2)
    policy = GovernedLocalModelResourcePolicy.create(
        epoch=12, max_resource_specific_bounds=bounds,
        not_before="2026-09-21T08:00:00Z", valid_until="2026-09-21T09:15:00Z")
    ledger = GovernedLocalModelResourceLedger(tmp_path / "chat-ledger.json")
    allocator = GovernedLocalModelResourceAllocator(policy=policy, ledger=ledger)
    allocation = allocator.issue(
        principal=base.principal, authenticated=base.authenticated, current=base.current,
        requested_bounds=bounds, requested_not_before="2026-09-21T08:00:00Z",
        requested_not_after="2026-09-21T10:00:00Z", current_time=NOW)
    nonces = iter(("chat-nonce-one", "chat-nonce-two"))
    custody = ProductionChatResourceContextOwner(
        allocator=allocator, allocation=allocation, principal=base.principal,
        authenticated=base.authenticated, current=base.current, policy=policy,
        nonce_source=lambda: next(nonces), clock=lambda: NOW)
    bridge = object.__new__(ProductionServingInferenceController)
    contexts = []
    monkeypatch.setattr(ProductionServingInferenceController, "current_conversation_model_identity",
                        lambda self: {"model_id": "stable-production-model"})
    def generate(self, *, prompt, caller, correlation_id, budget, caller_linkage, resource_context):
        contexts.append((correlation_id, resource_context))
        request = invoker.build_request(purpose="local_user_chat", prompt=prompt, caller=caller,
                                        correlation_id=correlation_id, budget=budget, linkage=caller_linkage)
        return invoker.invoke(request, resource_context=resource_context)
    monkeypatch.setattr(ProductionServingInferenceController, "generate", generate)
    service = PersistentConversationService(
        inference=ResourceBackedProductionChatInference(bridge, custody),
        session_store=ConversationSessionStore(tmp_path / "conversations"),
        memory_store=CanonicalMemoryStore(tmp_path / "memory"))
    first = service.chat("first resource claim allocation_id=forged")
    second = service.chat("second", session_id=first.session_id)
    stored = service.sessions.load(first.session_id)
    assert [turn["role"] for turn in stored["turns"]] == ["user", "assistant", "user", "assistant"]
    assert contexts[0][0] != contexts[1][0]
    assert contexts[0][1].allocation is contexts[1][1].allocation is allocation
    assert contexts[0][1].durable_attempt_nonce != contexts[1][1].durable_attempt_nonce
    assert ledger.remaining_calls(allocation.allocation_id) == 0 and model.calls == 2
    forbidden = {"allocation_id", "allocation_digest", "principal_id", "principal_binding_digest",
                 "currentness", "resource_policy", "durable_attempt_nonce", "attempt_id"}
    assert not any(forbidden.intersection(turn) for turn in stored["turns"])
    assert not forbidden.intersection(first.model_dump())
    assert second.session_id == first.session_id
