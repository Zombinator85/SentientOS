"""Read-only resident observation of installation-scoped production-chat custody.

The chat process remains the sole mutable ledger owner. This observer opens only
fixed authenticated installation objects and validates one atomically replaced
ledger image; it never constructs an allocator or ledger writer.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Mapping

from .causal_resource_principal import CausalResourcePrincipal
from .causal_resource_principal_authentication import (
    RootIssuerProvenanceVerifier,
    RootPrincipalIssuerProvenance,
)
from .causal_resource_principal_currentness import (
    PrincipalCurrentnessVerifier,
    ReadOnlyPrincipalRevocationRegistry,
)
from .causal_resource_principal_ed25519 import CryptographyEd25519RootIssuerSignatureVerifier
from .causal_resource_principal_trust_catalog import ReadOnlyTrustedIssuerCatalog
from .governed_local_model_invocation import validate_receipt
from .chat_process_generation import (
    ChatProcessGenerationError,
    read_stored_chat_process_runtime_observation,
    verify_stored_chat_process_handoff,
)
from .conversation_session import compact_runtime_generation_attribution
from .runtime.local_model_chat_recovery import (
    LocalModelChatRecoveryError,
    inspect_chat_recovery_phase_custody,
)
from .governed_local_model_resource_allocation import (
    GovernedLocalModelResourceAllocation,
    GovernedLocalModelResourceLedger,
    GovernedLocalModelResourceLedgerObservation,
    GovernedLocalModelResourcePolicy,
)
from .installation_state import (
    InstallationStateError, InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView,
)
from .local_model_production_serving import (
    ProductionServingError, read_serving_operation_attempts, read_serving_operation_history,
)
from .production_chat_resource_provisioning import (
    _NAMES,
    _manifest,
    _mapping,
    validate_resource_provisioning_id,
)

MAX_LEDGER_BYTES = 8 * 1024 * 1024
MAX_INVOCATION_RECEIPTS = 256
MAX_INVOCATION_RECEIPT_BYTES = 256 * 1024
_RECEIPT_NAME = re.compile(r"lmrec-[0-9a-f]{24}\.json\Z")
_RECEIPT_TEMP_NAME = re.compile(r"\.lmrec-[0-9a-f]{24}\.json\.[A-Za-z0-9_-]{1,64}\.tmp\Z")


class ProductionChatResourceObservationError(ValueError):
    """A selected installation source is absent or cannot be verified."""

    def __init__(self, code: str, *, status: str = "invalid") -> None:
        self.code = code
        self.status = status
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProductionChatResourceObservation:
    installation_identity: str
    provisioning_id: str
    manifest_digest: str
    ledger: GovernedLocalModelResourceLedgerObservation
    invocation_receipts: tuple[Mapping[str, Any], ...]
    invocation_receipt_posture: str
    chat_process_generation_attributions: tuple[Mapping[str, Any], ...] = ()
    chat_process_generation_posture: str = "unknown"
    chat_process_recovery_transitions: tuple[Mapping[str, Any], ...] = ()
    chat_process_recovery_posture: str = "unknown"
    chat_process_runtime_observation: Mapping[str, Any] | None = None
    chat_process_runtime_observation_posture: str = "unknown"
    serving_operation_attempts: tuple[Mapping[str, Any], ...] = ()
    serving_operation_attempt_posture: str = "unknown"
    serving_operation_history: tuple[Mapping[str, Any], ...] = ()


class ProductionChatResourceObservationOwner:
    """Explicit read-only selector for one preconfigured installation bundle."""

    __slots__ = ("_handle", "_provisioning_id")

    def __init__(self,
                 handle: InstallationStateReadOnlyView | WindowsInstallationStateReadOnlyView,
                 provisioning_id: str) -> None:
        if type(handle) not in (InstallationStateReadOnlyView, WindowsInstallationStateReadOnlyView):
            raise TypeError("read_only_installation_state_view_required")
        self._handle = handle
        self._provisioning_id = validate_resource_provisioning_id(provisioning_id)

    def observe(self) -> ProductionChatResourceObservation:
        prefix = f"local-model/resource-provisioning/{self._provisioning_id}/"

        def read(name: str, *, bound: int = 256 * 1024) -> bytes:
            try:
                value = self._handle.read_optional_regular_bounded(
                    prefix + _NAMES[name], max_bytes=bound)
            except InstallationStateError as exc:
                if exc.code == "state_parent_missing":
                    raise ProductionChatResourceObservationError("resource_bundle_missing", status="missing") from exc
                raise ProductionChatResourceObservationError(exc.code) from exc
            if value is None:
                raise ProductionChatResourceObservationError("resource_bundle_missing", status="missing")
            return value

        manifest = _manifest(read("manifest"), provisioning_id=self._provisioning_id,
                             installation_identity=self._handle.identity.value)
        principal = CausalResourcePrincipal.from_mapping(_mapping(read("principal"), "principal_json_invalid"))
        if (principal.principal_id != manifest["principal_id"]
                or principal.binding_digest != manifest["principal_binding_digest"]):
            raise ProductionChatResourceObservationError("manifest_principal_mismatch")
        provenance = RootPrincipalIssuerProvenance.from_mapping(
            _mapping(read("provenance"), "provenance_json_invalid"))
        if provenance.provenance_digest != manifest["provenance_digest"]:
            raise ProductionChatResourceObservationError("manifest_provenance_mismatch")
        catalog = ReadOnlyTrustedIssuerCatalog.from_bytes(
            read("catalog"), expected_catalog_version=int(manifest["trusted_issuer_catalog_version"]),
            expected_catalog_digest=str(manifest["trusted_issuer_catalog_digest"]))
        registry = ReadOnlyPrincipalRevocationRegistry.from_bytes(
            read("registry"), expected_registry_version=int(manifest["revocation_registry_version"]),
            expected_registry_digest=str(manifest["revocation_registry_digest"]))
        del catalog, registry  # Validation only; this observer has no currentness or allocation authority.
        policy = GovernedLocalModelResourcePolicy.from_mapping(_mapping(read("policy"), "policy_json_invalid"))
        if policy.policy_digest != manifest["resource_policy_digest"]:
            raise ProductionChatResourceObservationError("manifest_policy_mismatch")
        try:
            ledger_bytes = self._handle.read_optional_regular_bounded(
                prefix + _NAMES["ledger"], max_bytes=MAX_LEDGER_BYTES)
        except InstallationStateError as exc:
            raise ProductionChatResourceObservationError(exc.code) from exc
        if ledger_bytes is None:
            raise ProductionChatResourceObservationError("resource_ledger_missing", status="missing")
        try:
            ledger = GovernedLocalModelResourceLedger.read_only_snapshot(ledger_bytes, max_bytes=MAX_LEDGER_BYTES)
        except ValueError as exc:
            raise ProductionChatResourceObservationError("resource_ledger_invalid") from exc
        snapshot = ledger.observation_snapshot()
        if len(snapshot["allocations"]) != 1:
            raise ProductionChatResourceObservationError("resource_bundle_allocation_count_mismatch")
        allocation = next((GovernedLocalModelResourceAllocation.from_mapping(item)
                          for item in snapshot["allocations"]
                          if isinstance(item, Mapping) and item.get("allocation_id") == manifest["allocation_id"]), None)
        if allocation is None:
            raise ProductionChatResourceObservationError("manifest_allocation_missing")
        bindings = (
            (allocation.allocation_digest, manifest["allocation_digest"]),
            (allocation.resource_kind, manifest["resource_kind"]),
            (allocation.allocator_id, manifest["allocator_id"]),
            (allocation.principal_id, manifest["principal_id"]),
            (allocation.principal_binding_digest, manifest["principal_binding_digest"]),
            (allocation.policy_digest, manifest["resource_policy_digest"]),
        )
        if any(actual != expected for actual, expected in bindings):
            raise ProductionChatResourceObservationError("manifest_allocation_mismatch")
        try:
            authenticated = RootIssuerProvenanceVerifier(
                trust_store=catalog,
                signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier(),
            ).verify(principal, provenance,
                     current_time=allocation.validity.principal_currentness_checked_at)
            PrincipalCurrentnessVerifier().verify(
                principal, authenticated, registry,
                current_time=allocation.validity.principal_currentness_checked_at)
        except (TypeError, ValueError) as exc:
            raise ProductionChatResourceObservationError("historical_principal_binding_invalid") from exc
        invocation_receipts, receipt_posture, generation_attributions = self._invocation_receipts(
            allocation.allocation_digest)
        completed_invocations = tuple(item for item in invocation_receipts
            if item.get("status") == "admitted_completed"
            and isinstance(item.get("effects"), Mapping)
            and item["effects"].get("local_model_inference") is True)
        if not completed_invocations:
            generation_posture = "unknown_no_completed_invocations"
        elif len(generation_attributions) == len(completed_invocations):
            generation_posture = "verified"
        elif generation_attributions:
            generation_posture = "partial_legacy_or_unavailable"
        else:
            generation_posture = "unknown_legacy_or_unavailable"
        try:
            recovery_transitions = inspect_chat_recovery_phase_custody(self._handle, max_records=256)
            recovery_posture = ("verified_phase_custody" if recovery_transitions
                else "unknown_no_phase_custody")
        except LocalModelChatRecoveryError as exc:
            # The Windows view intentionally exposes only held-handle reads;
            # its directory API cannot distinguish an absent optional phase
            # directory from an unreadable one. Do not turn that ambiguity into
            # a claim that there were no recovery transitions.
            if os.name == "nt" and "directory" in exc.code:
                recovery_transitions = ()
                recovery_posture = "unknown_windows_read_only_phase_enumeration_unavailable"
            else:
                raise ProductionChatResourceObservationError(
                    "chat_process_recovery_custody_invalid:" + exc.code) from exc
        try:
            runtime_observation = read_stored_chat_process_runtime_observation(self._handle)
        except ChatProcessGenerationError as exc:
            raise ProductionChatResourceObservationError(
                "chat_process_runtime_observation_invalid:" + str(exc)) from exc
        if runtime_observation is None:
            runtime_observation_posture = "unknown_missing"
        elif runtime_observation.get("runtime_status") == "running_observed":
            runtime_observation_posture = "historically_observed_running"
        else:
            runtime_observation_posture = "historically_not_verified"
        try:
            serving_attempts = read_serving_operation_attempts(self._handle, maximum=256)
        except ProductionServingError as exc:
            raise ProductionChatResourceObservationError(
                "serving_operation_attempt_custody_invalid:" + str(exc)) from exc
        serving_attempt_posture = (
            "verified_attempts_present" if serving_attempts else "verified_no_attempts")
        try:
            serving_operation_history = read_serving_operation_history(self._handle, maximum=256)
        except ProductionServingError as exc:
            raise ProductionChatResourceObservationError(
                "serving_operation_history_invalid:" + str(exc)) from exc
        return ProductionChatResourceObservation(
            self._handle.identity.value, self._provisioning_id,
            str(manifest["manifest_digest"]), ledger, invocation_receipts, receipt_posture,
            generation_attributions, generation_posture, recovery_transitions, recovery_posture,
            runtime_observation, runtime_observation_posture,
            serving_attempts, serving_attempt_posture, serving_operation_history)

    def _invocation_receipts(self, allocation_digest: str
            ) -> tuple[tuple[Mapping[str, Any], ...], str, tuple[Mapping[str, Any], ...]]:
        try:
            names = self._handle.list_regular_names(
                "local-model/inference/receipts", max_entries=MAX_INVOCATION_RECEIPTS)
        except InstallationStateError as exc:
            if exc.code == "state_directory_missing":
                return (), "degraded_missing_receipt_directory", ()
            raise ProductionChatResourceObservationError("invocation_receipt_directory_invalid") from exc
        receipts: list[Mapping[str, Any]] = []
        generation_attributions: list[Mapping[str, Any]] = []
        for name in names:
            if _RECEIPT_TEMP_NAME.fullmatch(name) is not None:
                continue  # Incomplete atomic-write staging is never receipt evidence.
            if _RECEIPT_NAME.fullmatch(name) is None:
                raise ProductionChatResourceObservationError("invocation_receipt_name_invalid")
            try:
                raw = self._handle.read_regular_bounded(
                    f"local-model/inference/receipts/{name}", max_bytes=MAX_INVOCATION_RECEIPT_BYTES)
            except InstallationStateError as exc:
                raise ProductionChatResourceObservationError("invocation_receipt_read_invalid") from exc
            try:
                value = _mapping(raw, "invocation_receipt_json_invalid")
            except ValueError as exc:
                raise ProductionChatResourceObservationError("invocation_receipt_json_invalid") from exc
            if value.get("receipt_id") != name[:-5]:
                raise ProductionChatResourceObservationError("invocation_receipt_filename_mismatch")
            valid, findings = validate_receipt(value)
            if not valid:
                raise ProductionChatResourceObservationError("invocation_receipt_invalid:" + findings[0])
            request = value.get("request")
            linkage = request.get("linkage") if isinstance(request, Mapping) else None
            software = linkage.get("software_generation_attribution") if isinstance(linkage, Mapping) else None
            verified_software = None
            if software is not None:
                legacy_unavailable = {
                    "status": "unavailable",
                    "reason_code": "authenticated_chat_process_generation_issuer_not_composed",
                    "generation_identity": None,
                    "process_instance_id": None,
                }
                if software == legacy_unavailable:
                    verified_software = None
                elif (not isinstance(software, Mapping)
                        or software.get("status") != "runtime_launcher_process_and_source_bound"
                        or not isinstance(software.get("handoff_id"), str)
                        or not isinstance(software.get("handoff_digest"), str)):
                    raise ProductionChatResourceObservationError(
                        "invocation_software_generation_attribution_invalid")
                else:
                    try:
                        historical = verify_stored_chat_process_handoff(
                            handle=self._handle,
                            handoff_id=str(software["handoff_id"]),
                            expected_digest=str(software["handoff_digest"]))
                    except ChatProcessGenerationError as exc:
                        raise ProductionChatResourceObservationError(
                            "invocation_software_generation_handoff_invalid") from exc
                    if dict(software) != dict(historical):
                        raise ProductionChatResourceObservationError(
                            "invocation_software_generation_handoff_mismatch")
                    verified_software = dict(historical)
            if value.get("resource_allocation_digest") == allocation_digest:
                receipts.append(dict(value))
                request = value.get("request")
                if (verified_software is not None
                        and isinstance(request, Mapping)
                        and value.get("status") == "admitted_completed"
                        and isinstance(value.get("effects"), Mapping)
                        and value["effects"].get("local_model_inference") is True
                        and isinstance(value.get("output_digest"), str)):
                    compact_handoff = compact_runtime_generation_attribution(verified_software)
                    generation_attributions.append({
                        "invocation_receipt_id": value["receipt_id"],
                        "invocation_receipt_digest": value["receipt_digest"],
                        "invocation_request_id": request.get("request_id"),
                        "invocation_request_digest": request.get("request_digest"),
                        "chat_process_handoff": compact_handoff,
                        "attribution_posture": "invocation_receipt_and_historical_chat_handoff_verified",
                        "currentness_posture": "historical_process_identity_not_reobserved_during_recovery",
                    })
        receipts.sort(key=lambda item: (str(item.get("observed_at", "")), str(item.get("receipt_id", ""))))
        generation_attributions.sort(key=lambda item: (
            str(item.get("invocation_receipt_id", "")), str(item.get("invocation_receipt_digest", ""))))
        return (tuple(receipts),
            "verified" if receipts else "degraded_no_resource_invocation_receipts",
            tuple(generation_attributions))


__all__ = [
    "ProductionChatResourceObservation", "ProductionChatResourceObservationError",
    "ProductionChatResourceObservationOwner",
]
