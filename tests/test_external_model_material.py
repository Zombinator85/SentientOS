from dataclasses import asdict, replace
import inspect

import pytest

from sentientos.codex_task_authority_admission import (
    EXTERNAL_MODEL_INFERENCE_DEFINITION, authority_definition_digest,
)
from sentientos.external_model_custody import CustodyValidationError, canonical_bytes, payload_digest
from sentientos.external_model_execution_custody import (
    ExternalModelInferenceController, MaterialTransportResult,
    MaterialExternalModelTransport, NullExternalModelTransport, TransportEvidence,
)
from sentientos.external_model_material import (
    GovernedRequestMaterialResolver, RequestMaterialBinding, RequestMaterialError,
    UnavailableRequestMaterialSource,
)
from tests.test_external_model_credential_resolution import FakeBackend, governed, SECRET

pytestmark = pytest.mark.no_legacy_skip
REQUEST = b'{"messages":[{"role":"user","content":"synthetic only"}]}'
RESPONSE = b'{"synthetic":"untrusted response"}'


class ExactSource:
    def __init__(self, material=REQUEST):
        self.material = material
        self.reads = []
        self.returned = None

    def read_for_invocation(self, binding: RequestMaterialBinding) -> bytearray:
        self.reads.append(binding)
        self.returned = bytearray(self.material)
        return self.returned


def material_parts(tmp_path, *, enabled=True, source=None, maximum_bytes=1024):
    parts = list(governed(tmp_path, enabled=enabled))
    parts[3] = replace(parts[3], payload_digest=payload_digest(REQUEST))
    # Admission must be rebound after changing the request digest.
    entry, request = parts[0], parts[3]
    parts[8] = parts[6].issue(
        admission_id="material-admission", capability_id="external_model_inference",
        definition_version=1, subsystem_kind="external_model_inference",
        principal_id=request.principal.principal_id,
        principal_kind="deterministic_external_model_inference_controller",
        effects=("bounded_external_model_network_egress",),
        subject_id=f"{request.service_id}:{request.endpoint_id}",
        request_configuration_digest=__import__("sentientos.external_model_custody", fromlist=["digest"]).digest(
            {"request": request.binding_digest, "configuration": entry.configuration_digest}),
        provenance="isolated-material-test-fixture", issued_sequence=4,
        valid_through_sequence=6,
        affirmative_preconditions=EXTERNAL_MODEL_INFERENCE_DEFINITION.approval_requirements,
    )
    source = source or ExactSource()
    resolver = GovernedRequestMaterialResolver(
        catalog=parts[1], registry=parts[2], admission_verifier=parts[7],
        source=source, maximum_bytes=maximum_bytes,
    )
    return parts, source, resolver


def reveal(parts, resolver, *, request=None, admission=None, sequence=5, consumer=bytes):
    request = request or parts[3]
    admission = parts[8] if admission is None else admission
    return resolver.use_for_invocation(
        request=request, admission=admission, current_sequence=sequence,
        admission_evidence_ref=admission.admission_id, consumer=consumer,
    )


def test_exact_material_is_bound_verified_and_cleared(tmp_path):
    parts, source, resolver = material_parts(tmp_path)
    assert reveal(parts, resolver) == REQUEST
    binding = source.reads[0]
    assert (binding.request_id, binding.service_id, binding.endpoint_id, binding.model_id) == (
        "request-a", "service-a", "endpoint-a", "model-a")
    assert binding.expected_payload_digest == payload_digest(REQUEST)
    assert source.returned == bytearray(len(REQUEST))
    assert not any(hasattr(resolver, name) for name in ("resolve", "get_prompt", "fetch_blob", "read_request"))


def test_wrong_unavailable_and_oversized_material_fail_and_clear(tmp_path):
    parts, wrong, resolver = material_parts(tmp_path / "wrong", source=ExactSource(b"wrong"))
    with pytest.raises(RequestMaterialError, match="digest_mismatch"):
        reveal(parts, resolver)
    assert wrong.returned == bytearray(5)
    parts, _, resolver = material_parts(tmp_path / "missing", source=UnavailableRequestMaterialSource())
    with pytest.raises(RequestMaterialError, match="source_unavailable"):
        reveal(parts, resolver)
    parts, large, resolver = material_parts(tmp_path / "large", source=ExactSource(REQUEST), maximum_bytes=4)
    with pytest.raises(RequestMaterialError, match="too_large"):
        reveal(parts, resolver)
    assert large.returned == bytearray(len(REQUEST))


@pytest.mark.parametrize("change", [
    {"request_id": "other"}, {"service_id": "other"}, {"endpoint_id": "other"},
    {"model_id": "other"}, {"credential_ref": "other"},
    {"generation_parameters": (("max_tokens", 9),)},
])
def test_request_metadata_substitution_fails_before_source(tmp_path, change):
    parts, source, resolver = material_parts(tmp_path)
    with pytest.raises(RequestMaterialError):
        reveal(parts, resolver, request=replace(parts[3], **change))
    assert source.reads == []


def test_disabled_expired_revoked_and_admission_substitution_precede_read(tmp_path):
    disabled, source, resolver = material_parts(tmp_path / "disabled", enabled=False)
    with pytest.raises(RequestMaterialError, match="disabled"): reveal(disabled, resolver)
    assert source.reads == []
    parts, source, resolver = material_parts(tmp_path / "admission")
    with pytest.raises(RequestMaterialError, match="expired"): reveal(parts, resolver, sequence=7)
    for field, value in (("principal_id", "other"), ("effects", ("other",)),
                         ("subject_id", "other"), ("request_configuration_digest", "sha256:" + "0" * 64)):
        with pytest.raises(RequestMaterialError):
            reveal(parts, resolver, admission=replace(parts[8], **{field: value}))
    parts[6].revoke(parts[8].admission_id, sequence=5, reason_category="operator_policy_change", provenance="test")
    with pytest.raises(RequestMaterialError, match="revoked"): reveal(parts, resolver)
    assert source.reads == []


