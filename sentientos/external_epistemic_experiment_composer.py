"""Compose governed external observations for persistent-epistemic experiments.

This module is an adapter, not an authority owner or inference engine.  It
prepares exact request bytes, supplies one-shot material to the existing
admission-bound resolver, binds captured external responses to durable
invocation receipts, and scores answers against precommitted independent keys.
Raw request and response bytes remain transient and are cleared on use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import http.client
import json
import os
from threading import Lock
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit

from .epistemic_revision_qualification import (
    IndependentAnswerKey, RevisionCase, _canonical, _digest, _object,
)
from .external_model_custody import (
    CustodyRegistry, CustodyValidationError, InvocationReceipt,
    InvocationRequestEnvelope, canonical_bytes, payload_digest,
)
from .external_model_execution_custody import (
    ConfiguredExternalModelService, CredentialResolutionError,
    InvocationReceiptStore,
)
from .external_model_material import (
    MAX_REQUEST_MATERIAL_BYTES, MAX_RESPONSE_MATERIAL_BYTES,
    RequestMaterialBinding, RequestMaterialError, UntrustedResponseMetadata,
)
from .persistent_epistemic_state import (
    EpistemicCognitiveProjection, semantic_packets_for_projection,
)

COMPOSER_SCHEMA = "sentientos.external_epistemic_request:v1"
REPORT_SCHEMA = "sentientos.external_epistemic_observation:v1"
MAX_ANSWER_BYTES = 65_536
SUPPORTED_SIDES = frozenset({"before", "after"})


def _sha256(raw: bytes | bytearray | memoryview) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class PreparedExternalRequest:
    """Exact transient request bytes and their preregistered experiment binding."""

    case_id: str
    side: str
    condition: str
    proposition_id: str
    model_id: str
    projection_digest: str
    prompt_digest: str
    payload_digest: str
    generation_parameters_digest: str
    encoder_id: str
    material: bytearray = field(repr=False, compare=False)

    def clear(self) -> None:
        self.material[:] = b"\x00" * len(self.material)


class RequestEncoder(Protocol):
    encoder_id: str

    def encode(self, *, model_id: str, experiment_payload: Mapping[str, Any]) -> bytes: ...


class CanonicalJSONRequestEncoder:
    """Provider-neutral JSON framing; the configured endpoint owns API framing."""

    encoder_id = "sentientos.canonical_json_request_encoder:v1"

    def encode(self, *, model_id: str, experiment_payload: Mapping[str, Any]) -> bytes:
        return bytes(canonical_bytes({"model": model_id, "input": dict(experiment_payload)}))


class OpenAIResponsesRequestEncoder:
    """Model-aware request framing for JSON-only OpenAI Responses inference."""

    encoder_id = "openai_responses_json_request_encoder:v1"
    _PARAMETER_MAP = {
        "max_tokens": "max_output_tokens",
        "max_output_tokens": "max_output_tokens",
        "temperature": "temperature",
        "top_p": "top_p",
        "reasoning_effort": "reasoning",
    }

    def encode(self, *, model_id: str, experiment_payload: Mapping[str, Any]) -> bytes:
        parameters = experiment_payload.get("generation_parameters", {})
        if not isinstance(parameters, Mapping):
            raise ValueError("openai_responses_generation_parameters_invalid")
        request: dict[str, Any] = {
            "model": model_id,
            "input": json.dumps(dict(experiment_payload), sort_keys=True,
                separators=(",", ":"), ensure_ascii=False, allow_nan=False),
            "text": {"format": {"type": "json_object"}},
        }
        for key, value in parameters.items():
            target = self._PARAMETER_MAP.get(key)
            if target is None:
                raise ValueError("openai_responses_generation_parameter_unsupported")
            if target in request:
                raise ValueError("openai_responses_generation_parameter_duplicate")
            request[target] = {"effort": value} if target == "reasoning" else value
        return bytes(canonical_bytes(request))


def prepare_external_request(*, case: RevisionCase, side: str,
        projection: EpistemicCognitiveProjection, model_id: str,
        prompt: str,
        generation_parameters: tuple[tuple[str, int | float | bool | str], ...] = (),
        encoder: RequestEncoder | None = None) -> PreparedExternalRequest:
    """Bind the exact persistent evidence packet and treatment to request bytes.

    Answer keys are intentionally absent. The caller registers the returned
    payload digest in the existing invocation request before any execution.
    """
    commitment = case.commitment()
    if side not in SUPPORTED_SIDES:
        raise ValueError("external_experiment_side_invalid")
    if projection.proposition_ids != (case.proposition_id,):
        raise ValueError("external_experiment_proposition_scope_mismatch")
    if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 256:
        raise ValueError("external_experiment_model_id_invalid")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > MAX_ANSWER_BYTES:
        raise ValueError("external_experiment_prompt_invalid")
    parameter_names = [name for name, _ in generation_parameters]
    if (parameter_names != sorted(parameter_names)
            or len(parameter_names) != len(set(parameter_names))
            or len(parameter_names) > 16):
        raise ValueError("external_experiment_generation_parameters_invalid")
    prompt_digest = _digest({"prompt": prompt})
    expected = case.before_prompt_digest if side == "before" else case.after_prompt_digest
    if prompt_digest != expected:
        raise ValueError("external_experiment_prompt_commitment_mismatch")
    [packet] = semantic_packets_for_projection(projection)
    experiment_payload = {
        "schema": COMPOSER_SCHEMA,
        "case_id": case.case_id,
        "case_commitment": commitment,
        "case_kind": case.kind,
        "side": side,
        "proposition_id": case.proposition_id,
        "prior_epistemic_state": {
            "projection_digest": projection.projection_digest,
            "semantic_packets": [packet],
        },
        "prompt": prompt,
        "generation_parameters": dict(generation_parameters),
        "response_contract": {
            "format": "json_object",
            "instruction": "Return exactly one JSON object with no markdown or surrounding text.",
            "required_fields": ["conclusion", "reason_code", "evidence_ids"],
        },
    }
    selected_encoder = encoder or CanonicalJSONRequestEncoder()
    encoded = selected_encoder.encode(model_id=model_id, experiment_payload=experiment_payload)
    if not isinstance(encoded, bytes) or not encoded or len(encoded) > MAX_REQUEST_MATERIAL_BYTES:
        raise ValueError("external_experiment_request_material_invalid")
    return PreparedExternalRequest(
        case.case_id, side, case.kind, case.proposition_id, model_id,
        projection.projection_digest, prompt_digest, payload_digest(encoded),
        _digest(generation_parameters), selected_encoder.encoder_id, bytearray(encoded),
    )


class OneShotEpistemicRequestMaterialSource:
    """Memory-only exact binding source compatible with governed material use.

    A material binding can be consumed once. Registration is explicit and
    creates no admission; the existing resolver still verifies current runtime
    admission, catalog identity, and payload digest before exposing bytes.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[RequestMaterialBinding, bytearray]] = {}
        self._lock = Lock()

    def register(self, binding: RequestMaterialBinding, material: bytes | bytearray) -> None:
        if not isinstance(material, (bytes, bytearray)) or not material:
            raise RequestMaterialError("request_material_missing")
        if len(material) > MAX_REQUEST_MATERIAL_BYTES:
            raise RequestMaterialError("request_material_too_large")
        if _sha256(material) != binding.expected_payload_digest:
            raise RequestMaterialError("request_material_digest_mismatch")
        owned = bytearray(material)
        with self._lock:
            if binding.request_id in self._entries:
                owned[:] = b"\x00" * len(owned)
                raise RequestMaterialError("request_material_duplicate_registration")
            self._entries[binding.request_id] = (binding, owned)

    def read_for_invocation(self, binding: RequestMaterialBinding) -> bytearray:
        with self._lock:
            entry = self._entries.pop(binding.request_id, None)
            if entry is None:
                raise RequestMaterialError("request_material_source_unavailable")
            expected, material = entry
            if expected != binding:
                material[:] = b"\x00" * len(material)
                raise RequestMaterialError("request_material_binding_mismatch")
            result = bytearray(material)
            material[:] = b"\x00" * len(material)
            return result

    def operational_readiness(self) -> object:
        from .external_model_operational_feasibility import LocalReadiness, seal_local_readiness
        return seal_local_readiness(LocalReadiness(
            "request_material", "one_shot_epistemic_request_material_source:v1", True,
            bounded_request_material=True, structurally_configured=True,
        ))


