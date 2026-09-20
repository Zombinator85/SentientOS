"""Bounded, non-authoritative custody for external-model material.

This module has no production material store.  A source is asked for one exact
admitted invocation and returns an owned mutable buffer.  The resolver validates
all metadata and admission bindings before exposing a read-only view, then
overwrites that buffer in a ``finally`` block.  This is best-effort clearing of
the owned ``bytearray``; Python and the operating system may retain copies.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Protocol, TypeVar

from sentientos.external_model_custody import (
    CustodyRegistry, CustodyValidationError, InvocationRequestEnvelope, digest,
)
from sentientos.runtime_admission import AdmissionEvidence, RuntimeAdmissionVerifier

MAX_REQUEST_MATERIAL_BYTES = 1_048_576
MAX_RESPONSE_MATERIAL_BYTES = 4_194_304


class RequestMaterialError(CustodyValidationError):
    """Fail-closed error containing only bounded reason codes, never material."""


@dataclass(frozen=True)
class RequestMaterialBinding:
    """Complete invocation identity supplied to a narrow material owner."""
    request_id: str
    service_id: str
    endpoint_id: str
    model_id: str
    credential_ref: str | None
    request_binding_digest: str
    configuration_digest: str
    admission_evidence_ref: str
    expected_payload_digest: str


class RequestMaterialSource(Protocol):
    """Return an owned buffer for one complete binding; no digest-only lookup."""
    def read_for_invocation(self, binding: RequestMaterialBinding) -> bytearray: ...


class UnavailableRequestMaterialSource:
    """Safe production default until a legitimate material owner is connected."""
    def read_for_invocation(self, binding: RequestMaterialBinding) -> bytearray:
        raise RequestMaterialError("request_material_source_unavailable")

    def operational_readiness(self) -> object:
        from sentientos.external_model_operational_feasibility import LocalReadiness, seal_local_readiness
        return seal_local_readiness(LocalReadiness("request_material", "unavailable_request_material_source:v1", False))


class ConfiguredService(Protocol):
    configuration_digest: str


class ServiceCatalog(Protocol):
    def resolve(self, request: InvocationRequestEnvelope) -> ConfiguredService: ...


_T = TypeVar("_T")


class GovernedRequestMaterialResolver:
    """Expose verified material only for an exact, currently valid admission."""
    def __init__(self, *, catalog: ServiceCatalog, registry: CustodyRegistry,
                 admission_verifier: RuntimeAdmissionVerifier,
                 source: RequestMaterialSource,
                 admission_capability_id: str = "external_model_inference",
                 maximum_bytes: int = MAX_REQUEST_MATERIAL_BYTES) -> None:
        if maximum_bytes < 1:
            raise ValueError("invalid_request_material_size_bound")
        self._catalog, self._registry = catalog, registry
        self._admission_verifier, self._source = admission_verifier, source
        self._admission_capability_id, self.maximum_bytes = admission_capability_id, maximum_bytes

    def use_for_invocation(self, *, request: InvocationRequestEnvelope,
                           admission: AdmissionEvidence | None,
                           current_sequence: int,
                           admission_evidence_ref: str,
                           consumer: Callable[[memoryview], _T]) -> _T:
        try:
            entry = self._catalog.resolve(request)
            self._registry.validate_request(request)
        except CustodyValidationError as exc:
            raise RequestMaterialError(str(exc)) from exc
        if admission is None or admission.admission_id != admission_evidence_ref:
            raise RequestMaterialError("request_material_admission_required")
        configuration_digest = entry.configuration_digest
        try:
            self._admission_verifier.verify(
                admission, current_sequence=current_sequence,
                capability_id=self._admission_capability_id,
                principal_id=request.principal.principal_id,
                effect=request.required_effect.effect_kind,
                subject_id=f"{request.service_id}:{request.endpoint_id}",
                request_configuration_digest=digest({"request": request.binding_digest, "configuration": configuration_digest}),
            )
        except ValueError as exc:
            raise RequestMaterialError(str(exc)) from exc
        binding = RequestMaterialBinding(
            request.request_id, request.service_id, request.endpoint_id,
            request.model_id, request.credential_ref, request.binding_digest,
            configuration_digest, admission.admission_id, request.payload_digest,
        )
        try:
            material = self._source.read_for_invocation(binding)
        except RequestMaterialError:
            raise
        except Exception as exc:
            raise RequestMaterialError("request_material_source_unavailable") from exc
        if not isinstance(material, bytearray):
            raise RequestMaterialError("corrupt_request_material")
        try:
            if not material:
                raise RequestMaterialError("request_material_missing")
            if len(material) > self.maximum_bytes:
                raise RequestMaterialError("request_material_too_large")
            if "sha256:" + hashlib.sha256(material).hexdigest() != request.payload_digest:
                raise RequestMaterialError("request_material_digest_mismatch")
            return consumer(memoryview(material).toreadonly())
        finally:
            material[:] = b"\x00" * len(material)


@dataclass(frozen=True)
class UntrustedResponseMetadata:
    """Binding metadata for external data; it conveys no truth or authority."""
    request_id: str
    request_binding_digest: str
    response_payload_digest: str
    synthetic_test_only: bool
    epistemic_status: str = "untrusted_external_data"


ResponseConsumer = Callable[[UntrustedResponseMetadata, memoryview], None]


def verify_and_handoff_response(*, request: InvocationRequestEnvelope,
                                response_material: bytearray,
                                claimed_digest: str | None,
                                synthetic_test_only: bool,
                                consumer: ResponseConsumer | None,
                                maximum_bytes: int = MAX_RESPONSE_MATERIAL_BYTES) -> str:
    """Verify, briefly expose, and clear an owned response buffer."""
    if not isinstance(response_material, bytearray):
        raise RequestMaterialError("corrupt_response_material")
    try:
        if not response_material:
            raise RequestMaterialError("response_material_missing")
        if len(response_material) > maximum_bytes:
            raise RequestMaterialError("response_material_too_large")
        computed = "sha256:" + hashlib.sha256(response_material).hexdigest()
        if claimed_digest != computed:
            raise RequestMaterialError("response_material_digest_mismatch")
        if consumer is not None:
            metadata = UntrustedResponseMetadata(
                request.request_id, request.binding_digest, computed, synthetic_test_only,
            )
            consumer(metadata, memoryview(response_material).toreadonly())
        return computed
    finally:
        response_material[:] = b"\x00" * len(response_material)