class SyntheticMaterialTransport:
    def __init__(self, response=RESPONSE, claimed=None, responded=True):
        self.seen_request = self.seen_credential = None
        self.response = response
        self.claimed = claimed if claimed is not None else payload_digest(response) if response is not None else payload_digest(b"missing")
        self.responded = responded
        self.returned = None

    def invoke_with_material(self, invocation, request_material, credential):
        self.seen_request, self.seen_credential = bytes(request_material), bytes(credential) if credential else None
        self.returned = bytearray(self.response) if self.response is not None else None
        evidence = TransportEvidence(
            invocation.request.binding_digest, True, True, self.responded,
            self.claimed if self.responded else None, 200, synthetic_test_only=True,
        )
        return MaterialTransportResult(evidence, self.returned)


def controller(parts, resolver, transport):
    return ExternalModelInferenceController(
        catalog=parts[1], registry=parts[2], transport=transport, receipts=parts[5],
        admission_verifier=parts[7], credential_resolver=parts[10],
        request_material_resolver=resolver,
    )


def test_material_transport_gets_governed_request_credential_and_untrusted_handoff(tmp_path):
    parts, source, resolver = material_parts(tmp_path)
    transport = SyntheticMaterialTransport()
    handed = []
    receipt = controller(parts, resolver, transport).execute(
        parts[3], credential_handle=parts[4], admission=parts[8], current_sequence=5,
        response_consumer=lambda metadata, material: handed.append((metadata, bytes(material))),
    )
    assert transport.seen_request == REQUEST and transport.seen_credential == SECRET
    assert handed[0][1] == RESPONSE
    assert handed[0][0].epistemic_status == "untrusted_external_data"
    assert handed[0][0].synthetic_test_only
    assert receipt.response_payload_digest == payload_digest(RESPONSE)
    assert receipt.synthetic and not receipt.effect_occurred
    assert transport.returned == bytearray(len(RESPONSE))
    durable = parts[5].path.read_bytes()
    assert REQUEST not in durable and RESPONSE not in durable
    assert payload_digest(RESPONSE).encode() in durable


def test_response_digest_missing_material_contradiction_and_size_fail_closed(tmp_path):
    parts, _, resolver = material_parts(tmp_path / "digest")
    transport = SyntheticMaterialTransport(claimed=payload_digest(b"different"))
    with pytest.raises(RequestMaterialError, match="digest_mismatch"):
        controller(parts, resolver, transport).execute(parts[3], credential_handle=parts[4], admission=parts[8], current_sequence=4)
    assert transport.returned == bytearray(len(RESPONSE))
    parts, _, resolver = material_parts(tmp_path / "missing")
    with pytest.raises(CustodyValidationError, match="response_material_required"):
        controller(parts, resolver, SyntheticMaterialTransport(response=None)).execute(parts[3], credential_handle=parts[4], admission=parts[8], current_sequence=4)
    parts, _, resolver = material_parts(tmp_path / "contradiction")
    with pytest.raises(CustodyValidationError, match="response_material"):
        controller(parts, resolver, SyntheticMaterialTransport(responded=False)).execute(parts[3], credential_handle=parts[4], admission=parts[8], current_sequence=4)
    parts, _, resolver = material_parts(tmp_path / "large")
    transport = SyntheticMaterialTransport(response=b"x" * (4_194_304 + 1))
    with pytest.raises(RequestMaterialError, match="too_large"):
        controller(parts, resolver, transport).execute(parts[3], credential_handle=parts[4], admission=parts[8], current_sequence=4)


def test_null_transport_reads_neither_material_nor_credential(tmp_path):
    source, backend = ExactSource(), FakeBackend(unavailable=True)
    parts, source, resolver = material_parts(tmp_path, source=source)
    parts[9] = backend
    # The resolver installed by governed uses its original test backend; neither may be read.
    with pytest.raises(CustodyValidationError, match="transport_unavailable"):
        controller(parts, resolver, NullExternalModelTransport()).execute(
            parts[3], credential_handle=parts[4], admission=parts[8], current_sequence=4)
    assert source.reads == [] and backend.reads == []
    receipt = parts[5].load()[0]
    assert not receipt.execution_attempted and not receipt.effect_occurred and receipt.synthetic


def test_material_is_non_authority_and_static_surface_is_non_networking(tmp_path):
    parts, source, resolver = material_parts(tmp_path)
    before = parts[6]._ledger.load()
    reveal(parts, resolver)
    assert parts[6]._ledger.load() == before
    assert authority_definition_digest(EXTERNAL_MODEL_INFERENCE_DEFINITION) == "539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c"
    public = canonical_bytes({"binding": asdict(source.reads[0])})
    assert REQUEST not in public
    module = __import__("sentientos.external_model_material", fromlist=["*"])
    production = inspect.getsource(module)
    for forbidden in ("import requests", "urllib.request", "urlopen", "aiohttp", "import httpx", "import socket", "subprocess", "getenv", "environ", "set_password", "delete_password"):
        assert forbidden not in production
    assert not hasattr(module, "issue_grant") and not hasattr(module, "issue_admission")
    assert isinstance(SyntheticMaterialTransport(), MaterialExternalModelTransport)
