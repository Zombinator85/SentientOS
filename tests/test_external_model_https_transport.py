from dataclasses import replace
import inspect
import os
import ssl

import pytest

from sentientos.codex_task_authority_admission import EXTERNAL_MODEL_INFERENCE_DEFINITION, authority_definition_digest
from sentientos.external_model_custody import CustodyValidationError, payload_digest
from sentientos.external_model_execution_custody import (
    AdmittedInvocation, ExactHTTPSTransportProfile, ExternalModelServiceCatalog,
    ExternalModelInferenceController, GovernedCredentialResolver,
    MaterialExternalModelTransport,
)
from sentientos.external_model_custody import CustodyRegistry, digest
from sentientos.external_model_material import GovernedRequestMaterialResolver
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from tests.test_external_model_credential_resolution import FakeBackend
from tests.test_external_model_material import ExactSource
from sentientos.external_model_https_transport import (
    ExactHTTPSExternalModelTransport, ExactHTTPSTransportError,
)
from tests.test_external_model_execution_custody import fixture

pytestmark = pytest.mark.no_legacy_skip
BODY = b'{"model":"model-a","messages":[]}'
RESPONSE = b'{"result":"untrusted"}'


class FakeResponse:
    def __init__(self, status=200, body=RESPONSE, headers=None):
        self.status, self.body, self.headers = status, body, headers or {}
        self.read_amount = None

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, amount=None):
        self.read_amount = amount
        return self.body[:amount]


class FakeConnection:
    def __init__(self, response=None, failure=None):
        self.response, self.failure = response or FakeResponse(), failure
        self.requests, self.closed = [], False

    def request(self, method, url, body, headers):
        self.requests.append((method, url, body, dict(headers)))
        if self.failure:
            raise self.failure

    def getresponse(self): return self.response
    def close(self): self.closed = True


class Factory:
    def __init__(self, connection): self.connection, self.calls = connection, []
    def __call__(self, host, port, timeout, context):
        self.calls.append((host, port, timeout, context))
        return self.connection


def configured(tmp_path, *, auth="bearer", endpoint=None):
    entry, *_ = fixture(tmp_path)
    if endpoint is not None:
        service = replace(entry.service, endpoint_ids=(endpoint.endpoint_id,))
        entry = replace(entry, endpoint=endpoint, service=service)
    profile = ExactHTTPSTransportProfile(1, "POST", "application/json", auth)
    entry = replace(entry, live_transport=profile,
                    credential_ref=None if auth == "none" else entry.credential_ref)
    entry.validate()
    return entry


def invoke(entry, factory, *, credential=b"test-secret", material=BODY):
    transport = ExactHTTPSExternalModelTransport(entry, connection_factory=factory)
    _, _, _, request, handle, *_ = fixture(pytest.TempPathFactory if False else __import__("pathlib").Path("/tmp"))
    request = replace(request, credential_ref=entry.credential_ref,
                      service_id=entry.service.service_id,
                      endpoint_id=entry.endpoint.endpoint_id,
                      payload_digest=payload_digest(material))
    admitted = AdmittedInvocation(request, entry.configuration_digest, handle, "admission")
    value = None if credential is None else memoryview(credential)
    return transport, transport.invoke_with_material(admitted, memoryview(material), value)


def test_authority_digest_and_construction_create_no_authority(tmp_path):
    entry = configured(tmp_path)
    transport = ExactHTTPSExternalModelTransport(entry, connection_factory=Factory(FakeConnection()))
    assert authority_definition_digest(EXTERNAL_MODEL_INFERENCE_DEFINITION) == "539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c"
    assert not hasattr(transport, "issue_grant") and not hasattr(transport, "issue_admission")
    assert isinstance(transport, MaterialExternalModelTransport)


def test_profile_is_configuration_bound_and_legacy_is_not_live_ready(tmp_path):
    entry = configured(tmp_path)
    changed = replace(entry, live_transport=replace(entry.live_transport, authentication_mode="x-api-key"))
    assert changed.configuration_digest != entry.configuration_digest
    with pytest.raises(CustodyValidationError, match="profile_required"):
        ExactHTTPSExternalModelTransport(replace(entry, live_transport=None))
    path = tmp_path / "catalog.json"
    ExternalModelServiceCatalog({entry.service.service_id: entry}).save(path)
    assert ExternalModelServiceCatalog.load(path).resolve(
        replace(fixture(tmp_path)[3], payload_digest=payload_digest(BODY))).live_transport == entry.live_transport