class FailClosedOSKeyringCredentialBackend:
    """Keep an absent optional runtime extra inside the credential error rail."""

    def read_exact(self, *, service_id: str, credential_ref: str) -> bytearray:
        try:
            import keyring
        except ModuleNotFoundError as exc:
            if exc.name == "keyring":
                raise CredentialResolutionError("credential_backend_unavailable") from None
            raise
        try:
            value = keyring.get_password(f"sentientos.external_model.{service_id}", credential_ref)
        except Exception as exc:
            raise CredentialResolutionError("credential_backend_unavailable") from exc
        if value is None:
            raise CredentialResolutionError("credential_secret_missing")
        if not isinstance(value, str) or not value:
            raise CredentialResolutionError("corrupt_credential_material")
        return bytearray(value, "utf-8")


def register_prepared_request(source: OneShotEpistemicRequestMaterialSource, *,
        prepared: PreparedExternalRequest, binding: RequestMaterialBinding) -> None:
    """Check every request binding before handing exact prepared bytes to source."""
    if (binding.expected_payload_digest != prepared.payload_digest
            or binding.model_id != prepared.model_id):
        raise RequestMaterialError("prepared_request_binding_mismatch")
    try:
        source.register(binding, prepared.material)
    finally:
        prepared.clear()


@dataclass(frozen=True)
class CapturedExternalResponse:
    metadata: UntrustedResponseMetadata
    material: bytearray = field(repr=False, compare=False)

    def clear(self) -> None:
        self.material[:] = b"\x00" * len(self.material)


