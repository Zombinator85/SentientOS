from dataclasses import asdict, replace
import inspect

import pytest

from sentientos.external_model_custody import *
from sentientos.external_model_execution_custody import *

pytestmark = pytest.mark.no_legacy_skip


def fixture(tmp_path, *, enabled=True):
    endpoint = EndpointIdentity("endpoint-a", "https", "models.example.invalid", 443, "/v1/inference")
    service = ExternalModelServiceIdentity("service-a", "Configured synthetic service", "language-model", (endpoint.endpoint_id,))
    credential = CredentialReference("credential-a", service.service_id)
    entry = ConfiguredExternalModelService(service, endpoint, ("model-a", "model-b"), credential.credential_ref, enabled, "operator-reviewed-test-fixture", 1)
    catalog = ExternalModelServiceCatalog({service.service_id: entry})
    registry = CustodyRegistry({endpoint.endpoint_id: endpoint}, {service.service_id: service}, {credential.credential_ref: credential})
    request = InvocationRequestEnvelope("request-a", service.service_id, endpoint.endpoint_id, credential.credential_ref, "model-a", payload_digest(b"not persisted"), (("max_tokens", 8),), "test", PrincipalIdentity("controller-a"), RequiredEffectDescription("bounded_external_model_network_egress", endpoint.endpoint_id, service.service_id), 4)
    handle = OpaqueCredentialUseHandle(credential.credential_ref, service.service_id, available=True)
    admission = ExternalAdmissionEvidence("admission-a", ADMISSION_KIND, request.principal.principal_id, service.service_id, endpoint.endpoint_id, request.binding_digest, entry.configuration_digest, 3, 5, True, True)
    store = InvocationReceiptStore(tmp_path / "receipts.json")
    return entry, catalog, registry, request, handle, admission, store


def test_catalog_persists_and_resolves_exact_configuration(tmp_path):
    entry, catalog, _, request, *_ = fixture(tmp_path)
    path = tmp_path / "catalog.json"
    catalog.save(path)
    loaded = ExternalModelServiceCatalog.load(path)
    assert loaded.resolve(request).configuration_digest == entry.configuration_digest
    assert path.read_bytes() == path.read_bytes()


def test_unknown_disabled_endpoint_model_and_credential_fail_closed(tmp_path):
    _, catalog, _, request, _, _, _ = fixture(tmp_path)
    for changed, reason in (
        (replace(request, service_id="unknown"), "unknown_configured_service"),
        (replace(request, endpoint_id="endpoint-other"), "configured_endpoint_mismatch"),
        (replace(request, model_id="model-other"), "model_outside_configured_scope"),
        (replace(request, credential_ref="credential-other"), "configured_credential_reference_mismatch"),
    ):
        with pytest.raises(CustodyValidationError, match=reason): catalog.resolve(changed)
    _, disabled, _, request2, *_ = fixture(tmp_path, enabled=False)
    with pytest.raises(CustodyValidationError, match="disabled"): disabled.resolve(request2)


def test_credential_handle_is_opaque_and_service_bound(tmp_path):
    _, catalog, registry, request, handle, admission, store = fixture(tmp_path)
    assert set(handle.__dataclass_fields__) == {"credential_ref", "service_id", "usage_class", "provenance", "available"}
    controller = ExternalModelInferenceController(catalog=catalog, registry=registry, transport=NullExternalModelTransport(), receipts=store)
    with pytest.raises(CustodyValidationError, match="credential_handle_service_mismatch"):
        controller.execute(request, credential_handle=replace(handle, service_id="other"), admission=admission, current_sequence=4)


