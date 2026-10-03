"""Create-only publisher for verified production provisioning requests."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable, Mapping, cast

from .causal_resource_principal import CausalResourcePrincipal, CausalResourcePrincipalVerifier
from .causal_resource_principal_authentication import RootIssuerProvenanceVerifier, RootPrincipalIssuerProvenance
from .causal_resource_principal_currentness import PrincipalCurrentnessVerifier, ReadOnlyPrincipalRevocationRegistry
from .causal_resource_principal_ed25519 import CryptographyEd25519RootIssuerSignatureVerifier
from .causal_resource_principal_trust_catalog import ReadOnlyTrustedIssuerCatalog
from .governed_local_model_resource_allocation import GovernedLocalModelResourceBounds, GovernedLocalModelResourcePolicy
from .installation_state import InstallationStateError, InstallationStateHandle
from .production_chat_resource_provisioning import trusted_utc_clock, validate_resource_provisioning_id
from .production_chat_resource_provisioning_actuator import REQUEST_SCHEMA, load_provisioning_request, prepare_provisioning_intent

PUBLICATION_RECEIPT_SCHEMA = "sentientos.production_chat_resource_provisioning_request_publication_receipt:v1"
AUTHORITY_DEFINITION_DIGEST = "349058b7e6959c06bfae1a8acabd01c6c022245c6fd404e63535cac6ed608cf5"


class ProductionChatResourceProvisioningRequestPublisherError(ValueError):
    """A bounded verification or create-only publication failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProductionChatResourceProvisioningRequestPublicationResult:
    installation_identity: str
    resource_provisioning_id: str
    request_digest: str
    intent_digest: str
    receipt_digest: str
    authority_definition_digest: str


def _duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProductionChatResourceProvisioningRequestPublisherError("invalid_publication_input")
        result[key] = value
    return result