class ExternalResponseCapture:
    """Single-use response callback for ExternalModelInferenceController."""

    def __init__(self) -> None:
        self._capture: CapturedExternalResponse | None = None

    def __call__(self, metadata: UntrustedResponseMetadata, material: memoryview) -> None:
        if self._capture is not None:
            self._capture.clear()
            self._capture = None
            raise CustodyValidationError("external_response_duplicate_capture")
        if len(material) < 1 or len(material) > MAX_RESPONSE_MATERIAL_BYTES:
            raise CustodyValidationError("external_response_capture_size_invalid")
        self._capture = CapturedExternalResponse(metadata, bytearray(material))

    def take(self) -> CapturedExternalResponse | None:
        capture, self._capture = self._capture, None
        return capture


class ExternalResponseDecoder(Protocol):
    decoder_id: str

    def decode(self, raw: bytes) -> tuple[str, str | None]:
        """Return candidate answer JSON text and provider-reported model id."""


class DirectJSONAnswerDecoder:
    """Decoder for endpoints that return the structured answer as the body."""

    decoder_id = "sentientos.direct_json_answer_decoder:v1"

    def decode(self, raw: bytes) -> tuple[str, str | None]:
        raw.decode("utf-8", errors="strict")
        return raw.decode("utf-8"), None