def test_exact_endpoint_tls_headers_and_body_are_fixed(tmp_path, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "https://attacker.invalid:8443")
    entry = configured(tmp_path)
    connection, factory = FakeConnection(), None
    factory = Factory(connection)
    transport, result = invoke(entry, factory)
    host, port, timeout, context = factory.calls[0]
    method, path, body, headers = connection.requests[0]
    assert (host, port, method, path, body) == (entry.endpoint.host, 443, "POST", "/v1/inference", BODY)
    assert timeout > 0 and context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert headers == {"Host": entry.endpoint.host, "Content-Type": "application/json",
                       "Content-Length": str(len(BODY)), "Authorization": "Bearer test-secret"}
    assert result.response_material == bytearray(RESPONSE)
    assert result.evidence.succeeded and result.evidence.provider_responded
    assert not any(hasattr(transport, name) for name in ("request", "fetch", "open_url", "invoke_host"))


@pytest.mark.parametrize("status", [301, 400, 500])
def test_non_success_responses_are_truthful_and_never_redirected(tmp_path, status):
    response = FakeResponse(status, headers={"Location": "https://different-host.example/escape"})
    connection, factory = FakeConnection(response), None
    factory = Factory(connection)
    _, result = invoke(configured(tmp_path), factory)
    assert result.evidence.attempted and result.evidence.provider_responded
    assert not result.evidence.succeeded and result.evidence.status_code == status
    assert len(connection.requests) == 1 and len(factory.calls) == 1


def test_bounds_content_length_and_connection_failure_evidence(tmp_path):
    oversized = FakeConnection(FakeResponse(headers={"Content-Length": "4194305"}))
    with pytest.raises(ExactHTTPSTransportError, match="too_large") as error:
        invoke(configured(tmp_path / "large"), Factory(oversized))
    assert error.value.evidence.attempted and error.value.evidence.provider_responded
    streaming = FakeConnection(FakeResponse(body=b"x" * 4_194_305))
    with pytest.raises(ExactHTTPSTransportError, match="too_large"):
        invoke(configured(tmp_path / "stream"), Factory(streaming))
    assert streaming.response.read_amount == 4_194_305
    failed = FakeConnection(failure=OSError("private diagnostic"))
    with pytest.raises(ExactHTTPSTransportError, match="https_transport_io_failure") as failure:
        invoke(configured(tmp_path / "failure"), Factory(failed))
    assert failure.value.evidence.attempted and not failure.value.evidence.provider_responded
    assert "private diagnostic" not in str(failure.value)


def test_authentication_modes_and_pre_network_failures_are_sanitized(tmp_path):
    for mode, name, value in (("bearer", "Authorization", "Bearer test-secret"),
                              ("x-api-key", "X-API-Key", "test-secret")):
        connection, factory = FakeConnection(), None
        factory = Factory(connection)
        invoke(configured(tmp_path / mode, auth=mode), factory)
        assert connection.requests[0][3][name] == value
    factory = Factory(FakeConnection())
    with pytest.raises(ExactHTTPSTransportError, match="missing") as missing:
        invoke(configured(tmp_path / "missing"), factory, credential=None)
    assert not missing.value.evidence.attempted and factory.calls == []
    with pytest.raises(ExactHTTPSTransportError, match="unexpected"):
        invoke(configured(tmp_path / "none", auth="none"), Factory(FakeConnection()))
    secret = b"secret\r\nInjected: yes"
    with pytest.raises(ExactHTTPSTransportError, match="framing_invalid") as injection:
        invoke(configured(tmp_path / "inject"), Factory(FakeConnection()), credential=secret)
    assert secret.decode() not in str(injection.value)


