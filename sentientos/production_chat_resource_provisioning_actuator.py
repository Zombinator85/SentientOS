"""Explicit prepare/confirm/create actuator for production resource provisioning."""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Callable, Mapping, cast

from .causal_resource_principal import CausalResourcePrincipal
from .causal_resource_principal_authentication import RootPrincipalIssuerProvenance
from .causal_resource_principal_currentness import ReadOnlyPrincipalRevocationRegistry
from .causal_resource_principal_trust_catalog import ReadOnlyTrustedIssuerCatalog
from .governed_local_model_resource_allocation import (
    GovernedLocalModelResourceBounds, GovernedLocalModelResourcePolicy,
)
from .installation_state import InstallationIdentity, InstallationStateRegistry
from .production_chat_resource_provisioning import validate_resource_provisioning_id
from .production_chat_resource_provisioning_bundle_producer import (
    ProductionChatResourceProvisioningBundleResult,
    produce_production_chat_resource_provisioning_bundle,
)

REQUEST_SCHEMA = "sentientos.production_chat_resource_provisioning_request:v1"
INTENT_SCHEMA = "sentientos.production_chat_resource_provisioning_intent:v1"
_DIGEST = re.compile(r"[0-9a-f]{64}")
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
_ARTIFACT_FIELDS = frozenset({"encoding", "sha256", "data"})
_FIELDS = frozenset({
    "schema_version", "installation_identity", "resource_provisioning_id",
    "principal_artifact", "provenance_artifact", "trusted_issuer_catalog_artifact",
    "principal_revocation_registry_artifact", "resource_policy_artifact",
    "requested_bounds", "requested_not_before", "requested_not_after", "request_digest",
})