class OpenAIResponsesAnswerDecoder:
    """Strict extraction for the OpenAI Responses API without tool-result use."""

    decoder_id = "openai_responses_output_text_decoder:v1"

    def decode(self, raw: bytes) -> tuple[str, str | None]:
        try:
            payload = _object(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("external_response_envelope_invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("external_response_envelope_invalid")
        if payload.get("status", "completed") != "completed" or payload.get("incomplete_details") is not None:
            raise ValueError("external_response_incomplete")
        model_id = payload.get("model")
        if model_id is not None and (not isinstance(model_id, str) or not model_id):
            raise ValueError("external_response_model_identity_invalid")
        output = payload.get("output")
        if not isinstance(output, list) or len(output) != 1 or not isinstance(output[0], dict):
            raise ValueError("external_response_output_shape_invalid")
        message = output[0]
        if message.get("type") != "message" or message.get("role") not in {None, "assistant"}:
            raise ValueError("external_response_output_shape_invalid")
        content = message.get("content")
        if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict):
            raise ValueError("external_response_content_shape_invalid")
        segment = content[0]
        if segment.get("type") != "output_text" or not isinstance(segment.get("text"), str):
            raise ValueError("external_response_content_shape_invalid")
        return segment["text"], model_id


def _key_for(case: RevisionCase, side: str) -> IndependentAnswerKey:
    return case.before_key if side == "before" else case.after_key


def _score_external_observation(*, case: RevisionCase, side: str,
        projection: EpistemicCognitiveProjection, prepared: PreparedExternalRequest,
        request: InvocationRequestEnvelope, service: ConfiguredExternalModelService,
        receipt: InvocationReceipt, receipt_store: InvocationReceiptStore,
        registry: CustodyRegistry, current_sequence: int,
        capture: CapturedExternalResponse | None,
        decoder: ExternalResponseDecoder | None = None) -> dict[str, Any]:
    """Verify custody and independently score one captured external answer.

    Invalid receipts raise a sanitized error. Failed/no-response executions are
    retained as insufficient observations, never dropped or converted to passes.
    """
    case_commitment = case.commitment()
    expected_prompt_digest = case.before_prompt_digest if side == "before" else case.after_prompt_digest
    if (side not in SUPPORTED_SIDES or prepared.side != side
            or prepared.condition != case.kind or prepared.case_id != case.case_id
            or prepared.prompt_digest != expected_prompt_digest
            or current_sequence < 0):
        raise ValueError("external_observation_case_binding_mismatch")
    if prepared.model_id != request.model_id or request.payload_digest != prepared.payload_digest:
        raise ValueError("external_observation_request_material_binding_mismatch")
    if _digest(request.generation_parameters) != prepared.generation_parameters_digest:
        raise ValueError("external_observation_generation_binding_mismatch")
    if projection.projection_digest != prepared.projection_digest or projection.proposition_ids != (case.proposition_id,):
        raise ValueError("external_observation_projection_binding_mismatch")
    service.validate()
    if (request.service_id != service.service.service_id
            or request.endpoint_id != service.endpoint.endpoint_id
            or request.model_id not in service.permitted_model_ids):
        raise ValueError("external_observation_service_identity_mismatch")
    registry.validate_request(request)
    stored = receipt_store.load()
    if not any(row.receipt_id == receipt.receipt_id and row == receipt for row in stored):
        raise CustodyValidationError("external_observation_durable_receipt_required")
    if (receipt.request_id != request.request_id
            or receipt.request_binding_digest != request.binding_digest
            or receipt.principal_id != request.principal.principal_id
            or receipt.service_id != request.service_id
            or receipt.endpoint_id != request.endpoint_id
            or receipt.credential_ref != request.credential_ref
            or not receipt.request_admitted
            or not receipt.admission_evidence_ref
            or receipt.sequence < 1 or receipt.sequence > len(stored)
            or receipt.execution_succeeded and not receipt.execution_attempted
            or receipt.execution_succeeded and not receipt.response_payload_digest
            or receipt.effect_occurred != (receipt.execution_attempted and not receipt.synthetic)
            ):
        raise CustodyValidationError("external_observation_receipt_invalid")
    if receipt.response_payload_digest is not None:
        if (len(receipt.response_payload_digest) != 71
                or not receipt.response_payload_digest.startswith("sha256:")
                or any(c not in "0123456789abcdef" for c in receipt.response_payload_digest[7:])):
            raise CustodyValidationError("external_observation_receipt_invalid")
    if capture is not None:
        if (capture.metadata.request_id != request.request_id
                or capture.metadata.request_binding_digest != request.binding_digest
                or capture.metadata.response_payload_digest != receipt.response_payload_digest
                or capture.metadata.synthetic_test_only != receipt.synthetic):
            capture.clear()
            raise CustodyValidationError("external_observation_response_provenance_mismatch")
        if (not capture.material or len(capture.material) > MAX_RESPONSE_MATERIAL_BYTES
                or _sha256(capture.material) != receipt.response_payload_digest):
            capture.clear()
            raise CustodyValidationError("external_observation_response_digest_mismatch")

    [packet] = semantic_packets_for_projection(projection)
    key = _key_for(case, side)
    answer_fields: dict[str, Any] = {
        "answer_shape_valid": None, "answer_correct": None,
        "reason_code_correct": None, "citations_correct": None,
    }
    reported_model_id: str | None = None
    execution_status = (
        "completed" if receipt.execution_succeeded and receipt.response_payload_digest
        else "failed" if receipt.execution_attempted
        else "not_attempted"
    )
    measurement_status = "insufficient"
    score_outcome = "no_response"
    selected_decoder = decoder or DirectJSONAnswerDecoder()
    if capture is not None:
        try:
            if not receipt.execution_succeeded:
                score_outcome = "response_from_failed_inference"
            else:
                if len(capture.material) > MAX_ANSWER_BYTES and isinstance(selected_decoder, DirectJSONAnswerDecoder):
                    raise ValueError("external_answer_size_limit_exceeded")
                answer_text, reported_model_id = selected_decoder.decode(bytes(capture.material))
                answer = _object(answer_text)
                citations = answer.get("evidence_ids")
                shape_valid = (
                    isinstance(answer.get("conclusion"), str)
                    and isinstance(answer.get("reason_code"), str)
                    and isinstance(citations, list) and len(citations) <= 256
                    and all(isinstance(item, str) for item in citations)
                )
                available = {row["binding_id"] for row in packet["active_evidence_bindings"]}
                available.update(row["binding_id"] for row in packet["removed_evidence_history"])
                citation_values = citations if isinstance(citations, list) else []
                answer_fields = {
                    "answer_shape_valid": shape_valid,
                    "answer_correct": shape_valid and answer.get("conclusion") == key.conclusion,
                    "reason_code_correct": shape_valid and answer.get("reason_code") == key.reason_code,
                    "citations_correct": shape_valid and set(key.evidence_ids) <= set(citation_values)
                        and set(citation_values) <= available,
                }
                score_outcome = "scored_synthetic_observation" if receipt.synthetic else "scored"
                measurement_status = "scored"
        except (ValueError, TypeError, UnicodeDecodeError):
            answer_fields = {name: False for name in answer_fields}
            score_outcome = "invalid_or_unparseable_response"
            measurement_status = "scored"
        finally:
            capture.clear()

    provider_model_identity = (
        "unreported" if reported_model_id is None
        else "provider_reported_match" if reported_model_id == request.model_id
        else "provider_reported_mismatch"
    )
    answer_passed = measurement_status == "scored" and all(answer_fields.values())
    if measurement_status == "scored" and provider_model_identity == "provider_reported_mismatch":
        score_outcome = "scored_model_identity_mismatch"
    report = {
        "schema_version": REPORT_SCHEMA,
        "case_id": case.case_id,
        "case_kind": case.kind,
        "case_commitment": case_commitment,
        "side": side,
        "condition": prepared.condition,
        "proposition_id": case.proposition_id,
        "projection_digest": projection.projection_digest,
        "prompt_digest": prepared.prompt_digest,
        "state_digest": packet["state"]["state_digest"],
        "proposition_digest": _digest(packet["proposition"]),
        "evidence_set_digest": packet["state"]["evidence_set_digest"],
        "update_event_history_digest": _digest(packet["update_event_history"]),
        "update_event_history_count": len(packet["update_event_history"]),
        "prior_update_event_history_digest": _digest(packet["update_event_history"][:-1]),
        "last_update_event": dict(packet["last_update_event"]),
        "state_stance_correct": packet["state"]["stance"] == key.stance,
        "request_id": request.request_id,
        "request_binding_digest": request.binding_digest,
        "request_payload_digest": request.payload_digest,
        "service_id": service.service.service_id,
        "endpoint_id": service.endpoint.endpoint_id,
        "service_configuration_digest": service.configuration_digest,
        "requested_model_id": request.model_id,
        "provider_reported_model_id": reported_model_id,
        "model_artifact_identity": "unknown_provider_managed",
        "provider_model_identity_status": provider_model_identity,
        "generation_parameters_digest": _digest(request.generation_parameters),
        "measurement_sequence": current_sequence,
        "encoder_id": prepared.encoder_id,
        "decoder_id": selected_decoder.decoder_id,
        "receipt_id": receipt.receipt_id,
        "receipt_digest": receipt.receipt_digest,
        "result_digest": receipt.result_digest,
        "result_digest_verification": "opaque_controller_validated_not_recomputed",
        "receipt_verification_scope": "durable_chain_and_exact_request_binding",
        "response_payload_digest": receipt.response_payload_digest,
        "execution_attempted": receipt.execution_attempted,
        "execution_succeeded": receipt.execution_succeeded,
        "synthetic_test_only": receipt.synthetic,
        "effect_occurred": receipt.effect_occurred,
        "execution_status": execution_status,
        "score_outcome": score_outcome,
        "measurement_status": measurement_status,
        "answer_passed": answer_passed,
        **answer_fields,
        "real_model_qualification_established": False,
        "causal_claim_made": False,
        "oracle_independence_verified": False,
        "preregistration_timing_verified": False,
        "authority": False,
        "source_mutation_performed": False,
    }
    report["report_digest"] = _digest(report)
    return report


def score_external_observation(*, case: RevisionCase, side: str,
        projection: EpistemicCognitiveProjection, prepared: PreparedExternalRequest,
        request: InvocationRequestEnvelope, service: ConfiguredExternalModelService,
        receipt: InvocationReceipt, receipt_store: InvocationReceiptStore,
        registry: CustodyRegistry, current_sequence: int,
        capture: CapturedExternalResponse | None,
        decoder: ExternalResponseDecoder | None = None) -> dict[str, Any]:
    """Always clear a captured external response, including all failure paths."""
    try:
        return _score_external_observation(case=case, side=side,
            projection=projection, prepared=prepared, request=request,
            service=service, receipt=receipt, receipt_store=receipt_store,
            registry=registry, current_sequence=current_sequence,
            capture=capture, decoder=decoder)
    finally:
        if capture is not None:
            capture.clear()


def compare_external_pair(*, case: RevisionCase, before: Mapping[str, Any],
        after: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize paired outcomes without elevating one answer to persistent truth."""
    commitment = case.commitment()
    mismatches: list[str] = []
    for field in ("case_commitment", "proposition_id", "service_id", "endpoint_id",
                  "service_configuration_digest",
                  "generation_parameters_digest", "encoder_id", "decoder_id"):
        if before.get(field) != after.get(field):
            mismatches.append(field)
    if before.get("side") != "before" or after.get("side") != "after":
        mismatches.append("sample_side")
    if (before.get("prompt_digest") != case.before_prompt_digest
            or after.get("prompt_digest") != case.after_prompt_digest):
        mismatches.append("prompt_commitment")
    if case.kind != "model_replacement" and before.get("requested_model_id") != after.get("requested_model_id"):
        mismatches.append("requested_model_id")
    for sample in (before, after):
        if sample.get("provider_model_identity_status") != "provider_reported_match":
            mismatches.append("provider_reported_model_identity")
    preserve = case.kind in {"unsupported_pressure", "retained_correction", "model_replacement"}
    if before.get("proposition_digest") != after.get("proposition_digest"):
        mismatches.append("proposition_meaning")
    event = after.get("last_update_event")
    delta_valid = (
        isinstance(event, Mapping)
        and after.get("update_event_history_count") == before.get("update_event_history_count", 0) + 1
        and after.get("prior_update_event_history_digest") == before.get("update_event_history_digest")
        and event.get("prior_state_digest") == before.get("state_digest")
    )
    allowed = {
        "contrary_evidence": {"contradiction_arrival", "new_evidence"},
        "inference_correction": {"update_rule_correction", "dependency_correction", "operator_error_correction"},
        "outdated_evidence": {"source_reliability_revision", "evidence_withdrawal", "new_evidence"},
    }
    same_state = before.get("state_digest") == after.get("state_digest")
    transition_valid = (same_state and before.get("update_event_history_digest") == after.get("update_event_history_digest")) if preserve else (
        not same_state and delta_valid and isinstance(event, Mapping)
        and event.get("reason") in allowed.get(case.kind, set())
    )
    if case.kind == "inference_correction":
        transition_valid = transition_valid and before.get("evidence_set_digest") == after.get("evidence_set_digest")
    if case.kind in {"contrary_evidence", "outdated_evidence"}:
        transition_valid = transition_valid and before.get("evidence_set_digest") != after.get("evidence_set_digest")
    if case.kind == "model_replacement":
        # A provider-managed deployment cannot prove its weights unchanged or
        # changed, so this path intentionally cannot qualify replacement.
        mismatches.append("provider_model_artifact_identity_unavailable")
    insufficient = bool(mismatches) or any(
        sample.get("measurement_status") != "scored" or sample.get("synthetic_test_only")
        for sample in (before, after)
    )
    passed = (transition_valid and bool(before.get("state_stance_correct"))
        and bool(after.get("state_stance_correct")) and bool(before.get("answer_passed"))
        and bool(after.get("answer_passed")))
    report = {
        "schema_version": "sentientos.external_epistemic_pair:v1",
        "case_id": case.case_id,
        "case_kind": case.kind,
        "case_commitment": commitment,
        "status": "insufficient" if insufficient else "case_passed" if passed else "case_failed",
        "before": dict(before),
        "after": dict(after),
        "state_transition_appropriate": transition_valid,
        "control_mismatches": mismatches,
        "real_model_qualification_established": False,
        "causal_claim_made": False,
        "oracle_independence_verified": False,
        "preregistration_timing_verified": False,
        "authority": False,
        "source_mutation_performed": False,
    }
    report["report_digest"] = _digest(report)
    return report


def managed_https_proxy_connection_factory(proxy_url: str | None = None) -> Callable[..., Any]:
    """Return a verified-TLS HTTPS CONNECT factory for the managed HTTP proxy.

    The proxy carries only CONNECT metadata. Provider authentication remains in
    the tunneled TLS request. Proxy credentials and HTTPS-to-proxy TLS are
    rejected because this transport has no governed representation for them.
    With no configured proxy, the existing direct exact-endpoint transport is
    retained for ordinary non-proxied deployments.
    """
    configured = proxy_url or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not configured:
        def direct(host: str, port: int, timeout: float, context: Any) -> Any:
            return http.client.HTTPSConnection(host=host, port=port, timeout=timeout, context=context)
        return direct
    try:
        parsed = urlsplit(configured)
        proxy_port = parsed.port or (80 if parsed.scheme == "http" else None)
    except ValueError as exc:
        raise CustodyValidationError("managed_https_proxy_url_invalid") from exc
    if (parsed.scheme != "http" or not parsed.hostname
            or any(char.isspace() or char in "/?#@\\" for char in parsed.hostname)
            or proxy_port is None or not 1 <= proxy_port <= 65535
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise CustodyValidationError("managed_https_proxy_profile_unsupported")
    proxy_host = parsed.hostname

    def through_managed_proxy(host: str, port: int, timeout: float,
                              context: Any) -> Any:
        connection = http.client.HTTPSConnection(
            host=proxy_host, port=proxy_port, timeout=timeout, context=context,
        )
        connection.set_tunnel(host, port)
        return connection

    return through_managed_proxy


__all__ = [
    "CanonicalJSONRequestEncoder", "CapturedExternalResponse",
    "DirectJSONAnswerDecoder", "ExternalResponseCapture",
    "FailClosedOSKeyringCredentialBackend", "OneShotEpistemicRequestMaterialSource",
    "OpenAIResponsesAnswerDecoder",
    "OpenAIResponsesRequestEncoder",
    "PreparedExternalRequest", "compare_external_pair",
    "managed_https_proxy_connection_factory", "prepare_external_request",
    "register_prepared_request", "score_external_observation",
]
