"""Read-only resident observation of installation-scoped production-chat custody.

The chat process remains the sole mutable ledger owner. This observer opens only
fixed authenticated installation objects and validates one atomically replaced
ledger image; it never constructs an allocator or ledger writer.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
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
from .governed_local_model_resource_allocation import (
    GovernedLocalModelResourceAllocation,
    GovernedLocalModelResourceLedger,
    GovernedLocalModelResourceLedgerObservation,
    GovernedLocalModelResourcePolicy,
)
from .installation_state import InstallationStateError, InstallationStateHandle
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


class ProductionChatResourceObservationOwner:
    """Explicit read-only selector for one preconfigured installation bundle."""

    __slots__ = ("_handle", "_provisioning_id")

    def __init__(self, handle: InstallationStateHandle, provisioning_id: str) -> None:
        if type(handle) is not InstallationStateHandle:
            raise TypeError("authenticated_installation_state_handle_required")
        self._handle = handle
        self._provisioning_id = validate_resource_provisioning_id(provisioning_id)

    def observe(self) -> ProductionChatResourceObservation:
        prefix = f"local-model/resource-provisioning/{self._provisioning_id}/"

        def read(name: str, *, bound: int = 256 * 1024) -> bytes:
            try:
                value = self._handle.read_optional_regular_bounded(
                    self._handle.fixed_object(prefix + _NAMES[name]), max_bytes=bound)
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
                self._handle.fixed_object(prefix + _NAMES["ledger"]), max_bytes=MAX_LEDGER_BYTES)
        except InstallationStateError as exc:
            raise ProductionChatResourceObservationError(exc.code) from exc
        if ledger_bytes is None:
            raise ProductionChatResourceObservationError("resource_ledger_missing", status="missing")
        try:
            ledger = GovernedLocalModelResourceLedger.read_only_snapshot(ledger_bytes, max_bytes=MAX_LEDGER_BYTES)
        except ValueError as exc:
            raise ProductionChatResourceObservationError("resource_ledger_invalid") from exc
        snapshot = ledger.observation_snapshot()
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
        invocation_receipts, receipt_posture = self._invocation_receipts(allocation.allocation_digest)
        return ProductionChatResourceObservation(
            self._handle.identity.value, self._provisioning_id,
            str(manifest["manifest_digest"]), ledger, invocation_receipts, receipt_posture)

    def _invocation_receipts(self, allocation_digest: str) -> tuple[tuple[Mapping[str, Any], ...], str]:
        directory = self._handle.fixed_object("local-model/inference/receipts")
        try:
            names = self._handle.list_regular_names(directory, max_entries=MAX_INVOCATION_RECEIPTS)
        except InstallationStateError as exc:
            if exc.code == "state_directory_missing":
                return (), "degraded_missing_receipt_directory"
            raise ProductionChatResourceObservationError("invocation_receipt_directory_invalid") from exc
        receipts: list[Mapping[str, Any]] = []
        for name in names:
            if _RECEIPT_TEMP_NAME.fullmatch(name) is not None:
                continue  # Incomplete atomic-write staging is never receipt evidence.
            if _RECEIPT_NAME.fullmatch(name) is None:
                raise ProductionChatResourceObservationError("invocation_receipt_name_invalid")
            try:
                raw = self._handle.read_regular_bounded(
                    directory.child(name), max_bytes=MAX_INVOCATION_RECEIPT_BYTES)
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
            if value.get("resource_allocation_digest") == allocation_digest:
                receipts.append(dict(value))
        receipts.sort(key=lambda item: (str(item.get("observed_at", "")), str(item.get("receipt_id", ""))))
        return tuple(receipts), "verified" if receipts else "degraded_no_resource_invocation_receipts"


__all__ = [
    "ProductionChatResourceObservation", "ProductionChatResourceObservationError",
    "ProductionChatResourceObservationOwner",
]
