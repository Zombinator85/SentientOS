"""Read-only verifier for published production provisioning-request custody.

Successful loading proves only immutable request/receipt custody and their frozen
bindings.  It does not prove operator confirmation, runtime admission, allocation,
bundle existence, current eligibility, startup authorization, or inference authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Mapping

from .codex_task_authority_admission import (
    PRODUCTION_CHAT_RESOURCE_PROVISIONING_REQUEST_PUBLISH_DEFINITION,
    authority_definition_digest,
)
from .installation_state import InstallationStateError, InstallationStateHandle
from .production_chat_resource_provisioning import validate_resource_provisioning_id
from .production_chat_resource_provisioning_actuator import (
    ProductionChatResourceProvisioningActuatorError,
    load_provisioning_request,
    prepare_provisioning_intent,
)
from .production_chat_resource_provisioning_request_publisher import (
    AUTHORITY_DEFINITION_DIGEST,
    PUBLICATION_RECEIPT_SCHEMA,
)

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_RECEIPT_FIELDS = frozenset({
    "schema_version", "installation_identity", "resource_provisioning_id",
    "request_digest", "intent_digest", "principal_artifact_sha256",
    "provenance_artifact_sha256", "trusted_issuer_catalog_artifact_sha256",
    "principal_revocation_registry_artifact_sha256", "resource_policy_artifact_sha256",
    "principal_id", "principal_binding_digest", "provenance_digest",
    "trusted_issuer_catalog_version", "trusted_issuer_catalog_digest",
    "revocation_registry_version", "revocation_registry_digest", "resource_policy_digest",
    "verified_at", "authority_definition_digest", "receipt_digest",
})


class ProductionChatResourceProvisioningRequestConsumerError(ValueError):
    """A bounded fixed-custody read or verification failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ProductionChatResourceProvisioningRequestConsumerError("duplicate_custody_key")
        value[key] = item
    return value


def _mapping(raw: bytes, code: str) -> Mapping[str, object]:
    if type(raw) is not bytes or not raw:
        raise ProductionChatResourceProvisioningRequestConsumerError(code)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except ProductionChatResourceProvisioningRequestConsumerError:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ProductionChatResourceProvisioningRequestConsumerError(code) from exc
    if not isinstance(value, dict):
        raise ProductionChatResourceProvisioningRequestConsumerError(code)
    return value


