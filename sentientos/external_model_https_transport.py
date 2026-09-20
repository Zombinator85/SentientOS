"""Audited, exact-endpoint HTTPS actuator for external-model material.

Construction is configuration-bound; invocation accepts no destination or
header inputs.  The standard-library connection deliberately bypasses proxy
environment variables and never implements redirects or retries.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import ssl
from typing import Any, Callable, Protocol, cast

from sentientos.external_model_custody import CustodyValidationError
from sentientos.external_model_execution_custody import (
    AdmittedInvocation, ConfiguredExternalModelService, MaterialTransportResult,
    TransportEvidence,
)
from sentientos.external_model_material import (
    MAX_REQUEST_MATERIAL_BYTES, MAX_RESPONSE_MATERIAL_BYTES,
)

CONNECT_TIMEOUT_SECONDS = 15.0


class _Response(Protocol):
    status: int
    def getheader(self, name: str, default: str | None = None) -> str | None: ...
    def read(self, amount: int | None = None) -> bytes: ...


class _Connection(Protocol):
    def request(self, method: str, url: str, body: bytes,
                headers: dict[str, str]) -> None: ...
    def getresponse(self) -> _Response: ...
    def close(self) -> None: ...


ConnectionFactory = Callable[[str, int, float, ssl.SSLContext], _Connection]


class ExactHTTPSTransportError(CustodyValidationError):
    """Sanitized failure with truthful, non-material transport evidence."""
    def __init__(self, reason: str, evidence: TransportEvidence) -> None:
        super().__init__(reason)
        self.evidence = evidence


def _production_connection(host: str, port: int, timeout: float,
                           context: ssl.SSLContext) -> _Connection:
    return cast(_Connection, http.client.HTTPSConnection(
        host=host, port=port, timeout=timeout, context=context))


def _public_destination(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        # DNS names are exact but intentionally not pre-resolved: resolution is
        # left to the single TLS connection, avoiding a policy/connect TOCTOU.
        return ":" not in normalized
    return not (address.is_loopback or address.is_unspecified or
                address.is_link_local or address.is_multicast or
                address.is_private or address.is_reserved)


class ExactHTTPSExternalModelTransport:
    """One-shot HTTPS transport fixed to one validated configured service."""

    def __init__(self, service: ConfiguredExternalModelService, *,
                 connection_factory: ConnectionFactory = _production_connection,
                 connect_timeout_seconds: float = CONNECT_TIMEOUT_SECONDS,
                 tls_context: ssl.SSLContext | None = None) -> None:
        service.validate()
        if service.live_transport is None:
            raise CustodyValidationError("live_transport_profile_required")
        if not service.enabled:
            raise CustodyValidationError("live_transport_service_disabled")
        if not _public_destination(service.endpoint.host):
            raise CustodyValidationError("unsafe_live_transport_destination")
        if not (0 < connect_timeout_seconds <= 120):
            raise CustodyValidationError("invalid_live_transport_timeout")
        context = tls_context if tls_context is not None else ssl.create_default_context()
        if context.check_hostname is not True or context.verify_mode != ssl.CERT_REQUIRED:
            raise CustodyValidationError("verified_tls_context_required")
        self._service = service
        self._factory = connection_factory
        self._timeout = float(connect_timeout_seconds)
        self._tls_context = context

    def operational_readiness(self) -> Any:
        """Report structural readiness only; perform no DNS, TLS, or HTTP I/O."""
        from sentientos.external_model_operational_feasibility import LocalReadiness, seal_local_readiness
        return seal_local_readiness(LocalReadiness(
            "transport", "exact_https_external_model_transport:v1", True,
            exact_endpoint_enforcement=True, bounded_request_material=True,
            response_material_custody=True, structurally_configured=True,
        ))

    def invoke_with_material(self, invocation: AdmittedInvocation,
                             request_material: memoryview,
                             credential: memoryview | None) -> MaterialTransportResult:
        profile = self._service.live_transport
        assert profile is not None
        never = TransportEvidence(invocation.request.binding_digest, False, False,
                                  False, None, None)
        if invocation.configuration_digest != self._service.configuration_digest:
            raise ExactHTTPSTransportError("transport_configuration_binding_mismatch", never)
        request = invocation.request
        endpoint = self._service.endpoint
        if (request.service_id != self._service.service.service_id or
                request.endpoint_id != endpoint.endpoint_id):
            raise ExactHTTPSTransportError("transport_invocation_binding_mismatch", never)
        if len(request_material) < 1 or len(request_material) > MAX_REQUEST_MATERIAL_BYTES:
            raise ExactHTTPSTransportError("request_material_size_invalid", never)
        headers = {
            "Host": endpoint.host if endpoint.port == 443 else f"{endpoint.host}:{endpoint.port}",
            "Content-Type": profile.media_type,
            "Content-Length": str(len(request_material)),
        }
        if profile.authentication_mode == "none":
            if credential is not None:
                raise ExactHTTPSTransportError("unexpected_credential_material", never)
        else:
            if credential is None or len(credential) == 0:
                raise ExactHTTPSTransportError("required_credential_material_missing", never)
            try:
                secret = bytes(credential).decode("ascii")
            except UnicodeDecodeError as exc:
                raise ExactHTTPSTransportError("credential_framing_invalid", never) from exc
            if "\r" in secret or "\n" in secret:
                raise ExactHTTPSTransportError("credential_framing_invalid", never)
            if profile.authentication_mode == "bearer":
                headers["Authorization"] = "Bearer " + secret
            else:
                headers["X-API-Key"] = secret
        body = bytes(request_material)
        attempted = TransportEvidence(request.binding_digest, True, False, False,
                                      None, None)
        connection: _Connection | None = None
        try:
            connection = self._factory(endpoint.host, endpoint.port, self._timeout,
                                       self._tls_context)
            connection.request(profile.method, endpoint.path_prefix, body, headers)
            response = connection.getresponse()
            status = int(response.status)
            length_value = response.getheader("Content-Length")
            if length_value is not None:
                try:
                    declared_length = int(length_value)
                except ValueError as exc:
                    raise ExactHTTPSTransportError("response_content_length_invalid",
                        TransportEvidence(request.binding_digest, True, False, True, None, status)) from exc
                if declared_length < 0 or declared_length > MAX_RESPONSE_MATERIAL_BYTES:
                    raise ExactHTTPSTransportError("response_material_too_large",
                        TransportEvidence(request.binding_digest, True, False, True, None, status))
            raw = response.read(MAX_RESPONSE_MATERIAL_BYTES + 1)
            if len(raw) > MAX_RESPONSE_MATERIAL_BYTES:
                raise ExactHTTPSTransportError("response_material_too_large",
                    TransportEvidence(request.binding_digest, True, False, True, None, status))
            material = bytearray(raw)
            response_digest = "sha256:" + hashlib.sha256(material).hexdigest()
            evidence = TransportEvidence(request.binding_digest, True,
                200 <= status < 300, True, response_digest, status)
            return MaterialTransportResult(evidence, material)
        except ExactHTTPSTransportError:
            raise
        except Exception as exc:
            raise ExactHTTPSTransportError("https_transport_io_failure", attempted) from exc
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass


__all__ = ["ExactHTTPSExternalModelTransport", "ExactHTTPSTransportError"]
