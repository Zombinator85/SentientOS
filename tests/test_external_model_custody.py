from dataclasses import FrozenInstanceError, replace

import pytest

from sentientos.external_model_custody import *

pytestmark = pytest.mark.no_legacy_skip


def fixture():
    endpoint = EndpointIdentity("endpoint-a", "https", "models.example.invalid", 443, "/v1/inference")
    service = ExternalModelServiceIdentity("service-a", "Synthetic service", "language-model", (endpoint.endpoint_id,))
    credential = CredentialReference("credential-a", service.service_id)
    registry = CustodyRegistry({endpoint.endpoint_id: endpoint}, {service.service_id: service}, {credential.credential_ref: credential})
    request = InvocationRequestEnvelope("request-a", service.service_id, endpoint.endpoint_id, credential.credential_ref, "model-a", payload_digest(b"synthetic prompt"), (("max_tokens", 32), ("temperature", 0)), "test-fixture", PrincipalIdentity("custody-controller-a"), RequiredEffectDescription("bounded_external_model_network_egress", endpoint.endpoint_id, service.service_id), 1)
    result = InvocationResultEnvelope(request.request_id, request.binding_digest, service.service_id, endpoint.endpoint_id, None, False, False, False, False, None, None, None, None)
    receipt = InvocationReceipt("receipt-a", request.request_id, request.binding_digest, request.principal.principal_id, service.service_id, endpoint.endpoint_id, credential.credential_ref, None, False, False, False, None, digest(result.to_dict()), 1)
    return registry, request, result, receipt


def test_valid_inert_identity_and_deterministic_bindings():
    registry, request, result, receipt = fixture()
    assert registry.validate_request(request) == request.binding_digest
    assert registry.validate_result(result, request) == digest(result.to_dict())
    assert registry.validate_receipt(receipt, request, result) == receipt.receipt_digest
    assert request.binding_digest == request.binding_digest


def test_endpoint_wildcard_substitution_and_service_mismatch_fail():
    registry, request, _, _ = fixture()
    with pytest.raises(CustodyValidationError, match="host"):
        replace(registry.endpoints["endpoint-a"], host="*.example.invalid").validate()
    other = EndpointIdentity("endpoint-b", "https", "other.example.invalid", 443, "/v1")
    changed = CustodyRegistry({**registry.endpoints, "endpoint-b": other}, registry.services, registry.credentials)
    with pytest.raises(CustodyValidationError, match="mismatch"):
        changed.validate_request(replace(request, endpoint_id="endpoint-b"))


def test_credentials_are_opaque_service_bound_and_never_secret_bearing():
    registry, request, _, _ = fixture()
    assert set(registry.credentials["credential-a"].__dataclass_fields__) == {"credential_ref", "service_id", "usage_class", "available", "use_authorized"}
    mismatched = CustodyRegistry(
        registry.endpoints,
        registry.services,
        {"credential-b": CredentialReference("credential-b", "service-b")},
    )
    with pytest.raises(CustodyValidationError, match="credential_service_mismatch"):
        mismatched.validate_request(replace(request, credential_ref="credential-b"))
    assert "synthetic prompt" not in canonical_bytes(request.to_dict()).decode()


def test_payload_principal_and_effect_are_bound_but_never_authority():
    registry, request, _, _ = fixture()
    changed = replace(request, payload_digest=payload_digest(b"different"))
    assert registry.validate_request(changed) != request.binding_digest
    assert not request.principal.empowered and not request.required_effect.admitted and not request.admitted
    with pytest.raises(CustodyValidationError, match="empowered"):
        registry.validate_request(replace(request, principal=replace(request.principal, empowered=True)))
    with pytest.raises(CustodyValidationError, match="authority"):
        registry.validate_request(replace(request, required_effect=replace(request.required_effect, admitted=True)))


def test_result_correlation_and_admission_execution_are_distinct():
    registry, request, result, _ = fixture()
    with pytest.raises(CustodyValidationError, match="correlation"):
        registry.validate_result(replace(result, request_id="request-b"), request)
    admitted_not_run = replace(result, request_admitted=True, admission_evidence_ref="synthetic-admission-ref")
    assert not admitted_not_run.execution_attempted
    registry.validate_result(admitted_not_run, request)
    with pytest.raises(CustodyValidationError, match="success_without_attempt"):
        registry.validate_result(replace(result, execution_succeeded=True), request)


def test_receipts_are_frozen_linked_synthetic_evidence():
    registry, request, result, receipt = fixture()
    registry.validate_receipt(receipt, request, result)
    with pytest.raises(FrozenInstanceError):
        receipt.effect_occurred = True  # type: ignore[misc]
    with pytest.raises(CustodyValidationError, match="effect_truth"):
        registry.validate_receipt(replace(receipt, synthetic=False, effect_occurred=True), request, result)
    linked = replace(receipt, previous_receipt_digest=receipt.receipt_digest)
    assert registry.validate_receipt(linked, request, result) != receipt.receipt_digest


def test_public_structures_reject_secret_keys():
    registry, request, _, _ = fixture()
    poisoned = replace(request, generation_parameters=(("api_key", "not-a-real-secret"),))
    with pytest.raises(CustodyValidationError, match="secret_material"):
        registry.validate_request(poisoned)


def test_module_has_no_transport_or_environment_consumers():
    import inspect
    import sentientos.external_model_custody as module
    source = inspect.getsource(module)
    for forbidden in ("requests", "httpx", "aiohttp", "socket", "urlopen", "getenv", "environ", "OPENAI_API_KEY"):
        assert forbidden not in source
    assert "codex_task_authority_admission" not in source