def _canonical(value: object, code: str) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProductionChatResourceProvisioningRequestConsumerError(code) from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_digest(value: object, code: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ProductionChatResourceProvisioningRequestConsumerError(code)
    return value


def _require_publication_time(value: object) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProductionChatResourceProvisioningRequestConsumerError("invalid_verified_at")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProductionChatResourceProvisioningRequestConsumerError("invalid_verified_at") from exc
    if (parsed.utcoffset() != timezone.utc.utcoffset(parsed)
            or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value):
        raise ProductionChatResourceProvisioningRequestConsumerError("invalid_verified_at")


def load_published_production_chat_resource_provisioning_request(
    installation_handle: InstallationStateHandle,
    resource_provisioning_id: str,
) -> bytes:
    """Return exact verified request bytes from fixed completed-publication custody."""
    if type(installation_handle) is not InstallationStateHandle:
        raise TypeError("authenticated_installation_state_handle_required")
    try:
        selected = validate_resource_provisioning_id(resource_provisioning_id)
    except (TypeError, ValueError) as exc:
        raise ProductionChatResourceProvisioningRequestConsumerError(
            "invalid_resource_provisioning_id") from exc

    prefix = f"local-model/resource-provisioning-requests/{selected}"
    try:
        request_bytes = installation_handle.read_regular(
            installation_handle.fixed_object(prefix + "/request.json"))
        receipt_bytes = installation_handle.read_regular(
            installation_handle.fixed_object(prefix + "/publication-receipt.json"))
    except (InstallationStateError, OSError) as exc:
        raise ProductionChatResourceProvisioningRequestConsumerError(
            "published_request_custody_unavailable") from exc

    request_value = _mapping(request_bytes, "invalid_request_custody_json")
    if _canonical(request_value, "invalid_request_custody_json") != request_bytes:
        raise ProductionChatResourceProvisioningRequestConsumerError("noncanonical_request_custody")
    try:
        request = load_provisioning_request(request_bytes)
        intent = prepare_provisioning_intent(request_bytes)
    except ProductionChatResourceProvisioningActuatorError as exc:
        raise ProductionChatResourceProvisioningRequestConsumerError(
            "invalid_published_request") from exc
    if request._packet != request_bytes:
        raise ProductionChatResourceProvisioningRequestConsumerError("request_byte_binding_mismatch")

    receipt = _mapping(receipt_bytes, "invalid_publication_receipt_json")
    if set(receipt) != _RECEIPT_FIELDS:
        raise ProductionChatResourceProvisioningRequestConsumerError("receipt_fields_not_exact")
    if _canonical(receipt, "invalid_publication_receipt_json") != receipt_bytes:
        raise ProductionChatResourceProvisioningRequestConsumerError("noncanonical_receipt_custody")
    if receipt.get("schema_version") != PUBLICATION_RECEIPT_SCHEMA:
        raise ProductionChatResourceProvisioningRequestConsumerError("unsupported_receipt_schema")
    claimed_receipt_digest = _require_digest(receipt.get("receipt_digest"), "invalid_receipt_digest")
    receipt_body = dict(receipt)
    receipt_body.pop("receipt_digest")
    if _sha(_canonical(receipt_body, "invalid_publication_receipt_json")) != claimed_receipt_digest:
        raise ProductionChatResourceProvisioningRequestConsumerError("receipt_digest_mismatch")

    if (request.installation_identity != installation_handle.identity.value
            or receipt.get("installation_identity") != installation_handle.identity.value):
        raise ProductionChatResourceProvisioningRequestConsumerError("installation_identity_mismatch")
    if (request.resource_provisioning_id != selected
            or receipt.get("resource_provisioning_id") != selected):
        raise ProductionChatResourceProvisioningRequestConsumerError("resource_provisioning_id_mismatch")
    if receipt.get("request_digest") != request.request_digest:
        raise ProductionChatResourceProvisioningRequestConsumerError("request_digest_binding_mismatch")
    if receipt.get("intent_digest") != intent.intent_digest:
        raise ProductionChatResourceProvisioningRequestConsumerError("intent_digest_binding_mismatch")

    artifact_bindings = {
        "principal_artifact_sha256": request.principal_artifact,
        "provenance_artifact_sha256": request.provenance_artifact,
        "trusted_issuer_catalog_artifact_sha256": request.trusted_issuer_catalog_artifact,
        "principal_revocation_registry_artifact_sha256": request.principal_revocation_registry_artifact,
        "resource_policy_artifact_sha256": request.resource_policy_artifact,
    }
    for field, exact_bytes in artifact_bindings.items():
        if receipt.get(field) != _sha(exact_bytes):
            raise ProductionChatResourceProvisioningRequestConsumerError(
                f"{field}_binding_mismatch")

    for field in (
        "principal_id", "principal_binding_digest", "provenance_digest",
        "trusted_issuer_catalog_version", "trusted_issuer_catalog_digest",
        "revocation_registry_version", "revocation_registry_digest", "resource_policy_digest",
    ):
        if receipt.get(field) != getattr(intent, field):
            raise ProductionChatResourceProvisioningRequestConsumerError(f"{field}_binding_mismatch")

    _require_publication_time(receipt.get("verified_at"))
    authority_digest = _require_digest(
        receipt.get("authority_definition_digest"), "invalid_authority_definition_digest")
    if (authority_digest != AUTHORITY_DEFINITION_DIGEST
            or authority_definition_digest(
                PRODUCTION_CHAT_RESOURCE_PROVISIONING_REQUEST_PUBLISH_DEFINITION
            ) != AUTHORITY_DEFINITION_DIGEST):
        raise ProductionChatResourceProvisioningRequestConsumerError(
            "authority_definition_digest_mismatch")
    exact_packet = request._packet
    if type(exact_packet) is not bytes:
        raise ProductionChatResourceProvisioningRequestConsumerError("request_byte_binding_mismatch")
    return exact_packet


__all__ = [
    "ProductionChatResourceProvisioningRequestConsumerError",
    "load_published_production_chat_resource_provisioning_request",
]
