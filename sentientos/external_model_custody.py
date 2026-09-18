"""Offline custody types for a possible future external-model invocation.

The types in this module only describe and validate evidence.  They perform no
I/O, consult no credentials, and confer no capability or effect authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit


SCHEMA = "sentientos.external_model_invocation_custody:v1"
PRINCIPAL_KIND = "deterministic_external_model_inference_controller"
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_KEYS = frozenset({"secret", "secret_value", "api_key", "token", "password", "authorization", "bearer"})


class CustodyValidationError(ValueError):
    """An inert custody object is malformed or contradicts its registry."""


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def payload_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _identifier(value: str, label: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise CustodyValidationError(f"invalid_{label}")


def _digest(value: str, label: str) -> None:
    if not _SHA256.fullmatch(value):
        raise CustodyValidationError(f"invalid_{label}")


def _no_secrets(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _SECRET_KEYS:
                raise CustodyValidationError("secret_material_forbidden")
            _no_secrets(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _no_secrets(child)


@dataclass(frozen=True)
class EndpointIdentity:
    endpoint_id: str
    scheme: str
    host: str
    port: int
    path_prefix: str
    redirects_allowed: bool = False

    def validate(self) -> None:
        _identifier(self.endpoint_id, "endpoint_id")
        if self.scheme not in {"https"}:
            raise CustodyValidationError("invalid_endpoint_scheme")
        if not self.host or "*" in self.host or self.host.startswith(".") or "://" in self.host:
            raise CustodyValidationError("invalid_endpoint_host")
        parsed = urlsplit(f"{self.scheme}://{self.host}:{self.port}{self.path_prefix}")
        if parsed.hostname != self.host or not 1 <= self.port <= 65535:
            raise CustodyValidationError("malformed_endpoint")
        if not self.path_prefix.startswith("/") or "*" in self.path_prefix or ".." in self.path_prefix:
            raise CustodyValidationError("invalid_endpoint_path_scope")
        if self.redirects_allowed:
            raise CustodyValidationError("redirect_identity_unbounded")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExternalModelServiceIdentity:
    service_id: str
    label: str
    service_class: str
    endpoint_ids: tuple[str, ...]
    configured: bool = True
    authorized: bool = False

    def validate(self, endpoints: Mapping[str, EndpointIdentity]) -> None:
        _identifier(self.service_id, "service_id")
        if not self.label.strip() or not self.service_class.strip() or not self.endpoint_ids:
            raise CustodyValidationError("incomplete_service_identity")
        if self.authorized:
            raise CustodyValidationError("custody_cannot_authorize_service")
        if len(set(self.endpoint_ids)) != len(self.endpoint_ids):
            raise CustodyValidationError("duplicate_endpoint_identity")
        for endpoint_id in self.endpoint_ids:
            if endpoint_id not in endpoints:
                raise CustodyValidationError("unknown_service_endpoint")
            endpoints[endpoint_id].validate()


@dataclass(frozen=True)
class CredentialReference:
    credential_ref: str
    service_id: str
    usage_class: str = "external_model_inference_authentication"
    available: bool = False
    use_authorized: bool = False

    def validate(self) -> None:
        _identifier(self.credential_ref, "credential_ref")
        _identifier(self.service_id, "credential_service_id")
        if self.usage_class != "external_model_inference_authentication":
            raise CustodyValidationError("invalid_credential_usage_class")
        if self.use_authorized:
            raise CustodyValidationError("custody_cannot_authorize_credential")


@dataclass(frozen=True)
class PrincipalIdentity:
    principal_id: str
    principal_kind: str = PRINCIPAL_KIND
    empowered: bool = False

    def validate(self) -> None:
        _identifier(self.principal_id, "principal_id")
        if self.principal_kind != PRINCIPAL_KIND:
            raise CustodyValidationError("principal_kind_mismatch")
        if self.empowered:
            raise CustodyValidationError("custody_principal_cannot_be_empowered")


@dataclass(frozen=True)
class RequiredEffectDescription:
    effect_kind: str
    endpoint_id: str
    service_id: str
    admission_required: bool = True
    admitted: bool = False

    def validate(self) -> None:
        if self.effect_kind != "bounded_external_model_network_egress":
            raise CustodyValidationError("invalid_required_effect")
        if not self.admission_required or self.admitted:
            raise CustodyValidationError("required_effect_has_authority")


@dataclass(frozen=True)
class InvocationRequestEnvelope:
    request_id: str
    service_id: str
    endpoint_id: str
    credential_ref: str | None
    model_id: str
    payload_digest: str
    generation_parameters: tuple[tuple[str, int | float | bool | str], ...]
    provenance: str
    principal: PrincipalIdentity
    required_effect: RequiredEffectDescription
    sequence: int
    schema: str = SCHEMA
    admitted: bool = False

    def to_dict(self) -> dict[str, Any]: return asdict(self)
    @property
    def binding_digest(self) -> str: return digest(self.to_dict())


@dataclass(frozen=True)
class InvocationResultEnvelope:
    request_id: str
    request_binding_digest: str
    service_id: str
    endpoint_id: str
    admission_evidence_ref: str | None
    request_admitted: bool
    execution_attempted: bool
    execution_succeeded: bool
    service_responded: bool
    response_payload_digest: str | None
    status_code: int | None
    started_sequence: int | None
    completed_sequence: int | None
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class InvocationReceipt:
    receipt_id: str
    request_id: str
    request_binding_digest: str
    principal_id: str
    service_id: str
    endpoint_id: str
    credential_ref: str | None
    admission_evidence_ref: str | None
    request_admitted: bool
    execution_attempted: bool
    execution_succeeded: bool
    response_payload_digest: str | None
    result_digest: str
    sequence: int
    previous_receipt_digest: str | None = None
    synthetic: bool = True
    effect_occurred: bool = False

    def to_dict(self) -> dict[str, Any]: return asdict(self)
    @property
    def receipt_digest(self) -> str: return digest(self.to_dict())


@dataclass(frozen=True)
class CustodyRegistry:
    endpoints: Mapping[str, EndpointIdentity]
    services: Mapping[str, ExternalModelServiceIdentity]
    credentials: Mapping[str, CredentialReference]

    def validate_request(self, request: InvocationRequestEnvelope) -> str:
        _no_secrets(request.to_dict())
        _identifier(request.request_id, "request_id")
        _identifier(request.model_id, "model_id")
        _digest(request.payload_digest, "payload_digest")
        if request.schema != SCHEMA or request.sequence < 0 or not request.provenance.strip() or request.admitted:
            raise CustodyValidationError("malformed_or_authorized_request")
        request.principal.validate()
        request.required_effect.validate()
        service = self.services.get(request.service_id)
        endpoint = self.endpoints.get(request.endpoint_id)
        if service is None: raise CustodyValidationError("unknown_service_id")
        if endpoint is None: raise CustodyValidationError("unknown_endpoint_id")
        service.validate(self.endpoints)
        if request.endpoint_id not in service.endpoint_ids:
            raise CustodyValidationError("service_endpoint_mismatch")
        if (request.required_effect.service_id, request.required_effect.endpoint_id) != (request.service_id, request.endpoint_id):
            raise CustodyValidationError("required_effect_identity_mismatch")
        if request.credential_ref is not None:
            credential = self.credentials.get(request.credential_ref)
            if credential is None: raise CustodyValidationError("unknown_credential_reference")
            credential.validate()
            if credential.service_id != request.service_id:
                raise CustodyValidationError("credential_service_mismatch")
        keys = [item[0] for item in request.generation_parameters]
        if any(key.lower() in _SECRET_KEYS for key in keys):
            raise CustodyValidationError("secret_material_forbidden")
        if keys != sorted(keys) or len(keys) != len(set(keys)) or len(keys) > 16:
            raise CustodyValidationError("unbounded_generation_parameters")
        return request.binding_digest

    def validate_result(self, result: InvocationResultEnvelope, request: InvocationRequestEnvelope) -> str:
        _no_secrets(result.to_dict())
        binding = self.validate_request(request)
        if (result.request_id, result.request_binding_digest, result.service_id, result.endpoint_id) != (request.request_id, binding, request.service_id, request.endpoint_id):
            raise CustodyValidationError("result_request_correlation_mismatch")
        if result.execution_succeeded and not result.execution_attempted:
            raise CustodyValidationError("success_without_attempt")
        if result.service_responded and not result.execution_attempted:
            raise CustodyValidationError("response_without_attempt")
        if result.request_admitted != bool(result.admission_evidence_ref):
            raise CustodyValidationError("admission_evidence_mismatch")
        if result.service_responded != bool(result.response_payload_digest):
            raise CustodyValidationError("response_digest_mismatch")
        if result.response_payload_digest: _digest(result.response_payload_digest, "response_payload_digest")
        if not result.synthetic and not result.execution_attempted:
            raise CustodyValidationError("non_synthetic_non_execution_result")
        return digest(result.to_dict())

    def validate_receipt(self, receipt: InvocationReceipt, request: InvocationRequestEnvelope, result: InvocationResultEnvelope) -> str:
        _no_secrets(receipt.to_dict())
        result_digest = self.validate_result(result, request)
        expected = (request.request_id, request.binding_digest, request.principal.principal_id, request.service_id, request.endpoint_id, request.credential_ref)
        actual = (receipt.request_id, receipt.request_binding_digest, receipt.principal_id, receipt.service_id, receipt.endpoint_id, receipt.credential_ref)
        if actual != expected or receipt.result_digest != result_digest:
            raise CustodyValidationError("malformed_receipt_binding")
        if (receipt.request_admitted, receipt.execution_attempted, receipt.execution_succeeded, receipt.response_payload_digest) != (result.request_admitted, result.execution_attempted, result.execution_succeeded, result.response_payload_digest):
            raise CustodyValidationError("receipt_result_mismatch")
        if not receipt.synthetic or receipt.effect_occurred or receipt.sequence < 0:
            raise CustodyValidationError("receipt_claims_real_effect")
        if receipt.previous_receipt_digest: _digest(receipt.previous_receipt_digest, "previous_receipt_digest")
        return receipt.receipt_digest