def test_admission_required_and_all_bindings_and_freshness_are_consumed(tmp_path):
    _, catalog, registry, request, handle, admission, store = fixture(tmp_path)
    controller = ExternalModelInferenceController(catalog=catalog, registry=registry, transport=NullExternalModelTransport(), receipts=store)
    with pytest.raises(CustodyValidationError, match="external_admission_required"):
        controller.execute(request, credential_handle=handle, admission=None, current_sequence=4)
    for changed in (
        replace(admission, principal_id="other"), replace(admission, service_id="other"),
        replace(admission, endpoint_id="other"), replace(admission, request_binding_digest=payload_digest(b"other")),
        replace(admission, authority_identity="other"),
    ):
        with pytest.raises(CustodyValidationError, match="admission_request_mismatch"):
            controller.execute(request, credential_handle=handle, admission=changed, current_sequence=4)
    with pytest.raises(CustodyValidationError, match="stale"):
        controller.execute(request, credential_handle=handle, admission=replace(admission, valid_through_sequence=3), current_sequence=4)
    assert not hasattr(controller, "admit") and not hasattr(controller, "issue_admission")


def test_null_transport_records_not_attempted_then_fails_unavailable(tmp_path, monkeypatch):
    _, catalog, registry, request, handle, admission, store = fixture(tmp_path)
    monkeypatch.setattr("os.getenv", lambda *_: pytest.fail("credential environment read"))
    controller = ExternalModelInferenceController(catalog=catalog, registry=registry, transport=NullExternalModelTransport(), receipts=store)
    with pytest.raises(CustodyValidationError, match="transport_unavailable"):
        controller.execute(request, credential_handle=handle, admission=admission, current_sequence=4)
    receipt = store.load()[0]
    assert receipt.request_admitted and not receipt.execution_attempted and not receipt.execution_succeeded
    assert not receipt.effect_occurred and receipt.synthetic


def test_synthetic_transport_proves_result_correlation_and_restart(tmp_path):
    class FakeTransport:
        def invoke(self, invocation):
            return TransportEvidence(invocation.request.binding_digest, True, True, True, payload_digest(b"synthetic response"), 200, synthetic_test_only=True)
    _, catalog, registry, request, handle, admission, store = fixture(tmp_path)
    receipt = ExternalModelInferenceController(catalog=catalog, registry=registry, transport=FakeTransport(), receipts=store).execute(request, credential_handle=handle, admission=admission, current_sequence=4)
    assert receipt.execution_attempted and receipt.execution_succeeded and receipt.synthetic and not receipt.effect_occurred
    reconstructed = InvocationReceiptStore(store.path).load()
    assert reconstructed == (receipt,)
    assert not hasattr(reconstructed[0], "admission")


def test_malformed_transport_and_corrupt_persistence_fail_safely(tmp_path):
    class LyingTransport:
        def invoke(self, invocation): return TransportEvidence(invocation.request.binding_digest, False, True, True, None, 200, True)
    _, catalog, registry, request, handle, admission, store = fixture(tmp_path)
    with pytest.raises(CustodyValidationError, match="malformed_transport"):
        ExternalModelInferenceController(catalog=catalog, registry=registry, transport=LyingTransport(), receipts=store).execute(request, credential_handle=handle, admission=admission, current_sequence=4)
    store.path.write_text("{broken", encoding="utf-8")
    with pytest.raises(CustodyValidationError, match="corrupt_invocation_receipt_store"): store.load()


def test_no_secret_or_transport_implementation_surface(tmp_path):
    entry, catalog, _, request, handle, admission, _ = fixture(tmp_path)
    path = tmp_path / "catalog.json"; catalog.save(path)
    public = canonical_bytes({"entry": entry.payload(), "request": request.to_dict(), "handle": asdict(handle), "admission": asdict(admission)}).decode()
    assert "not persisted" not in public and "secret_value" not in public
    source = inspect.getsource(__import__("sentientos.external_model_execution_custody", fromlist=["*"]))
    for forbidden in ("import requests", "import httpx", "import aiohttp", "import socket", "urlopen", "OPENAI_API_KEY", "HF_API_TOKEN"):
        assert forbidden not in source
