"""Trusted process-local resource custody for persistent production chat."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Mapping, cast

from .causal_resource_principal import CausalResourcePrincipal
from .causal_resource_principal_authentication import AuthenticatedRootPrincipalEvidence
from .causal_resource_principal_currentness import CurrentAuthenticatedRootPrincipalEvidence
from .governed_local_model_invocation import (
    GovernedLocalModelResourceCustodyLease,
    GovernedLocalModelResourceInvocationContext,
    LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
)
from .governed_local_model_resource_allocation import (
    GovernedLocalModelResourceAllocation,
    GovernedLocalModelResourceAllocator,
    GovernedLocalModelResourceConsumptionReceipt,
    GovernedLocalModelResourceError,
    GovernedLocalModelResourcePolicy,
)
from .installation_state import InstallationIdentity
from .local_model_authority import digest_payload
from .local_model_serving_inference import ProductionServingInferenceController


@dataclass(frozen=True, slots=True)
class GovernedLocalModelResourceEntitlementObservation:
    """One owner-minted, read-only snapshot of the current call entitlement."""

    allocation_id: str
    allocation_digest: str
    allocator_id: str
    resource_kind: str
    policy_digest: str
    policy_epoch: int
    principal_binding_digest: str
    remaining_call_entitlement: int
    entitlement_status: str
    invalidation_reason_code: str | None
    checked_at: str
    observation_id: str
    observation_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": (
                "sentientos.governed_local_model_resource_entitlement_observation:v2"),
            "allocation_id": self.allocation_id,
            "allocation_digest": self.allocation_digest,
            "allocator_id": self.allocator_id,
            "resource_kind": self.resource_kind,
            "policy_digest": self.policy_digest,
            "policy_epoch": self.policy_epoch,
            "principal_binding_digest": self.principal_binding_digest,
            "remaining_call_entitlement": self.remaining_call_entitlement,
            "entitlement_status": self.entitlement_status,
            "invalidation_reason_code": self.invalidation_reason_code,
            "checked_at": self.checked_at,
            "observation_id": self.observation_id,
            "observation_digest": self.observation_digest,
        }


class ProductionChatResourceContextOwner:
    """Hold one pre-existing, structurally bound resource entitlement bundle.

    Construction proves custody consistency only.  The allocator remains the
    authoritative currentness, validity, policy, and durable-debit gate.
    """

    __slots__ = (
        "allocator", "allocation", "principal", "authenticated", "current",
        "policy", "_installation_identity", "_provisioning_id", "_nonce_source",
        "_clock", "_ledger_owner_lock", "_closed", "_released", "_custody_lease",
        "_close_lock", "_last_entitlement_observation",
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
        installation_identity: str,
        provisioning_id: str,
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
        if not isinstance(provisioning_id, str) or not provisioning_id:
            raise GovernedLocalModelResourceError("owner_provisioning_identity_required")
        try:
            selected_installation = InstallationIdentity.parse(
                installation_identity).value
        except (TypeError, ValueError) as exc:
            raise GovernedLocalModelResourceError(
                "owner_installation_identity_invalid") from exc
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
        self._installation_identity = selected_installation
        self._provisioning_id = provisioning_id
        self._nonce_source = nonce_source
        self._clock = clock
        self._ledger_owner_lock = ledger_owner_lock
        self._closed = False
        self._released = False
        self._custody_lease = GovernedLocalModelResourceCustodyLease()
        self._close_lock = Lock()
        self._last_entitlement_observation: (
            GovernedLocalModelResourceEntitlementObservation | None) = None

    @property
    def has_single_process_custody(self) -> bool:
        return self._ledger_owner_lock is not None

    @property
    def installation_identity(self) -> str:
        return self._installation_identity

    @property
    def provisioning_id(self) -> str:
        return self._provisioning_id

    def close(self) -> None:
        with self._close_lock:
            if self._released:
                return
            self._begin_close_locked()
            self._custody_lease.wait_for_drain()
            lock = self._ledger_owner_lock
            self._ledger_owner_lock = None
            if lock is not None:
                lock.__exit__(None, None, None)
            self._released = True

    def begin_close(self) -> None:
        """Reject new resource-backed work before serving shutdown begins."""
        with self._close_lock:
            if self._closed:
                return
            self._begin_close_locked()

    def _begin_close_locked(self) -> None:
        self._closed = True
        self._custody_lease.stop_accepting()

    def _require_open(self) -> None:
        if self._closed:
            raise GovernedLocalModelResourceError("resource_context_owner_closed")

    def next_context(self) -> GovernedLocalModelResourceInvocationContext:
        """Create one context from custody alone, with one fresh trusted nonce."""
        self._require_open()
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
            custody_lease=self._custody_lease,
        )

    def recover_orphaned_provisional_attempts(self
            ) -> tuple[GovernedLocalModelResourceConsumptionReceipt, ...]:
        """Reconcile no-effect attempts while holding exclusive ledger custody."""
        self._require_open()
        if self._ledger_owner_lock is None:
            raise GovernedLocalModelResourceError(
                "resource_ledger_process_owner_required")
        self._custody_lease.acquire()
        try:
            self._require_open()
            observed_at = self._clock()
            if type(observed_at) is not str or not observed_at:
                raise GovernedLocalModelResourceError("invalid_current_time")
            return self.allocator._recover_orphaned_provisional_attempts(
                self.allocation, observed_at=observed_at)
        finally:
            self._custody_lease.release()

    def serving_admission_entitlement_binding(self) -> Mapping[str, object]:
        """Return a current call-entitlement reference without debiting a call.

        This proves that the resident model is serving under a live governed
        invocation entitlement. Its optional GPU layer ceiling applies to the
        configured layer count only; it does not reserve VRAM or exercise
        hardware-control authority.
        """
        self._require_open()
        self._custody_lease.acquire()
        try:
            return self._serving_admission_entitlement_binding()
        finally:
            self._custody_lease.release()

    def current_entitlement_observation(
            self) -> GovernedLocalModelResourceEntitlementObservation:
        """Mint evidence from the current allocation ledger while holding custody."""
        self._require_open()
        self._custody_lease.acquire()
        try:
            self._require_open()
            current_time = self._clock()
            if type(current_time) is not str or not current_time:
                raise GovernedLocalModelResourceError("invalid_current_time")
            try:
                allocation, remaining_calls = self.allocator.current_entitlement(
                    allocation=self.allocation,
                    principal=self.principal,
                    authenticated=self.authenticated,
                    current=self.current,
                    policy=self.policy,
                    current_time=current_time)
                entitlement_status = "exhausted" if remaining_calls == 0 else "current"
                invalidation_reason_code = None
            except GovernedLocalModelResourceError as exc:
                error_code = str(exc)
                if error_code not in {
                        "allocation_expired", "policy_expired", "currentness_stale",
                        "principal_expired", "allocation_not_current"}:
                    raise
                allocation = self.allocation
                remaining_calls = self.allocator.ledger.remaining_calls(
                    allocation.allocation_id)
                entitlement_status = "invalidated"
                invalidation_reason_code = error_code
            body: dict[str, object] = {
                "schema_version": (
                    "sentientos.governed_local_model_resource_entitlement_observation:v2"),
                "allocation_id": allocation.allocation_id,
                "allocation_digest": allocation.allocation_digest,
                "allocator_id": allocation.allocator_id,
                "resource_kind": allocation.resource_kind,
                "policy_digest": allocation.policy_digest,
                "policy_epoch": allocation.epoch,
                "principal_binding_digest": allocation.principal_binding_digest,
                "remaining_call_entitlement": remaining_calls,
                "entitlement_status": entitlement_status,
                "invalidation_reason_code": invalidation_reason_code,
                "checked_at": current_time,
            }
            observation_digest = digest_payload(body)
            observation = GovernedLocalModelResourceEntitlementObservation(
                allocation_id=allocation.allocation_id,
                allocation_digest=allocation.allocation_digest,
                allocator_id=allocation.allocator_id,
                resource_kind=allocation.resource_kind,
                policy_digest=allocation.policy_digest,
                policy_epoch=allocation.epoch,
                principal_binding_digest=allocation.principal_binding_digest,
                remaining_call_entitlement=remaining_calls,
                entitlement_status=entitlement_status,
                invalidation_reason_code=invalidation_reason_code,
                checked_at=current_time,
                observation_id="lmentitlement-" + observation_digest[:24],
                observation_digest=observation_digest)
            self._last_entitlement_observation = observation
            return observation
        finally:
            self._custody_lease.release()

    def verifies_current_entitlement_observation(self, observation: object) -> bool:
        """Verify the exact owner-minted entitlement snapshot remains valid."""
        if (type(observation) is not GovernedLocalModelResourceEntitlementObservation
                or observation is not self._last_entitlement_observation):
            return False
        try:
            self._require_open()
            self._custody_lease.acquire()
            try:
                self._require_open()
                current_time = self._clock()
                allocation, remaining_calls = self.allocator.current_entitlement(
                    allocation=self.allocation,
                    principal=self.principal,
                    authenticated=self.authenticated,
                    current=self.current,
                    policy=self.policy,
                    current_time=current_time)
            finally:
                self._custody_lease.release()
        except GovernedLocalModelResourceError as exc:
            error_code = str(exc)
            return (observation.entitlement_status == "invalidated"
                and observation.invalidation_reason_code == error_code
                and error_code in {"allocation_expired", "policy_expired",
                    "currentness_stale", "principal_expired", "allocation_not_current"}
                and observation.allocation_digest == self.allocation.allocation_digest
                and observation.policy_digest == self.allocation.policy_digest
                and observation.principal_binding_digest ==
                    self.allocation.principal_binding_digest)
        except (TypeError, ValueError):
            return False
        return (type(current_time) is str and bool(current_time)
            and observation.entitlement_status == (
                "exhausted" if remaining_calls == 0 else "current")
            and observation.invalidation_reason_code is None
            and allocation.allocation_digest == observation.allocation_digest
            and remaining_calls == observation.remaining_call_entitlement
            and allocation.policy_digest == observation.policy_digest
            and allocation.principal_binding_digest == observation.principal_binding_digest)

    def _serving_admission_entitlement_binding(self) -> Mapping[str, object]:
        current_time = self._clock()
        if type(current_time) is not str or not current_time:
            raise GovernedLocalModelResourceError("invalid_current_time")
        allocation, remaining_calls = self.allocator.current_entitlement(
            allocation=self.allocation,
            principal=self.principal,
            authenticated=self.authenticated,
            current=self.current,
            policy=self.policy,
            current_time=current_time)
        if remaining_calls <= 0:
            raise GovernedLocalModelResourceError("call_entitlement_exhausted")
        return {
            "schema_version": (
                "sentientos.governed_local_model_serving_entitlement_binding:v2"),
            "binding_scope": "inference_call_entitlement",
            "allocation_id": allocation.allocation_id,
            "allocation_digest": allocation.allocation_digest,
            "allocator_id": allocation.allocator_id,
            "resource_kind": allocation.resource_kind,
            "policy_digest": allocation.policy_digest,
            "policy_epoch": allocation.epoch,
            "principal_binding_digest": allocation.principal_binding_digest,
            "remaining_call_entitlement": remaining_calls,
            "max_gpu_layers": allocation.resource_specific_bounds.max_gpu_layers,
            "checked_at": current_time,
        }


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

    def set_workload_mode(self, mode: str,
                          game_process_names: tuple[str, ...] | list[str] = ()) -> str:
        return self._delegate.set_workload_mode(mode, game_process_names)

    def current_workload_mode(self) -> str:
        return self._delegate.current_workload_mode()

    def current_workload_state(self) -> Mapping[str, Any]:
        return self._delegate.current_workload_state()

    def reconcile_workload_state(self) -> Mapping[str, Any]:
        return self._delegate.reconcile_idle_game_resource_state(
            resource_entitlement_owner=self._owner)

    def resource_reconciliation_interval_seconds(self) -> float:
        return self._delegate.resource_reconciliation_interval_seconds()

    def set_resource_reconciliation_wakeup(self, callback: Any | None) -> None:
        self._delegate.set_resource_reconciliation_wakeup(callback)

    def cancel_pending_generation(self, *, reason: str = "client_disconnect") -> bool:
        return self._delegate.cancel_pending_generation(reason=reason)

    def verify_stored_chat_invocation(self, *, receipt_id: str, receipt_digest: str,
                                     session_id: str, user_turn_id: str,
                                     assistant_text: str | None = None,
                                     client_request_id_digest: str | None = None) -> Mapping[str, Any]:
        return self._delegate.verify_stored_chat_invocation(receipt_id=receipt_id,
            receipt_digest=receipt_digest, session_id=session_id, user_turn_id=user_turn_id,
            assistant_text=assistant_text,
            client_request_id_digest=client_request_id_digest)

    def inspect_interrupted_chat_invocation(self, *, session_id: str, user_turn_id: str,
                                             client_request_id_digest: str | None = None) -> Mapping[str, Any]:
        return self._delegate.inspect_interrupted_chat_invocation(
            session_id=session_id, user_turn_id=user_turn_id,
            client_request_id_digest=client_request_id_digest)

    def generate(self, *, prompt: str, caller: str, correlation_id: str,
                 budget: LocalModelInvocationBudget,
                 caller_linkage: Mapping[str, Any]) -> LocalModelInvocationReceipt:
        context = self._owner.next_context()
        if not self._delegate.resource_allocation_matches_current_serving(
                context.allocation):
            raise GovernedLocalModelResourceError(
                "serving_resource_allocation_mismatch")
        return self._delegate.generate(
            prompt=prompt,
            caller=caller,
            correlation_id=correlation_id,
            budget=budget,
            caller_linkage=caller_linkage,
            resource_context=context,
        )
