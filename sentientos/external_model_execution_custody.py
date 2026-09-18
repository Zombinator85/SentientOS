"""Deterministic execution custody for future external-model effects.

This module consumes (but cannot issue) admission evidence.  Its sole production
transport is deliberately unavailable and performs no credential or network I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

from sentientos.external_model_custody import (
    CustodyRegistry, CustodyValidationError, EndpointIdentity,
    ExternalModelServiceIdentity, InvocationReceipt, InvocationRequestEnvelope,
    InvocationResultEnvelope, canonical_bytes, digest,
)
from sentientos.runtime_admission import AdmissionEvidence, RuntimeAdmissionVerifier

CONFIG_SCHEMA = "sentientos.external_model_service_catalog:v1"
RECEIPT_SCHEMA = "sentientos.external_model_invocation_receipts:v1"
ADMISSION_KIND = "external_model_inference"  # identity only; never registered here


@dataclass(frozen=True)
class ConfiguredExternalModelService:
    service: ExternalModelServiceIdentity
    endpoint: EndpointIdentity
    permitted_model_ids: tuple[str, ...]
    credential_ref: str | None
    enabled: bool
    provenance: str
    version: int

    def payload(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def configuration_digest(self) -> str:
        return digest({"schema": CONFIG_SCHEMA, **self.payload()})

    def validate(self) -> None:
        self.endpoint.validate()
        self.service.validate({self.endpoint.endpoint_id: self.endpoint})
        if self.service.endpoint_ids != (self.endpoint.endpoint_id,):
            raise CustodyValidationError("configured_endpoint_not_exact")
        if not self.permitted_model_ids or len(set(self.permitted_model_ids)) != len(self.permitted_model_ids):
            raise CustodyValidationError("invalid_configured_model_scope")
        if tuple(sorted(self.permitted_model_ids)) != self.permitted_model_ids or any("*" in value for value in self.permitted_model_ids):
            raise CustodyValidationError("unbounded_configured_model_scope")
        if self.version < 1 or not self.provenance.strip():
            raise CustodyValidationError("invalid_configuration_provenance")


class ExternalModelServiceCatalog:
    """Positive configuration registry; configuration never implies admission."""

    def __init__(self, entries: Mapping[str, ConfiguredExternalModelService]) -> None:
        self._entries = dict(entries)
        for service_id, entry in self._entries.items():
            entry.validate()
            if service_id != entry.service.service_id:
                raise CustodyValidationError("catalog_service_key_mismatch")

    def resolve(self, request: InvocationRequestEnvelope) -> ConfiguredExternalModelService:
        entry = self._entries.get(request.service_id)
        if entry is None:
            raise CustodyValidationError("unknown_configured_service")
        if not entry.enabled:
            raise CustodyValidationError("configured_service_disabled")
        if request.endpoint_id != entry.endpoint.endpoint_id:
            raise CustodyValidationError("configured_endpoint_mismatch")
        if request.model_id not in entry.permitted_model_ids:
            raise CustodyValidationError("model_outside_configured_scope")
        if request.credential_ref != entry.credential_ref:
            raise CustodyValidationError("configured_credential_reference_mismatch")
        return entry

    def save(self, path: Path) -> None:
        rows = [self._entries[key].payload() for key in sorted(self._entries)]
        payload = {"schema": CONFIG_SCHEMA, "entries": rows}
        payload["catalog_digest"] = digest(payload)
        _atomic_write(path, canonical_bytes(payload))

    @classmethod
    def load(cls, path: Path) -> "ExternalModelServiceCatalog":
        payload = _read_object(path, "corrupt_service_catalog")
        claimed = payload.pop("catalog_digest", None)
        if payload.get("schema") != CONFIG_SCHEMA or claimed != digest(payload):
            raise CustodyValidationError("corrupt_service_catalog")
        entries: dict[str, ConfiguredExternalModelService] = {}
        try:
            for raw in payload["entries"]:
                service_payload = dict(raw["service"])
                service_payload["endpoint_ids"] = tuple(service_payload["endpoint_ids"])
                service = ExternalModelServiceIdentity(**service_payload)
                endpoint = EndpointIdentity(**raw["endpoint"])
                entry = ConfiguredExternalModelService(service, endpoint, tuple(raw["permitted_model_ids"]), raw["credential_ref"], raw["enabled"], raw["provenance"], raw["version"])
                entries[service.service_id] = entry
        except (KeyError, TypeError, ValueError) as exc:
            raise CustodyValidationError("corrupt_service_catalog") from exc
        return cls(entries)


@dataclass(frozen=True)
class OpaqueCredentialUseHandle:
    credential_ref: str
    service_id: str
    usage_class: str = "external_model_inference_authentication"
    provenance: str = "configured-reference"
    available: bool = False


class SecretResolutionPort(Protocol):
    """Future narrow boundary.  No production implementation is provided."""
    def use_for_transport(self, handle: OpaqueCredentialUseHandle) -> object: ...


@dataclass(frozen=True)
class ExternalAdmissionEvidence:
    """Evidence supplied by an authority owner outside this custody module."""
    evidence_ref: str
    authority_identity: str
    principal_id: str
    service_id: str
    endpoint_id: str
    request_binding_digest: str
    configuration_digest: str
    sequence: int
    valid_through_sequence: int
    admitted: bool
    synthetic_test_only: bool = False


@dataclass(frozen=True)
class AdmittedInvocation:
    request: InvocationRequestEnvelope
    configuration_digest: str
    credential_handle: OpaqueCredentialUseHandle | None
    admission_evidence_ref: str


@dataclass(frozen=True)
class TransportEvidence:
    request_binding_digest: str
    attempted: bool
    succeeded: bool
    provider_responded: bool
    response_payload_digest: str | None
    status_code: int | None
    synthetic_test_only: bool = False
    unavailable: bool = False


class ExternalModelTransport(Protocol):
    def invoke(self, invocation: AdmittedInvocation) -> TransportEvidence: ...


class NullExternalModelTransport:
    """Production transport: reports unavailability without attempting an effect."""
    def invoke(self, invocation: AdmittedInvocation) -> TransportEvidence:
        return TransportEvidence(invocation.request.binding_digest, False, False, False, None, None, unavailable=True)


class InvocationReceiptStore:
    """Atomic, hash-linked receipt persistence with strict restart validation."""
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> tuple[InvocationReceipt, ...]:
        if not self.path.exists():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("schema") != RECEIPT_SCHEMA or not isinstance(payload.get("receipts"), list):
                raise ValueError
            receipts = tuple(InvocationReceipt(**row) for row in payload["receipts"])
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise CustodyValidationError("corrupt_invocation_receipt_store") from exc
        previous = None
        for sequence, receipt in enumerate(receipts, 1):
            if receipt.sequence != sequence or receipt.previous_receipt_digest != previous:
                raise CustodyValidationError("corrupt_invocation_receipt_chain")
            previous = receipt.receipt_digest
        return receipts

    def append(self, receipt: InvocationReceipt) -> None:
        receipts = self.load()
        expected_previous = receipts[-1].receipt_digest if receipts else None
        if receipt.sequence != len(receipts) + 1 or receipt.previous_receipt_digest != expected_previous:
            raise CustodyValidationError("receipt_order_mismatch")
        _atomic_write(self.path, canonical_bytes({"schema": RECEIPT_SCHEMA, "receipts": [item.to_dict() for item in (*receipts, receipt)]}))


class ExternalModelInferenceController:
    """Custody orchestrator.  It validates supplied admission; it cannot issue it."""
    def __init__(self, *, catalog: ExternalModelServiceCatalog, registry: CustodyRegistry, transport: ExternalModelTransport, receipts: InvocationReceiptStore, admission_verifier: RuntimeAdmissionVerifier | None = None, admission_capability_id: str = ADMISSION_KIND) -> None:
        self.catalog, self.registry, self.transport, self.receipts = catalog, registry, transport, receipts
        self.admission_verifier, self.admission_capability_id = admission_verifier, admission_capability_id

    def execute(self, request: InvocationRequestEnvelope, *, credential_handle: OpaqueCredentialUseHandle | None, admission: ExternalAdmissionEvidence | AdmissionEvidence | None, current_sequence: int) -> InvocationReceipt:
        entry = self.catalog.resolve(request)
        self.registry.validate_request(request)
        if entry.credential_ref is not None:
            if credential_handle is None:
                raise CustodyValidationError("credential_use_handle_required")
            if (credential_handle.credential_ref, credential_handle.service_id) != (entry.credential_ref, request.service_id):
                raise CustodyValidationError("credential_handle_service_mismatch")
        if admission is None:
            raise CustodyValidationError("external_admission_required")
        if isinstance(admission, AdmissionEvidence):
            if self.admission_verifier is None:
                raise CustodyValidationError("runtime_admission_verifier_required")
            try:
                self.admission_verifier.verify(admission, current_sequence=current_sequence, capability_id=self.admission_capability_id, principal_id=request.principal.principal_id, effect=request.required_effect.effect_kind, subject_id=f"{request.service_id}:{request.endpoint_id}", request_configuration_digest=digest({"request": request.binding_digest, "configuration": entry.configuration_digest}))
            except ValueError as exc:
                raise CustodyValidationError(str(exc)) from exc
            evidence_ref = admission.admission_id
        else:
            expected = (request.principal.principal_id, request.service_id, request.endpoint_id, request.binding_digest, entry.configuration_digest)
            actual = (admission.principal_id, admission.service_id, admission.endpoint_id, admission.request_binding_digest, admission.configuration_digest)
            if not admission.admitted or admission.authority_identity != ADMISSION_KIND or actual != expected:
                raise CustodyValidationError("admission_request_mismatch")
            if admission.sequence > current_sequence or admission.valid_through_sequence < current_sequence:
                raise CustodyValidationError("stale_or_malformed_admission")
            evidence_ref = admission.evidence_ref
        invocation = AdmittedInvocation(request, entry.configuration_digest, credential_handle, evidence_ref)
        evidence = self.transport.invoke(invocation)
        if evidence.request_binding_digest != request.binding_digest:
            raise CustodyValidationError("transport_request_correlation_mismatch")
        if evidence.succeeded and not evidence.attempted or evidence.provider_responded and not evidence.attempted:
            raise CustodyValidationError("malformed_transport_evidence")
        if evidence.provider_responded != bool(evidence.response_payload_digest):
            raise CustodyValidationError("malformed_transport_response")
        result = InvocationResultEnvelope(request.request_id, request.binding_digest, request.service_id, request.endpoint_id, evidence_ref, True, evidence.attempted, evidence.succeeded, evidence.provider_responded, evidence.response_payload_digest, evidence.status_code, current_sequence if evidence.attempted else None, current_sequence if evidence.attempted else None, synthetic=evidence.synthetic_test_only or not evidence.attempted)
        prior = self.receipts.load()
        receipt = InvocationReceipt(f"receipt-{request.request_id}-{len(prior)+1}", request.request_id, request.binding_digest, request.principal.principal_id, request.service_id, request.endpoint_id, request.credential_ref, evidence_ref, True, evidence.attempted, evidence.succeeded, evidence.response_payload_digest, digest(result.to_dict()), len(prior)+1, prior[-1].receipt_digest if prior else None, synthetic=evidence.synthetic_test_only or not evidence.attempted, effect_occurred=evidence.attempted and not evidence.synthetic_test_only)
        self.registry.validate_receipt(receipt, request, result)
        self.receipts.append(receipt)
        if evidence.unavailable:
            raise CustodyValidationError("external_model_transport_unavailable")
        return receipt


def _read_object(path: Path, error: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CustodyValidationError(error) from exc
    if not isinstance(value, dict):
        raise CustodyValidationError(error)
    return value


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists(): temporary.unlink()