def test_unsafe_destinations_and_unverified_tls_fail_before_network(tmp_path):
    from sentientos.external_model_custody import EndpointIdentity
    for host in ("localhost", "api.localhost", "127.0.0.1", "169.254.1.1", "10.0.0.1"):
        endpoint = EndpointIdentity("endpoint-a", "https", host, 443, "/v1/inference")
        with pytest.raises(CustodyValidationError, match="unsafe"):
            ExactHTTPSExternalModelTransport(configured(tmp_path / host.replace(":", "x"), endpoint=endpoint))
    with pytest.raises(CustodyValidationError, match="malformed_endpoint"):
        configured(tmp_path / "ipv6", endpoint=EndpointIdentity("endpoint-a", "https", "::1", 443, "/v1/inference"))
    context = ssl.create_default_context(); context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
    with pytest.raises(CustodyValidationError, match="verified_tls"):
        ExactHTTPSExternalModelTransport(configured(tmp_path / "tls"), tls_context=context)


def test_readiness_is_structural_and_does_not_construct_connection(tmp_path):
    factory = Factory(FakeConnection())
    readiness = ExactHTTPSExternalModelTransport(configured(tmp_path), connection_factory=factory).operational_readiness()
    assert readiness.implementation_available and readiness.exact_endpoint_enforcement
    assert readiness.bounded_request_material and readiness.response_material_custody
    assert factory.calls == []


def test_full_governed_material_and_credential_chain_uses_fake_network(tmp_path):
    base_entry, _, registry, request, handle, _, receipts = fixture(tmp_path)
    entry = replace(base_entry, live_transport=ExactHTTPSTransportProfile(
        1, "POST", "application/json", "bearer"))
    catalog = ExternalModelServiceCatalog({entry.service.service_id: entry})
    request = replace(request, payload_digest=payload_digest(BODY))
    ledger = AdmissionLedger(tmp_path / "admissions.json")
    authority = RuntimeAdmissionAuthority(definitions={"external_model_inference": EXTERNAL_MODEL_INFERENCE_DEFINITION}, ledger=ledger)
    verifier = RuntimeAdmissionVerifier(definitions={"external_model_inference": EXTERNAL_MODEL_INFERENCE_DEFINITION}, ledger=ledger)
    admission = authority.issue(
        admission_id="exact-https-test-admission", capability_id="external_model_inference",
        definition_version=1, subsystem_kind="external_model_inference",
        principal_id=request.principal.principal_id,
        principal_kind="deterministic_external_model_inference_controller",
        effects=("bounded_external_model_network_egress",),
        subject_id=f"{request.service_id}:{request.endpoint_id}",
        request_configuration_digest=digest({"request": request.binding_digest, "configuration": entry.configuration_digest}),
        provenance="isolated-fake-network-test", issued_sequence=3, valid_through_sequence=5,
        affirmative_preconditions=EXTERNAL_MODEL_INFERENCE_DEFINITION.approval_requirements,
    )
    source = ExactSource(BODY)
    material = GovernedRequestMaterialResolver(catalog=catalog, registry=registry,
        admission_verifier=verifier, source=source)
    backend = FakeBackend({("service-a", "credential-a"): b"test-secret"})
    credentials = GovernedCredentialResolver(catalog=catalog, registry=registry,
        admission_verifier=verifier, backend=backend)
    connection, handed = FakeConnection(), []
    transport = ExactHTTPSExternalModelTransport(entry, connection_factory=Factory(connection))
    receipt = ExternalModelInferenceController(
        catalog=catalog, registry=registry, transport=transport, receipts=receipts,
        admission_verifier=verifier, credential_resolver=credentials,
        request_material_resolver=material,
    ).execute(request, credential_handle=handle, admission=admission, current_sequence=4,
              response_consumer=lambda metadata, body: handed.append((metadata, bytes(body))))
    assert connection.requests[0][2] == BODY and handed[0][1] == RESPONSE
    assert handed[0][0].epistemic_status == "untrusted_external_data"
    assert receipt.execution_attempted and receipt.execution_succeeded and receipt.effect_occurred
    durable = receipts.path.read_bytes()
    assert BODY not in durable and RESPONSE not in durable and b"test-secret" not in durable


def test_static_surface_has_only_audited_standard_library_networking():
    import sentientos.external_model_https_transport as module
    source = inspect.getsource(module)
    for forbidden in ("import requests", "import httpx", "import aiohttp", "urlopen(",
                      "os.getenv", "os.environ", "keyring", "subprocess", "CERT_NONE",
                      "check_hostname = False", "set_tunnel", "Location"):
        assert forbidden not in source
    assert "http.client.HTTPSConnection" in source and "ssl.create_default_context" in source
