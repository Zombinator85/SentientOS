"""Deterministic execution custody for future external-model effects.

This module consumes (but cannot issue) admission evidence.  Its sole production
transport is deliberately unavailable and performs no credential or network I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, TypeVar, runtime_checkable

from sentientos.external_model_custody import (
    CustodyRegistry, CustodyValidationError, EndpointIdentity,
    ExternalModelServiceIdentity, InvocationReceipt, InvocationRequestEnvelope,
    InvocationResultEnvelope, canonical_bytes, digest,
)
from sentientos.runtime_admission import AdmissionEvidence, RuntimeAdmissionVerifier
from sentientos.external_model_material import (
    GovernedRequestMaterialResolver, ResponseConsumer, verify_and_handoff_response,
)

LEGACY_CONFIG_SCHEMA = "sentientos.external_model_service_catalog:v1"
CONFIG_SCHEMA = "sentientos.external_model_service_catalog:v2"
RECEIPT_SCHEMA = "sentientos.external_model_invocation_receipts:v1"
ADMISSION_KIND = "external_model_inference"  # identity only; definition registration grants nothing


@dataclass(frozen=True)
class ExactHTTPSTransportProfile:
    """Configuration-bound, closed framing for one exact HTTPS endpoint."""
    profile_version: int
    method: str
    media_type: str
    authentication_mode: str

    def validate(self) -> None:
        if self.profile_version != 1 or self.method != "POST":
            raise CustodyValidationError("invalid_live_transport_profile")
        if self.media_type not in {"application/json"}:
            raise CustodyValidationError("invalid_live_transport_media_type")
        if self.authentication_mode not in {"none", "bearer", "x-api-key"}:
            raise CustodyValidationError("invalid_live_transport_authentication")


@dataclass(frozen=True)
class ConfiguredExternalModelService:
    service: ExternalModelServiceIdentity
    endpoint: EndpointIdentity
    permitted_model_ids: tuple[str, ...]
    credential_ref: str | None
    enabled: bool
    provenance: str
    version: int
    live_transport: ExactHTTPSTransportProfile | None = None

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
        if self.live_transport is not None:
            self.live_transport.validate()
            expects_credential = self.live_transport.authentication_mode != "none"
            if expects_credential != (self.credential_ref is not None):
                raise CustodyValidationError("live_transport_credential_binding_mismatch")


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
        schema = payload.get("schema")
        if schema not in {CONFIG_SCHEMA, LEGACY_CONFIG_SCHEMA} or claimed != digest(payload):
            raise CustodyValidationError("corrupt_service_catalog")
        entries: dict[str, ConfiguredExternalModelService] = {}
        try:
            for raw in payload["entries"]:
                service_payload = dict(raw["service"])
                service_payload["endpoint_ids"] = tuple(service_payload["endpoint_ids"])
                service = ExternalModelServiceIdentity(**service_payload)
                endpoint = EndpointIdentity(**raw["endpoint"])
                profile = None
                if schema == CONFIG_SCHEMA:
                    raw_profile = raw.get("live_transport")
                    if raw_profile is not None:
                        if not isinstance(raw_profile, dict) or set(raw_profile) != {"profile_version", "method", "media_type", "authentication_mode"}:
                            raise ValueError
                        profile = ExactHTTPSTransportProfile(**raw_profile)
                elif "live_transport" in raw:
                    raise ValueError
                entry = ConfiguredExternalModelService(service, endpoint, tuple(raw["permitted_model_ids"]), raw["credential_ref"], raw["enabled"], raw["provenance"], raw["version"], profile)
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


class CredentialBackend(Protocol):
    """Read one exact service-scoped secret; deliberately has no admin surface."""
    def read_exact(self, *, service_id: str, credential_ref: str) -> bytearray: ...


class CredentialResolutionError(CustodyValidationError):
    """A fail-closed error which never incorporates backend or secret text."""


_CredentialResult = TypeVar("_CredentialResult")


class GovernedCredentialResolver:
    """Resolve only the credential bound to an exactly admitted invocation."""
    def __init__(self, *, catalog: ExternalModelServiceCatalog, registry: CustodyRegistry,
                 admission_verifier: RuntimeAdmissionVerifier, backend: CredentialBackend,
                 admission_capability_id: str = ADMISSION_KIND) -> None:
        self._catalog, self._registry = catalog, registry
        self._admission_verifier, self._backend = admission_verifier, backend
        self._admission_capability_id = admission_capability_id

    def use_for_invocation(self, *, request: InvocationRequestEnvelope,
                           credential_handle: OpaqueCredentialUseHandle | None,
                           admission: AdmissionEvidence | None, current_sequence: int,
                           consumer: Callable[[memoryview], _CredentialResult]) -> _CredentialResult:
        """Expose a short-lived read-only view only while ``consumer`` executes."""
        try:
            entry = self._catalog.resolve(request)
            self._registry.validate_request(request)
        except CustodyValidationError as exc:
            raise CredentialResolutionError(str(exc)) from exc
        if admission is None:
            raise CredentialResolutionError("credential_resolution_admission_required")
        if entry.credential_ref is None or credential_handle is None:
            raise CredentialResolutionError("credential_resolution_not_configured")
        if (credential_handle.credential_ref != entry.credential_ref
                or credential_handle.service_id != entry.service.service_id
                or credential_handle.usage_class != "external_model_inference_authentication"):
            raise CredentialResolutionError("credential_resolution_binding_mismatch")
        try:
            self._admission_verifier.verify(
                admission, current_sequence=current_sequence,
                capability_id=self._admission_capability_id,
                principal_id=request.principal.principal_id,
                effect=request.required_effect.effect_kind,
                subject_id=f"{request.service_id}:{request.endpoint_id}",
                request_configuration_digest=digest({"request": request.binding_digest, "configuration": entry.configuration_digest}),
            )
        except ValueError as exc:
            raise CredentialResolutionError(str(exc)) from exc
        try:
            secret = self._backend.read_exact(service_id=entry.service.service_id, credential_ref=entry.credential_ref)
        except CredentialResolutionError:
            raise
        except Exception as exc:
            raise CredentialResolutionError("credential_backend_unavailable") from exc
        if not isinstance(secret, bytearray):
            raise CredentialResolutionError("corrupt_credential_material")
        if not secret:
            raise CredentialResolutionError("credential_secret_missing")
        try:
            return consumer(memoryview(secret).toreadonly())
        finally:
            secret[:] = b"\x00" * len(secret)


class OSKeyringCredentialBackend:
    """Read-only production backend using an operator-provisioned OS keyring."""
    _NAMESPACE = "sentientos.external_model"

    def read_exact(self, *, service_id: str, credential_ref: str) -> bytearray:
        import keyring
        try:
            value = keyring.get_password(f"{self._NAMESPACE}.{service_id}", credential_ref)
        except Exception as exc:
            raise CredentialResolutionError("credential_backend_unavailable") from exc
        if value is None:
            raise CredentialResolutionError("credential_secret_missing")
        if not isinstance(value, str) or not value:
            raise CredentialResolutionError("corrupt_credential_material")
        return bytearray(value, "utf-8")


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


@dataclass(frozen=True)
class MaterialTransportResult:
    """Transient response bytes paired with transport evidence for verification."""
    evidence: TransportEvidence
    response_material: bytearray | None = field(repr=False)


class ExternalModelTransport(Protocol):
    def invoke(self, invocation: AdmittedInvocation) -> TransportEvidence: ...


@runtime_checkable
class CredentialedExternalModelTransport(Protocol):
    """Future transport seam; no production implementation exists."""
    def invoke_with_credential(self, invocation: AdmittedInvocation, credential: memoryview) -> TransportEvidence: ...


@runtime_checkable
class MaterialExternalModelTransport(Protocol):
    """Future provider-neutral seam; current production has no implementation."""
    def invoke_with_material(self, invocation: AdmittedInvocation,
                             request_material: memoryview,
                             credential: memoryview | None) -> MaterialTransportResult: ...


class NullExternalModelTransport:
    """Production transport: reports unavailability without attempting an effect."""
    def invoke(self, invocation: AdmittedInvocation) -> TransportEvidence:
        return TransportEvidence(invocation.request.binding_digest, False, False, False, None, None, unavailable=True)

    def operational_readiness(self) -> Any:
        from sentientos.external_model_operational_feasibility import LocalReadiness, seal_local_readiness
        return seal_local_readiness(LocalReadiness("transport", "null_external_model_transport:v1", False))


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
    def __init__(self, *, catalog: ExternalModelServiceCatalog, registry: CustodyRegistry, transport: ExternalModelTransport | CredentialedExternalModelTransport | MaterialExternalModelTransport, receipts: InvocationReceiptStore, admission_verifier: RuntimeAdmissionVerifier | None = None, admission_capability_id: str = ADMISSION_KIND, credential_resolver: GovernedCredentialResolver | None = None, request_material_resolver: GovernedRequestMaterialResolver | None = None) -> None:
        self.catalog, self.registry, self.transport, self.receipts = catalog, registry, transport, receipts
        self.admission_verifier, self.admission_capability_id = admission_verifier, admission_capability_id
        self.credential_resolver = credential_resolver
        self.request_material_resolver = request_material_resolver

    def execute(self, request: InvocationRequestEnvelope, *, credential_handle: OpaqueCredentialUseHandle | None, admission: ExternalAdmissionEvidence | AdmissionEvidence | None, current_sequence: int, response_consumer: ResponseConsumer | None = None) -> InvocationReceipt:
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
        response_material: bytearray | None = None
        if isinstance(self.transport, MaterialExternalModelTransport):
            if self.request_material_resolver is None or not isinstance(admission, AdmissionEvidence):
                raise CustodyValidationError("governed_request_material_resolver_required")
            material_transport: MaterialExternalModelTransport = self.transport
            def invoke_with_request(material: memoryview) -> MaterialTransportResult:
                if entry.credential_ref is None:
                    return material_transport.invoke_with_material(invocation, material, None)
                if self.credential_resolver is None:
                    raise CustodyValidationError("governed_credential_resolver_required")
                return self.credential_resolver.use_for_invocation(
                    request=request, credential_handle=credential_handle, admission=admission,
                    current_sequence=current_sequence,
                    consumer=lambda secret: material_transport.invoke_with_material(invocation, material, secret),
                )
            material_result = self.request_material_resolver.use_for_invocation(
                request=request, admission=admission, current_sequence=current_sequence,
                admission_evidence_ref=evidence_ref, consumer=invoke_with_request,
            )
            if not isinstance(material_result, MaterialTransportResult):
                raise CustodyValidationError("malformed_material_transport_result")
            evidence, response_material = material_result.evidence, material_result.response_material
        elif isinstance(self.transport, CredentialedExternalModelTransport):
            if self.credential_resolver is None or not isinstance(admission, AdmissionEvidence):
                raise CustodyValidationError("governed_credential_resolver_required")
            credentialed_transport: CredentialedExternalModelTransport = self.transport
            evidence = self.credential_resolver.use_for_invocation(
                request=request, credential_handle=credential_handle, admission=admission,
                current_sequence=current_sequence,
                consumer=lambda secret: credentialed_transport.invoke_with_credential(invocation, secret),
            )
        else:
            evidence = self.transport.invoke(invocation)
        try:
            if evidence.request_binding_digest != request.binding_digest:
                raise CustodyValidationError("transport_request_correlation_mismatch")
            if evidence.succeeded and not evidence.attempted or evidence.provider_responded and not evidence.attempted:
                raise CustodyValidationError("malformed_transport_evidence")
            if evidence.provider_responded != bool(evidence.response_payload_digest):
                raise CustodyValidationError("malformed_transport_response")
            if response_material is not None:
                if not evidence.attempted or not evidence.provider_responded:
                    raise CustodyValidationError("malformed_transport_response_material")
                verify_and_handoff_response(
                    request=request, response_material=response_material,
                    claimed_digest=evidence.response_payload_digest,
                    synthetic_test_only=evidence.synthetic_test_only,
                    consumer=response_consumer,
                )
            elif isinstance(self.transport, MaterialExternalModelTransport) and evidence.provider_responded:
                raise CustodyValidationError("response_material_required")
        except Exception:
            if response_material is not None:
                response_material[:] = b"\x00" * len(response_material)
            raise
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