class ProductionChatResourceProvisioningActuatorError(ValueError):
    """A bounded request or exact-confirmation failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProductionChatResourceProvisioningRequest:
    schema_version: str
    installation_identity: str
    resource_provisioning_id: str
    principal_artifact: bytes
    provenance_artifact: bytes
    trusted_issuer_catalog_artifact: bytes
    principal_revocation_registry_artifact: bytes
    resource_policy_artifact: bytes
    requested_bounds: GovernedLocalModelResourceBounds
    requested_not_before: str
    requested_not_after: str
    request_digest: str
    _packet: bytes


@dataclass(frozen=True, slots=True)
class ProductionChatResourceProvisioningIntent:
    schema_version: str
    request_digest: str
    installation_identity: str
    resource_provisioning_id: str
    principal_artifact_sha256: str
    provenance_artifact_sha256: str
    trusted_issuer_catalog_artifact_sha256: str
    principal_revocation_registry_artifact_sha256: str
    resource_policy_artifact_sha256: str
    principal_id: str
    principal_binding_digest: str
    provenance_digest: str
    trusted_issuer_catalog_version: int
    trusted_issuer_catalog_digest: str
    revocation_registry_version: int
    revocation_registry_digest: str
    resource_policy_digest: str
    requested_bounds: Mapping[str, object]
    requested_not_before: str
    requested_not_after: str
    intent_digest: str

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ProductionChatResourceProvisioningActuatorError("duplicate_request_key")
        value[key] = item
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProductionChatResourceProvisioningActuatorError("invalid_request_json") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _mapping(raw: bytes, code: str = "invalid_artifact") -> Mapping[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_keys,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except ProductionChatResourceProvisioningActuatorError:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ProductionChatResourceProvisioningActuatorError(code) from exc
    if not isinstance(value, dict):
        raise ProductionChatResourceProvisioningActuatorError(code)
    return value


def _artifact(value: object) -> bytes:
    if not isinstance(value, dict) or set(value) != _ARTIFACT_FIELDS:
        raise ProductionChatResourceProvisioningActuatorError("invalid_embedded_artifact")
    encoding, digest, data = value.get("encoding"), value.get("sha256"), value.get("data")
    if encoding != "base64url" or not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
        raise ProductionChatResourceProvisioningActuatorError("invalid_embedded_artifact")
    if not isinstance(data, str) or _BASE64URL.fullmatch(data) is None or "=" in data:
        raise ProductionChatResourceProvisioningActuatorError("noncanonical_base64url")
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (ValueError, binascii.Error) as exc:
        raise ProductionChatResourceProvisioningActuatorError("invalid_embedded_artifact") from exc
    if not raw or base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != data:
        raise ProductionChatResourceProvisioningActuatorError("noncanonical_base64url")
    if _sha(raw) != digest:
        raise ProductionChatResourceProvisioningActuatorError("artifact_digest_mismatch")
    return raw


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProductionChatResourceProvisioningActuatorError("invalid_requested_validity")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProductionChatResourceProvisioningActuatorError("invalid_requested_validity") from exc
    if (parsed.utcoffset() != timezone.utc.utcoffset(parsed)
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise ProductionChatResourceProvisioningActuatorError("invalid_requested_validity")
    return parsed


def load_provisioning_request(source: bytes | str | Path) -> ProductionChatResourceProvisioningRequest:
    """Load and fully validate one closed request packet without opening state."""
    try:
        raw = source if isinstance(source, bytes) else Path(source).read_bytes()
    except OSError as exc:
        raise ProductionChatResourceProvisioningActuatorError("request_read_failed") from exc
    value = _mapping(raw, "invalid_request_json")
    if set(value) != _FIELDS:
        raise ProductionChatResourceProvisioningActuatorError("request_fields_not_exact")
    if value.get("schema_version") != REQUEST_SCHEMA:
        raise ProductionChatResourceProvisioningActuatorError("unsupported_request_schema")
    claimed = value.get("request_digest")
    if not isinstance(claimed, str) or _DIGEST.fullmatch(claimed) is None:
        raise ProductionChatResourceProvisioningActuatorError("invalid_request_digest")
    body = dict(value)
    body.pop("request_digest")
    if _sha(_canonical(body)) != claimed:
        raise ProductionChatResourceProvisioningActuatorError("request_digest_mismatch")
    try:
        identity = InstallationIdentity.parse(cast(str, value.get("installation_identity")))
        provisioning_id = validate_resource_provisioning_id(cast(str, value.get("resource_provisioning_id")))
        bounds_value = value.get("requested_bounds")
        if not isinstance(bounds_value, Mapping):
            raise ValueError("invalid_bounds")
        bounds = GovernedLocalModelResourceBounds.from_mapping(bounds_value)
    except (TypeError, ValueError) as exc:
        raise ProductionChatResourceProvisioningActuatorError("invalid_request_identity_or_bounds") from exc
    before, after = value.get("requested_not_before"), value.get("requested_not_after")
    if _time(before) >= _time(after):
        raise ProductionChatResourceProvisioningActuatorError("invalid_requested_validity")
    return ProductionChatResourceProvisioningRequest(
        schema_version=REQUEST_SCHEMA, installation_identity=identity.value,
        resource_provisioning_id=provisioning_id,
        principal_artifact=_artifact(value.get("principal_artifact")),
        provenance_artifact=_artifact(value.get("provenance_artifact")),
        trusted_issuer_catalog_artifact=_artifact(value.get("trusted_issuer_catalog_artifact")),
        principal_revocation_registry_artifact=_artifact(value.get("principal_revocation_registry_artifact")),
        resource_policy_artifact=_artifact(value.get("resource_policy_artifact")),
        requested_bounds=bounds, requested_not_before=cast(str, before),
        requested_not_after=cast(str, after), request_digest=claimed, _packet=raw,
    )


def _validated(request: ProductionChatResourceProvisioningRequest | bytes | str | Path) -> ProductionChatResourceProvisioningRequest:
    if isinstance(request, ProductionChatResourceProvisioningRequest):
        return load_provisioning_request(request._packet)
    return load_provisioning_request(request)


def prepare_provisioning_intent(
    request: ProductionChatResourceProvisioningRequest | bytes | str | Path,
) -> ProductionChatResourceProvisioningIntent:
    """Inspect exact bytes and return a deterministic intent; never open or mutate state."""
    item = _validated(request)
    try:
        principal = CausalResourcePrincipal.from_mapping(_mapping(item.principal_artifact))
        provenance = RootPrincipalIssuerProvenance.from_mapping(_mapping(item.provenance_artifact))
        catalog_claim = _mapping(item.trusted_issuer_catalog_artifact)
        catalog = ReadOnlyTrustedIssuerCatalog.from_bytes(
            item.trusted_issuer_catalog_artifact,
            expected_catalog_version=cast(int, catalog_claim.get("catalog_version")),
            expected_catalog_digest=cast(str, catalog_claim.get("catalog_digest")),
        )
        registry_claim = _mapping(item.principal_revocation_registry_artifact)
        registry = ReadOnlyPrincipalRevocationRegistry.from_bytes(
            item.principal_revocation_registry_artifact,
            expected_registry_version=cast(int, registry_claim.get("registry_version")),
            expected_registry_digest=cast(str, registry_claim.get("registry_digest")),
        )
        policy = GovernedLocalModelResourcePolicy.from_mapping(_mapping(item.resource_policy_artifact))
    except ProductionChatResourceProvisioningActuatorError:
        raise
    except (TypeError, ValueError) as exc:
        raise ProductionChatResourceProvisioningActuatorError("artifact_semantic_validation_failed") from exc
    body: dict[str, object] = {
        "schema_version": INTENT_SCHEMA, "request_digest": item.request_digest,
        "installation_identity": item.installation_identity,
        "resource_provisioning_id": item.resource_provisioning_id,
        "principal_artifact_sha256": _sha(item.principal_artifact),
        "provenance_artifact_sha256": _sha(item.provenance_artifact),
        "trusted_issuer_catalog_artifact_sha256": _sha(item.trusted_issuer_catalog_artifact),
        "principal_revocation_registry_artifact_sha256": _sha(item.principal_revocation_registry_artifact),
        "resource_policy_artifact_sha256": _sha(item.resource_policy_artifact),
        "principal_id": principal.principal_id, "principal_binding_digest": principal.binding_digest,
        "provenance_digest": provenance.provenance_digest,
        "trusted_issuer_catalog_version": catalog.catalog_version,
        "trusted_issuer_catalog_digest": catalog.catalog_digest,
        "revocation_registry_version": registry.registry_version,
        "revocation_registry_digest": registry.registry_digest,
        "resource_policy_digest": policy.policy_digest,
        "requested_bounds": item.requested_bounds.to_dict(),
        "requested_not_before": item.requested_not_before,
        "requested_not_after": item.requested_not_after,
    }
    return ProductionChatResourceProvisioningIntent(**body, intent_digest=_sha(_canonical(body)))  # type: ignore[arg-type]


def execute_provisioning_intent(
    request: ProductionChatResourceProvisioningRequest | bytes | str | Path,
    *, confirmed_intent_digest: str,
    registry: InstallationStateRegistry | None = None,
    clock: Callable[[], str] | None = None,
) -> ProductionChatResourceProvisioningBundleResult:
    """Rebuild and confirm an intent, then invoke the create-only producer once."""
    if not isinstance(confirmed_intent_digest, str) or _DIGEST.fullmatch(confirmed_intent_digest) is None:
        raise ProductionChatResourceProvisioningActuatorError("invalid_confirmation_digest")
    item = _validated(request)
    intent = prepare_provisioning_intent(item)
    if confirmed_intent_digest != intent.intent_digest:
        raise ProductionChatResourceProvisioningActuatorError("intent_confirmation_mismatch")
    selected_registry = InstallationStateRegistry.system() if registry is None else registry
    handle = selected_registry.open(InstallationIdentity.parse(item.installation_identity))
    if clock is None:
        return produce_production_chat_resource_provisioning_bundle(
            handle, item.resource_provisioning_id,
            principal_artifact=item.principal_artifact,
            provenance_artifact=item.provenance_artifact,
            trusted_issuer_catalog_artifact=item.trusted_issuer_catalog_artifact,
            principal_revocation_registry_artifact=item.principal_revocation_registry_artifact,
            resource_policy_artifact=item.resource_policy_artifact,
            requested_bounds=item.requested_bounds,
            requested_not_before=item.requested_not_before,
            requested_not_after=item.requested_not_after)
    return produce_production_chat_resource_provisioning_bundle(
        handle, item.resource_provisioning_id,
        principal_artifact=item.principal_artifact,
        provenance_artifact=item.provenance_artifact,
        trusted_issuer_catalog_artifact=item.trusted_issuer_catalog_artifact,
        principal_revocation_registry_artifact=item.principal_revocation_registry_artifact,
        resource_policy_artifact=item.resource_policy_artifact,
        requested_bounds=item.requested_bounds,
        requested_not_before=item.requested_not_before,
        requested_not_after=item.requested_not_after,
        clock=clock)


__all__ = [
    "INTENT_SCHEMA", "REQUEST_SCHEMA", "ProductionChatResourceProvisioningActuatorError",
    "ProductionChatResourceProvisioningIntent", "ProductionChatResourceProvisioningRequest",
    "execute_provisioning_intent", "load_provisioning_request", "prepare_provisioning_intent",
]
