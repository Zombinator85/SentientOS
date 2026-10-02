"""Create exactly one production-chat provisioning bundle, manifest last."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Callable, Mapping, cast

from .causal_resource_principal import CausalResourcePrincipal, CausalResourcePrincipalVerifier
from .causal_resource_principal_authentication import RootIssuerProvenanceVerifier, RootPrincipalIssuerProvenance
from .causal_resource_principal_currentness import PrincipalCurrentnessVerifier, ReadOnlyPrincipalRevocationRegistry
from .causal_resource_principal_ed25519 import CryptographyEd25519RootIssuerSignatureVerifier
from .causal_resource_principal_trust_catalog import ReadOnlyTrustedIssuerCatalog
from .governed_local_model_resource_allocation import (
    ALLOCATOR_ID, RESOURCE_KIND, GovernedLocalModelResourceAllocator,
    GovernedLocalModelResourceBounds, GovernedLocalModelResourceLedger,
    GovernedLocalModelResourcePolicy,
)
from .installation_state import InstallationStateError, InstallationStateHandle
from .production_chat_resource_provisioning import (
    MANIFEST_SCHEMA, manifest_digest_for, trusted_utc_clock,
    validate_resource_provisioning_id,
)

_NAMES = (
    ("principal", "root-principal.json"),
    ("provenance", "root-principal-provenance.json"),
    ("catalog", "trusted-issuer-catalog.json"),
    ("registry", "principal-revocation-registry.json"),
    ("policy", "resource-policy.json"),
)


class ProductionChatResourceProvisioningBundleProducerError(ValueError):
    """Bounded create-only producer failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProductionChatResourceProvisioningBundleResult:
    provisioning_id: str
    installation_identity: str
    manifest_digest: str
    allocation_id: str
    allocation_digest: str
    resource_policy_digest: str
    principal_id: str
    principal_binding_digest: str


def _duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input")
        result[key] = value
    return result


