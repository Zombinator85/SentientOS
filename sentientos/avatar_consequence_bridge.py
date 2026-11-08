"""Opt-in bridge between consented screen measurement and consequence evidence.

This module only transports a one-shot request to the Windows capture owner and
returns its typed, signed measurement to a dedicated authenticated observer
runtime. It grants no action authority and does not claim causal attribution.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from .gaming_companion_bridge import (
    AVATAR_CONSEQUENCE_REQUEST_FIELDS,
    AVATAR_CONSEQUENCE_REQUEST_SCHEMA,
    CONSEQUENCE_OBSERVATION_SCHEMA_V2,
    VerifiedBridgeMessage,
    encode_message,
)
from .embodied_consequence import (
    AuthenticatedBridgeIndependentObserver,
    EmbodiedActionExpectation,
    IndependentConsequenceObservation,
    AvatarRendererReport,
    verify_expectation,
    verify_renderer_handoff,
    verify_renderer_report,
)


class _MessageClient(Protocol):
    def send(self, encoded: bytes) -> VerifiedBridgeMessage: ...


class AvatarConsequenceBridgeError(ValueError):
    """Invalid request, capture result, or consequence delivery."""


def _request_payload(*, expectation: EmbodiedActionExpectation,
                     handoff: Mapping[str, Any],
                     report: AvatarRendererReport | None,
                     capture_request_id: str) -> dict[str, Any]:
    verify_expectation(expectation)
    verify_renderer_handoff(handoff)
    if report is not None:
        verify_renderer_report(report)
    if (not isinstance(capture_request_id, str)
            or len(capture_request_id) != 32
            or any(char not in "0123456789abcdef" for char in capture_request_id)):
        raise AvatarConsequenceBridgeError("avatar_consequence_request_id_invalid")
    if (expectation.handoff_id != handoff.get("handoff_id")
            or expectation.handoff_digest != handoff.get("handoff_digest")
            or expectation.correlation_id != handoff.get("correlation_id")
            or expectation.body_generation != handoff.get("body_generation")
            or expectation.body_manifest_digest != handoff.get("body_manifest_digest")
            or (report is not None and (
                report.handoff_id != handoff.get("handoff_id")
                or report.handoff_digest != handoff.get("handoff_digest")
                or report.correlation_id != expectation.correlation_id
                or report.body_generation != expectation.body_generation))):
        raise AvatarConsequenceBridgeError("avatar_consequence_request_lineage_invalid")
    return {
        "schema_version": AVATAR_CONSEQUENCE_REQUEST_SCHEMA,
        "capture_request_id": capture_request_id,
        "expectation_id": expectation.expectation_id,
        "expectation_digest": expectation.expectation_digest,
        "handoff_id": handoff["handoff_id"],
        "handoff_digest": handoff["handoff_digest"],
        "renderer_report_id": report.report_id if report is not None else None,
        "renderer_report_digest": report.report_digest if report is not None else None,
        "correlation_id": expectation.correlation_id,
        "body_generation": expectation.body_generation,
    }


class AvatarConsequenceMeasurementRequestSender:
    """Send a single expectation-bound measurement request over the mTLS edge."""

    def __init__(self, *, client: _MessageClient, source_id: str, session_id: str,
                 generation_id: str, source_key: bytes) -> None:
        if not callable(getattr(client, "send", None)):
            raise AvatarConsequenceBridgeError("avatar_consequence_client_required")
        if not isinstance(source_key, bytes) or len(source_key) < 32:
            raise AvatarConsequenceBridgeError("bridge_key_too_short")
        self._client = client
        self._source_id = source_id
        self._session_id = session_id
        self._generation_id = generation_id
        self._source_key = bytes(source_key)
        self._sequence = 0
        self._lock = threading.Lock()

    def __call__(self, *, expectation: EmbodiedActionExpectation,
                 handoff: Mapping[str, Any],
                 report: AvatarRendererReport | None = None,
                 capture_request_id: str | None = None) -> VerifiedBridgeMessage:
        payload = _request_payload(
            expectation=expectation, handoff=handoff, report=report,
            capture_request_id=capture_request_id or uuid4().hex)
        with self._lock:
            sequence = self._sequence + 1
            encoded = encode_message(kind="avatar_consequence_request",
                source_id=self._source_id, session_id=self._session_id,
                generation_id=self._generation_id, sequence=sequence,
                payload=payload, key=self._source_key)
            self._sequence = sequence
            return self._client.send(encoded)


class AvatarConsequenceCaptureRequestHandler:
    """Handle one authenticated request on Windows and publish its typed result."""

    def __init__(self, *, observe: Callable[[], Mapping[str, Any]],
                 client: _MessageClient, request_source_id: str,
                 request_generation_id: str, observer_id: str,
                 observer_generation_id: str, session_id: str,
                 observer_source_key: bytes) -> None:
        if not callable(observe) or not callable(getattr(client, "send", None)):
            raise AvatarConsequenceBridgeError("avatar_consequence_capture_owner_required")
        if not isinstance(observer_source_key, bytes) or len(observer_source_key) < 32:
            raise AvatarConsequenceBridgeError("bridge_key_too_short")
        self._observe = observe
        self._client = client
        self._request_source_id = request_source_id
        self._request_generation_id = request_generation_id
        self._observer_id = observer_id
        self._observer_generation_id = observer_generation_id
        self._session_id = session_id
        self._key = bytes(observer_source_key)
        self._sequence = 0
        self._lock = threading.Lock()

    def __call__(self, message: VerifiedBridgeMessage) -> bool:
        if (not isinstance(message, VerifiedBridgeMessage)
                or message.kind != "avatar_consequence_request"
                or message.source_id != self._request_source_id
                or message.generation_id != self._request_generation_id
                or message.admission is not None
                or set(message.payload) != AVATAR_CONSEQUENCE_REQUEST_FIELDS
                or message.payload.get("schema_version") != AVATAR_CONSEQUENCE_REQUEST_SCHEMA):
            raise AvatarConsequenceBridgeError("avatar_consequence_request_binding_invalid")
        measurement = self._observe()
        if not isinstance(measurement, Mapping):
            raise AvatarConsequenceBridgeError("avatar_consequence_measurement_invalid")
        observed = measurement.get("observed")
        provenance = {
            "schema_version": "sentientos.screen_capture_provenance:v1",
            "capture_digest": measurement.get("capture_digest"),
            "process_name_digest": measurement.get("process_name_digest"),
            "consent_id_digest": measurement.get("consent_id_digest"),
            "capture_scope": measurement.get("capture_scope"),
            "raw_frame_retained": measurement.get("raw_frame_retained"),
        }
        if (not isinstance(observed, Mapping)
                or set(observed) != {"avatar_visible", "avatar_motion"}
                or observed.get("avatar_visible") not in (True, False, None)
                or observed.get("avatar_motion") not in {"idle", "wave", "nod", "uncertain"}
                or (observed.get("avatar_visible") is not True
                    and observed.get("avatar_motion") != "uncertain")
                or measurement.get("confidence") != "unknown"
                or measurement.get("quality") not in {"partial", "unknown"}
                or measurement.get("raw_frame_retained") is not False
                or not isinstance(measurement.get("observed_at"), str)):
            raise AvatarConsequenceBridgeError("avatar_consequence_measurement_contract_invalid")
        payload = {
            "schema_version": CONSEQUENCE_OBSERVATION_SCHEMA_V2,
            "capture_request_id": message.payload["capture_request_id"],
            "expectation_id": message.payload["expectation_id"],
            "expectation_digest": message.payload["expectation_digest"],
            "handoff_id": message.payload["handoff_id"],
            "handoff_digest": message.payload["handoff_digest"],
            "renderer_report_id": message.payload["renderer_report_id"],
            "renderer_report_digest": message.payload["renderer_report_digest"],
            "correlation_id": message.payload["correlation_id"],
            "body_generation": message.payload["body_generation"],
            "observed": dict(observed),
            "observed_at": measurement["observed_at"],
            "confidence": "unknown",
            "quality": measurement["quality"],
            "capture_provenance": provenance,
        }
        with self._lock:
            sequence = self._sequence + 1
            encoded = encode_message(kind="consequence", source_id=self._observer_id,
                session_id=self._session_id, generation_id=self._observer_generation_id,
                sequence=sequence, payload=payload, key=self._key)
            self._sequence = sequence
            self._client.send(encoded)
        return True


class RemoteAvatarConsequenceObserver:
    """Compose one explicit request with the existing authenticated observer."""

    def __init__(self, *, request_sender: AvatarConsequenceMeasurementRequestSender,
                 observer: AuthenticatedBridgeIndependentObserver) -> None:
        if not isinstance(request_sender, AvatarConsequenceMeasurementRequestSender):
            raise AvatarConsequenceBridgeError("avatar_consequence_request_sender_required")
        if not isinstance(observer, AuthenticatedBridgeIndependentObserver):
            raise AvatarConsequenceBridgeError("authenticated_observer_owner_required")
        self._sender = request_sender
        self._observer = observer
        self._lock = threading.Lock()

    def observe(self, *, expectation: EmbodiedActionExpectation,
                handoff: Mapping[str, Any],
                report: AvatarRendererReport | None = None
                ) -> IndependentConsequenceObservation:
        # Keep the dedicated receive stream one-request-at-a-time so concurrent
        # callers cannot consume each other’s expectation-bound measurements.
        with self._lock:
            capture_request_id = uuid4().hex
            self._sender(expectation=expectation, handoff=handoff, report=report,
                         capture_request_id=capture_request_id)
            return self._observer.observe(
                expectation=expectation, handoff=handoff, report=report,
                capture_request_id=capture_request_id)
