"""Verifier-side composition of an existing production chat resource bundle."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
from typing import Callable, Mapping, cast

from .causal_resource_principal import CausalResourcePrincipal
from .causal_resource_principal_authentication import RootIssuerProvenanceVerifier, RootPrincipalIssuerProvenance
from .causal_resource_principal_currentness import PrincipalCurrentnessVerifier, ReadOnlyPrincipalRevocationRegistry
from .causal_resource_principal_ed25519 import CryptographyEd25519RootIssuerSignatureVerifier
from .causal_resource_principal_trust_catalog import ReadOnlyTrustedIssuerCatalog
from .governed_local_model_resource_allocation import (ALLOCATOR_ID, RESOURCE_KIND,
    GovernedLocalModelResourceAllocator, GovernedLocalModelResourceLedger,
    GovernedLocalModelResourcePolicy)
from .installation_state import InstallationStateHandle
from .production_chat_resource_context import ProductionChatResourceContextOwner

MANIFEST_SCHEMA = "sentientos.production_chat_resource_provisioning:v1"
_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FIELDS = frozenset({"schema_version", "provisioning_id", "installation_identity", "resource_kind",
    "allocator_id", "principal_id", "principal_binding_digest", "provenance_digest",
    "trusted_issuer_catalog_version", "trusted_issuer_catalog_digest", "revocation_registry_version",
    "revocation_registry_digest", "resource_policy_digest", "allocation_id", "allocation_digest",
    "manifest_digest"})
_NAMES = {"manifest": "manifest.json", "principal": "root-principal.json",
    "provenance": "root-principal-provenance.json", "catalog": "trusted-issuer-catalog.json",
    "registry": "principal-revocation-registry.json", "policy": "resource-policy.json",
    "ledger": "resource-ledger.json"}


class ProductionChatResourceProvisioningError(ValueError):
    """A bounded fail-closed production provisioning failure."""


def trusted_utc_clock() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def trusted_nonce_source() -> str:
    return secrets.token_hex(32)


def validate_resource_provisioning_id(value: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None or ".." in value or value in {"all", "any"}:
        raise ProductionChatResourceProvisioningError("invalid_resource_provisioning_id")
    return value


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def manifest_digest_for(value: Mapping[str, object]) -> str:
    body = dict(value); body.pop("manifest_digest", None)
    return "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()


def _duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result: raise ProductionChatResourceProvisioningError("manifest_json_invalid")
        result[key] = value
    return result


def _mapping(raw: bytes, code: str) -> Mapping[str, object]:
    try: value = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicates)
    except ProductionChatResourceProvisioningError: raise
    except (UnicodeError, ValueError, TypeError) as exc: raise ProductionChatResourceProvisioningError(code) from exc
    if not isinstance(value, dict): raise ProductionChatResourceProvisioningError(code)
    return value


def _manifest(raw: bytes, *, provisioning_id: str, installation_identity: str) -> Mapping[str, object]:
    value = _mapping(raw, "manifest_json_invalid")
    if set(value) != _FIELDS: raise ProductionChatResourceProvisioningError("manifest_fields_not_exact")
    if value["schema_version"] != MANIFEST_SCHEMA: raise ProductionChatResourceProvisioningError("unsupported_manifest_schema")
    if value["provisioning_id"] != provisioning_id: raise ProductionChatResourceProvisioningError("provisioning_id_mismatch")
    if value["installation_identity"] != installation_identity: raise ProductionChatResourceProvisioningError("installation_identity_mismatch")
    if value["resource_kind"] != RESOURCE_KIND or value["allocator_id"] != ALLOCATOR_ID:
        raise ProductionChatResourceProvisioningError("resource_identity_mismatch")
    for field in ("principal_binding_digest", "provenance_digest", "trusted_issuer_catalog_digest",
                  "revocation_registry_digest", "resource_policy_digest", "allocation_digest", "manifest_digest"):
        candidate = value[field]
        if not isinstance(candidate, str) or _DIGEST.fullmatch(candidate) is None:
            raise ProductionChatResourceProvisioningError("invalid_manifest_digest")
    if value["manifest_digest"] != manifest_digest_for(value):
        raise ProductionChatResourceProvisioningError("manifest_digest_mismatch")
    for field in ("trusted_issuer_catalog_version", "revocation_registry_version"):
        candidate = value[field]
        if type(candidate) is not int or candidate < 1: raise ProductionChatResourceProvisioningError("invalid_manifest_version")
    return value


def load_production_chat_resource_context_owner(
    installation_handle: InstallationStateHandle, provisioning_id: str, *,
    clock: Callable[[], str] = trusted_utc_clock,
    nonce_source: Callable[[], str] = trusted_nonce_source,
) -> ProductionChatResourceContextOwner:
    """Authenticate and compose one exact pre-issued allocation; never issue one."""
    if type(installation_handle) is not InstallationStateHandle:
        raise TypeError("authenticated_installation_state_handle_required")
    selected = validate_resource_provisioning_id(provisioning_id)
    prefix = f"local-model/resource-provisioning/{selected}/"
    def read(name: str) -> bytes:
        return cast(bytes, installation_handle.read_regular(
            installation_handle.fixed_object(prefix + _NAMES[name])))
    manifest = _manifest(read("manifest"), provisioning_id=selected,
                         installation_identity=installation_handle.identity.value)
    now = clock()
    principal = CausalResourcePrincipal.from_mapping(_mapping(read("principal"), "principal_json_invalid"))
    if principal.principal_id != manifest["principal_id"] or principal.binding_digest != manifest["principal_binding_digest"]:
        raise ProductionChatResourceProvisioningError("manifest_principal_mismatch")
    provenance = RootPrincipalIssuerProvenance.from_mapping(_mapping(read("provenance"), "provenance_json_invalid"))
    if provenance.provenance_digest != manifest["provenance_digest"]:
        raise ProductionChatResourceProvisioningError("manifest_provenance_mismatch")
    catalog = ReadOnlyTrustedIssuerCatalog.from_bytes(read("catalog"),
        expected_catalog_version=cast(int, manifest["trusted_issuer_catalog_version"]),
        expected_catalog_digest=cast(str, manifest["trusted_issuer_catalog_digest"]))
    authenticated = RootIssuerProvenanceVerifier(trust_store=catalog,
        signature_verifier=CryptographyEd25519RootIssuerSignatureVerifier()).verify(
            principal, provenance, current_time=now)
    registry = ReadOnlyPrincipalRevocationRegistry.from_bytes(read("registry"),
        expected_registry_version=cast(int, manifest["revocation_registry_version"]),
        expected_registry_digest=cast(str, manifest["revocation_registry_digest"]))
    current = PrincipalCurrentnessVerifier().verify(principal, authenticated, registry, current_time=now)
    policy = GovernedLocalModelResourcePolicy.from_mapping(_mapping(read("policy"), "policy_json_invalid"))
    if policy.policy_digest != manifest["resource_policy_digest"]:
        raise ProductionChatResourceProvisioningError("manifest_policy_mismatch")
    ledger_object = installation_handle.fixed_object(prefix + _NAMES["ledger"])
    installation_handle.read_regular(ledger_object)  # existence/type custody before constructor
    ledger = GovernedLocalModelResourceLedger(ledger_object.path)
    allocation = ledger.allocation(cast(str, manifest["allocation_id"]))
    bindings = ((allocation.allocation_digest, manifest["allocation_digest"]),
        (allocation.resource_kind, manifest["resource_kind"]), (allocation.allocator_id, manifest["allocator_id"]),
        (allocation.principal_id, manifest["principal_id"]),
        (allocation.principal_binding_digest, manifest["principal_binding_digest"]),
        (allocation.policy_digest, manifest["resource_policy_digest"]))
    if any(actual != expected for actual, expected in bindings):
        raise ProductionChatResourceProvisioningError("manifest_allocation_mismatch")
    allocator = GovernedLocalModelResourceAllocator(policy=policy, ledger=ledger)
    return ProductionChatResourceContextOwner(allocator=allocator, allocation=allocation, principal=principal,
        authenticated=authenticated, current=current, policy=policy, nonce_source=nonce_source, clock=clock)


__all__ = ["MANIFEST_SCHEMA", "ProductionChatResourceProvisioningError",
    "load_production_chat_resource_context_owner", "manifest_digest_for", "trusted_nonce_source",
    "trusted_utc_clock", "validate_resource_provisioning_id"]
