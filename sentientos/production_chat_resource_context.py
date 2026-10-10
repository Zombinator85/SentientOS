"""Trusted process-local resource custody for persistent production chat."""
from __future__ import annotations

from typing import Any, Callable, Mapping, cast

from .causal_resource_principal import CausalResourcePrincipal
from .causal_resource_principal_authentication import AuthenticatedRootPrincipalEvidence
from .causal_resource_principal_currentness import CurrentAuthenticatedRootPrincipalEvidence
from .governed_local_model_invocation import (
    GovernedLocalModelResourceInvocationContext,
    LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
)
from .governed_local_model_resource_allocation import (
    GovernedLocalModelResourceAllocation,
    GovernedLocalModelResourceAllocator,
    GovernedLocalModelResourceError,
    GovernedLocalModelResourcePolicy,
)
from .local_model_serving_inference import ProductionServingInferenceController


class ProductionChatResourceContextOwner:
    """Hold one pre-existing, structurally bound resource entitlement bundle.

    Construction proves custody consistency only.  The allocator remains the
    authoritative currentness, validity, policy, and durable-debit gate.
    """

    __slots__ = (
        "allocator", "allocation", "principal", "authenticated", "current",
        "policy", "_nonce_source", "_clock", "_ledger_owner_lock",
    )

    def __init__(
        self,
        *,
        allocator: GovernedLocalModelResourceAllocator,
        allocation: GovernedLocalModelResourceAllocation,
        principal: CausalResourcePrincipal,
        authenticated: AuthenticatedRootPrincipalEvidence,
        current: CurrentAuthenticatedRootPrincipalEvidence,
        policy: GovernedLocalModelResourcePolicy,
        nonce_source: Callable[[], str],
        clock: Callable[[], str],
        ledger_owner_lock: Any | None = None,
    ) -> None:
        exact_types = (
            (allocator, GovernedLocalModelResourceAllocator),
            (allocation, GovernedLocalModelResourceAllocation),
            (principal, CausalResourcePrincipal),
            (authenticated, AuthenticatedRootPrincipalEvidence),
            (current, CurrentAuthenticatedRootPrincipalEvidence),
            (policy, GovernedLocalModelResourcePolicy),
        )
        if any(type(value) is not expected for value, expected in exact_types):
            raise TypeError("exact_production_chat_resource_types_required")
        if not callable(nonce_source) or not callable(clock):
            raise TypeError("trusted_nonce_source_and_clock_required")
        if allocator.policy != policy:
            raise GovernedLocalModelResourceError("owner_allocator_policy_mismatch")
        if allocator.ledger.allocation(allocation.allocation_id) != allocation:
            raise GovernedLocalModelResourceError("owner_allocation_not_exactly_stored")
        if not (allocation.principal_id == principal.principal_id == authenticated.principal_id == current.principal_id):
            raise GovernedLocalModelResourceError("owner_principal_id_mismatch")
        if not (allocation.principal_binding_digest == principal.binding_digest == authenticated.principal_binding_digest == current.principal_binding_digest):
            raise GovernedLocalModelResourceError("owner_principal_binding_mismatch")
        if not (allocation.principal_epoch == principal.epoch == current.epoch):
            raise GovernedLocalModelResourceError("owner_principal_epoch_mismatch")
        if not (principal.issuer_id == authenticated.issuer_id == current.issuer_id):
            raise GovernedLocalModelResourceError("owner_principal_issuer_mismatch")
        if authenticated.provenance_digest != current.provenance_digest:
            raise GovernedLocalModelResourceError("owner_provenance_mismatch")
        if allocation.policy_digest != policy.policy_digest or allocation.epoch != policy.epoch:
            raise GovernedLocalModelResourceError("owner_allocation_policy_mismatch")
        self.allocator = allocator
        self.allocation = allocation
        self.principal = principal
        self.authenticated = authenticated
        self.current = current
        self.policy = policy
        self._nonce_source = nonce_source
        self._clock = clock
        self._ledger_owner_lock = ledger_owner_lock

    @property
    def has_single_process_custody(self) -> bool:
        return self._ledger_owner_lock is not None

    def close(self) -> None:
        lock = self._ledger_owner_lock
        self._ledger_owner_lock = None
        if lock is not None:
            lock.__exit__(None, None, None)

    def next_context(self) -> GovernedLocalModelResourceInvocationContext:
        """Create one context from custody alone, with one fresh trusted nonce."""
        nonce = self._nonce_source()
        if type(nonce) is not str or not nonce:
            raise GovernedLocalModelResourceError("invalid_durable_attempt_nonce")
        return GovernedLocalModelResourceInvocationContext(
            allocator=self.allocator,
            allocation=self.allocation,
            principal=self.principal,
            authenticated=self.authenticated,
            current=self.current,
            policy=self.policy,
            durable_attempt_nonce=nonce,
            clock=self._clock,
        )


class ResourceBackedProductionChatInference:
    """Adapt ordinary chat inference to mandatory trusted resource custody."""

    __slots__ = ("_delegate", "_owner")

    def __init__(self, delegate: ProductionServingInferenceController,
                 owner: ProductionChatResourceContextOwner) -> None:
        if type(delegate) is not ProductionServingInferenceController:
            raise TypeError("exact_production_serving_inference_controller_required")
        if type(owner) is not ProductionChatResourceContextOwner:
            raise TypeError("exact_production_chat_resource_context_owner_required")
        self._delegate = delegate
        self._owner = owner

    def current_conversation_model_identity(self) -> Mapping[str, Any]:
        return cast(Mapping[str, Any], self._delegate.current_conversation_model_identity())

    def verify_stored_chat_invocation(self, *, receipt_id: str, receipt_digest: str,
                                     session_id: str, user_turn_id: str,
                                     assistant_text: str | None = None) -> Mapping[str, Any]:
        return self._delegate.verify_stored_chat_invocation(receipt_id=receipt_id,
            receipt_digest=receipt_digest, session_id=session_id, user_turn_id=user_turn_id,
            assistant_text=assistant_text)

    def generate(self, *, prompt: str, caller: str, correlation_id: str,
                 budget: LocalModelInvocationBudget,
                 caller_linkage: Mapping[str, Any]) -> LocalModelInvocationReceipt:
        context = self._owner.next_context()
        return self._delegate.generate(
            prompt=prompt,
            caller=caller,
            correlation_id=correlation_id,
            budget=budget,
            caller_linkage=caller_linkage,
            resource_context=context,
        )