def _mapping(raw: bytes) -> Mapping[str, object]:
    if type(raw) is not bytes or not raw:
        raise ProductionChatResourceProvisioningRequestPublisherError("invalid_publication_input")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except ProductionChatResourceProvisioningRequestPublisherError:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ProductionChatResourceProvisioningRequestPublisherError("invalid_publication_input") from exc
    if not isinstance(value, dict):
        raise ProductionChatResourceProvisioningRequestPublisherError("invalid_publication_input")
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProductionChatResourceProvisioningRequestPublisherError("invalid_publication_input") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProductionChatResourceProvisioningRequestPublisherError("invalid_publication_time")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProductionChatResourceProvisioningRequestPublisherError("invalid_publication_time") from exc
    if (parsed.utcoffset() != timezone.utc.utcoffset(parsed)
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise ProductionChatResourceProvisioningRequestPublisherError("invalid_publication_time")
    return parsed


def _embedded(raw: bytes) -> dict[str, str]:
    return {"encoding": "base64url", "sha256": _sha(raw),
            "data": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")}


def _verify_request(raw: bytes) -> None:
    load_provisioning_request(raw)


def publish_production_chat_resource_provisioning_request(
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
    publication_clock: Callable[[], str] = trusted_utc_clock,
) -> ProductionChatResourceProvisioningRequestPublicationResult:
    """Verify exact artifacts and publish one request plus its receipt, receipt last."""
    if type(installation_handle) is not InstallationStateHandle:
        raise TypeError("authenticated_installation_state_handle_required")
    try:
        selected = validate_resource_provisioning_id(resource_provisioning_id)
        if type(requested_bounds) is not GovernedLocalModelResourceBounds or not callable(publication_clock):
            raise ProductionChatResourceProvisioningRequestPublisherError("invalid_publication_input")
        principal = CausalResourcePrincipal.from_mapping(_mapping(principal_artifact))
        provenance = RootPrincipalIssuerProvenance.from_mapping(_mapping(provenance_artifact))
        catalog_claim = _mapping(trusted_issuer_catalog_artifact)
        catalog = ReadOnlyTrustedIssuerCatalog.from_bytes(
            trusted_issuer_catalog_artifact,
            expected_catalog_version=cast(int, catalog_claim.get("catalog_version")),
            expected_catalog_digest=cast(str, catalog_claim.get("catalog_digest")))
        registry_claim = _mapping(principal_revocation_registry_artifact)
        registry = ReadOnlyPrincipalRevocationRegistry.from_bytes(
            principal_revocation_registry_artifact,
            expected_registry_version=cast(int, registry_claim.get("registry_version")),
            expected_registry_digest=cast(str, registry_claim.get("registry_digest")))
        policy = GovernedLocalModelResourcePolicy.from_mapping(_mapping(resource_policy_artifact))
        publication_time = publication_clock()
        now = _time(publication_time)
        CausalResourcePrincipalVerifier().verify(principal, current_time=publication_time)
        authenticated = RootIssuerProvenanceVerifier(
            trust_store=catalog,
            signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier(),
        ).verify(principal, provenance, current_time=publication_time)
        PrincipalCurrentnessVerifier().verify(
            principal, authenticated, registry, current_time=publication_time)
        if not _time(policy.not_before) <= now < _time(policy.valid_until):
            raise ProductionChatResourceProvisioningRequestPublisherError("resource_policy_not_current")
        before, after = _time(requested_not_before), _time(requested_not_after)
        if before >= after:
            raise ProductionChatResourceProvisioningRequestPublisherError("invalid_requested_validity")
        if any(getattr(requested_bounds, field) > getattr(policy.max_resource_specific_bounds, field)
               for field in GovernedLocalModelResourceBounds.__dataclass_fields__):
            raise ProductionChatResourceProvisioningRequestPublisherError("requested_bounds_exceed_policy")
    except ProductionChatResourceProvisioningRequestPublisherError:
        raise
    except (TypeError, ValueError) as exc:
        raise ProductionChatResourceProvisioningRequestPublisherError("artifact_verification_failed") from exc

    prefix = f"local-model/resource-provisioning-requests/{selected}"
    lock_directory = installation_handle.fixed_object("local-model/resource-provisioning-request-locks")
    lock_object = installation_handle.fixed_object(f"local-model/resource-provisioning-request-locks/{selected}.lock")
    destination = installation_handle.fixed_object(prefix)
    try:
        installation_handle.ensure_directory(lock_directory)
        with installation_handle.exclusive_lock(lock_object):
            installation_handle.ensure_directory(destination)
            if installation_handle.list_regular_names(destination):
                raise ProductionChatResourceProvisioningRequestPublisherError("request_destination_not_unused")
            body: dict[str, object] = {
                "schema_version": REQUEST_SCHEMA,
                "installation_identity": installation_handle.identity.value,
                "resource_provisioning_id": selected,
                "principal_artifact": _embedded(principal_artifact),
                "provenance_artifact": _embedded(provenance_artifact),
                "trusted_issuer_catalog_artifact": _embedded(trusted_issuer_catalog_artifact),
                "principal_revocation_registry_artifact": _embedded(principal_revocation_registry_artifact),
                "resource_policy_artifact": _embedded(resource_policy_artifact),
                "requested_bounds": requested_bounds.to_dict(),
                "requested_not_before": requested_not_before,
                "requested_not_after": requested_not_after,
            }
            request_digest = _sha(_canonical(body))
            request_bytes = _canonical({**body, "request_digest": request_digest})
            loaded = load_provisioning_request(request_bytes)
            if loaded._packet != request_bytes:
                raise ProductionChatResourceProvisioningRequestPublisherError("request_round_trip_failed")
            intent = prepare_provisioning_intent(request_bytes)
            installation_handle.durable_create(
                installation_handle.fixed_object(prefix + "/request.json"), request_bytes,
                verify=_verify_request)
            receipt: dict[str, object] = {
                "schema_version": PUBLICATION_RECEIPT_SCHEMA,
                "installation_identity": installation_handle.identity.value,
                "resource_provisioning_id": selected,
                "request_digest": request_digest,
                "intent_digest": intent.intent_digest,
                "principal_artifact_sha256": _sha(principal_artifact),
                "provenance_artifact_sha256": _sha(provenance_artifact),
                "trusted_issuer_catalog_artifact_sha256": _sha(trusted_issuer_catalog_artifact),
                "principal_revocation_registry_artifact_sha256": _sha(principal_revocation_registry_artifact),
                "resource_policy_artifact_sha256": _sha(resource_policy_artifact),
                "principal_id": principal.principal_id,
                "principal_binding_digest": principal.binding_digest,
                "provenance_digest": provenance.provenance_digest,
                "trusted_issuer_catalog_version": catalog.catalog_version,
                "trusted_issuer_catalog_digest": catalog.catalog_digest,
                "revocation_registry_version": registry.registry_version,
                "revocation_registry_digest": registry.registry_digest,
                "resource_policy_digest": policy.policy_digest,
                "verified_at": publication_time,
                "authority_definition_digest": AUTHORITY_DEFINITION_DIGEST,
            }
            receipt_digest = _sha(_canonical(receipt))
            receipt_bytes = _canonical({**receipt, "receipt_digest": receipt_digest})
            installation_handle.durable_create(
                installation_handle.fixed_object(prefix + "/publication-receipt.json"), receipt_bytes)
    except ProductionChatResourceProvisioningRequestPublisherError:
        raise
    except InstallationStateError as exc:
        code = "request_lock_failure" if "lock" in exc.code else "request_publication_failed"
        raise ProductionChatResourceProvisioningRequestPublisherError(code) from exc
    except OSError as exc:
        raise ProductionChatResourceProvisioningRequestPublisherError("request_publication_failed") from exc
    return ProductionChatResourceProvisioningRequestPublicationResult(
        installation_identity=installation_handle.identity.value,
        resource_provisioning_id=selected,
        request_digest=request_digest,
        intent_digest=intent.intent_digest,
        receipt_digest=receipt_digest,
        authority_definition_digest=AUTHORITY_DEFINITION_DIGEST)


__all__ = [
    "AUTHORITY_DEFINITION_DIGEST", "PUBLICATION_RECEIPT_SCHEMA",
    "ProductionChatResourceProvisioningRequestPublicationResult",
    "ProductionChatResourceProvisioningRequestPublisherError",
    "publish_production_chat_resource_provisioning_request",
]