def _mapping(raw: bytes) -> Mapping[str, object]:
    if type(raw) is not bytes:
        raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_keys,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except ProductionChatResourceProvisioningBundleProducerError:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input") from exc
    if not isinstance(value, dict):
        raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input")
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input") from exc
    if (parsed.utcoffset() != timezone.utc.utcoffset(parsed)
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input")
    return parsed


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def produce_production_chat_resource_provisioning_bundle(
    installation_handle: InstallationStateHandle,
    resource_provisioning_id: str,
    *,
    principal_artifact: bytes,
    provenance_artifact: bytes,
    trusted_issuer_catalog_artifact: bytes,
    principal_revocation_registry_artifact: bytes,
    resource_policy_artifact: bytes,
    requested_bounds: GovernedLocalModelResourceBounds,
    requested_not_before: str,
    requested_not_after: str,
    clock: Callable[[], str] = trusted_utc_clock,
) -> ProductionChatResourceProvisioningBundleResult:
    """Validate explicit artifacts, issue once, and publish a new bundle."""
    if type(installation_handle) is not InstallationStateHandle:
        raise TypeError("authenticated_installation_state_handle_required")
    try:
        selected = validate_resource_provisioning_id(resource_provisioning_id)
        if type(requested_bounds) is not GovernedLocalModelResourceBounds or not callable(clock):
            raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input")
        principal = CausalResourcePrincipal.from_mapping(_mapping(principal_artifact))
        provenance = RootPrincipalIssuerProvenance.from_mapping(_mapping(provenance_artifact))
        catalog_claim = _mapping(trusted_issuer_catalog_artifact)
        catalog = ReadOnlyTrustedIssuerCatalog.from_bytes(
            trusted_issuer_catalog_artifact,
            expected_catalog_version=cast(int, catalog_claim.get("catalog_version")),
            expected_catalog_digest=cast(str, catalog_claim.get("catalog_digest")),
        )
        registry_claim = _mapping(principal_revocation_registry_artifact)
        registry = ReadOnlyPrincipalRevocationRegistry.from_bytes(
            principal_revocation_registry_artifact,
            expected_registry_version=cast(int, registry_claim.get("registry_version")),
            expected_registry_digest=cast(str, registry_claim.get("registry_digest")),
        )
        policy = GovernedLocalModelResourcePolicy.from_mapping(_mapping(resource_policy_artifact))
        provisioning_time = clock()
        now = _time(provisioning_time)
        CausalResourcePrincipalVerifier().verify(principal, current_time=provisioning_time)
        authenticated = RootIssuerProvenanceVerifier(
            trust_store=catalog,
            signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier(),
        ).verify(principal, provenance, current_time=provisioning_time)
        current = PrincipalCurrentnessVerifier().verify(
            principal, authenticated, registry, current_time=provisioning_time)
        if not _time(policy.not_before) <= now < _time(policy.valid_until):
            raise ProductionChatResourceProvisioningBundleProducerError("policy_not_current")
        before, after = _time(requested_not_before), _time(requested_not_after)
        if after <= before:
            raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input")
        if any(getattr(requested_bounds, field) > getattr(policy.max_resource_specific_bounds, field)
               for field in GovernedLocalModelResourceBounds.__dataclass_fields__):
            raise ProductionChatResourceProvisioningBundleProducerError("invalid_provisioning_input")
    except ProductionChatResourceProvisioningBundleProducerError:
        raise
    except (TypeError, ValueError) as exc:
        raise ProductionChatResourceProvisioningBundleProducerError("artifact_verification_failed") from exc

    prefix = f"local-model/resource-provisioning/{selected}"
    lock_directory = installation_handle.fixed_object("local-model/resource-provisioning-locks")
    lock_object = installation_handle.fixed_object(f"local-model/resource-provisioning-locks/{selected}.lock")
    destination = installation_handle.fixed_object(prefix)
    artifacts = {
        "principal": principal_artifact,
        "provenance": provenance_artifact,
        "catalog": trusted_issuer_catalog_artifact,
        "registry": principal_revocation_registry_artifact,
        "policy": resource_policy_artifact,
    }
    try:
        installation_handle.ensure_directory(lock_directory)
        with installation_handle.exclusive_lock(lock_object):
            installation_handle.ensure_directory(destination)
            if installation_handle.list_regular_names(destination):
                raise ProductionChatResourceProvisioningBundleProducerError(
                    "provisioning_destination_not_unused")
            ledger_object = installation_handle.fixed_object(prefix + "/resource-ledger.json")
            ledger = GovernedLocalModelResourceLedger(ledger_object.path)
            if ledger.snapshot_counts() != (0, 0, 0):
                raise ProductionChatResourceProvisioningBundleProducerError(
                    "provisioning_destination_not_unused")
            allocator = GovernedLocalModelResourceAllocator(policy=policy, ledger=ledger)
            try:
                allocation = allocator.issue(
                    principal=principal, authenticated=authenticated, current=current,
                    requested_bounds=requested_bounds,
                    requested_not_before=requested_not_before,
                    requested_not_after=requested_not_after,
                    current_time=provisioning_time,
                )
            except ValueError as exc:
                raise ProductionChatResourceProvisioningBundleProducerError(
                    "allocation_issuance_failed") from exc
            if (ledger.snapshot_counts() != (1, 0, 0)
                    or ledger.remaining_calls(allocation.allocation_id)
                    != allocation.resource_specific_bounds.max_calls_per_correlation):
                raise ProductionChatResourceProvisioningBundleProducerError(
                    "allocation_issuance_failed")
            for key, filename in _NAMES:
                installation_handle.durable_create(
                    installation_handle.fixed_object(prefix + "/" + filename), artifacts[key])
            manifest: dict[str, object] = {
                "schema_version": MANIFEST_SCHEMA,
                "provisioning_id": selected,
                "installation_identity": installation_handle.identity.value,
                "resource_kind": RESOURCE_KIND,
                "allocator_id": ALLOCATOR_ID,
                "principal_id": principal.principal_id,
                "principal_binding_digest": principal.binding_digest,
                "provenance_digest": provenance.provenance_digest,
                "trusted_issuer_catalog_version": catalog.catalog_version,
                "trusted_issuer_catalog_digest": catalog.catalog_digest,
                "revocation_registry_version": registry.registry_version,
                "revocation_registry_digest": registry.registry_digest,
                "resource_policy_digest": policy.policy_digest,
                "allocation_id": allocation.allocation_id,
                "allocation_digest": allocation.allocation_digest,
            }
            manifest["manifest_digest"] = manifest_digest_for(manifest)
            installation_handle.durable_create(
                installation_handle.fixed_object(prefix + "/manifest.json"), _canonical(manifest))
    except ProductionChatResourceProvisioningBundleProducerError:
        raise
    except InstallationStateError as exc:
        code = "provisioning_lock_failure" if "lock" in exc.code else "bundle_publication_failed"
        raise ProductionChatResourceProvisioningBundleProducerError(code) from exc
    except OSError as exc:
        raise ProductionChatResourceProvisioningBundleProducerError("bundle_publication_failed") from exc
    return ProductionChatResourceProvisioningBundleResult(
        provisioning_id=selected,
        installation_identity=installation_handle.identity.value,
        manifest_digest=cast(str, manifest["manifest_digest"]),
        allocation_id=allocation.allocation_id,
        allocation_digest=allocation.allocation_digest,
        resource_policy_digest=policy.policy_digest,
        principal_id=principal.principal_id,
        principal_binding_digest=principal.binding_digest,
    )


__all__ = [
    "ProductionChatResourceProvisioningBundleProducerError",
    "ProductionChatResourceProvisioningBundleResult",
    "produce_production_chat_resource_provisioning_bundle",
]
