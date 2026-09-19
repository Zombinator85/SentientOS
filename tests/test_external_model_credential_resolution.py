from dataclasses import asdict, replace
import inspect
import pytest
from sentientos.codex_task_authority_admission import EXTERNAL_MODEL_INFERENCE_DEFINITION, authority_definition_digest
from sentientos.external_model_custody import canonical_bytes, digest
from sentientos.external_model_execution_custody import *
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from tests.test_external_model_execution_custody import fixture
pytestmark = pytest.mark.no_legacy_skip
CAPABILITY = "external_model_inference"
SECRET = b"test-secret-that-must-never-escape"

class FakeBackend:
    def __init__(self, values=None, unavailable=False): self.values=values or {}; self.unavailable=unavailable; self.reads=[]; self.returned=None
    def read_exact(self, *, service_id, credential_ref):
        self.reads.append((service_id, credential_ref))
        if self.unavailable: raise RuntimeError("private backend diagnostic")
        value=self.values.get((service_id, credential_ref))
        if value is None: raise CredentialResolutionError("credential_secret_missing")
        self.returned=bytearray(value); return self.returned

def governed(tmp_path, *, enabled=True, backend=None, capability=CAPABILITY):
    entry,catalog,registry,request,handle,_,receipts=fixture(tmp_path,enabled=enabled)
    ledger=AdmissionLedger(tmp_path/"authority/admissions.json")
    authority=RuntimeAdmissionAuthority(definitions={CAPABILITY:EXTERNAL_MODEL_INFERENCE_DEFINITION},ledger=ledger)
    verifier=RuntimeAdmissionVerifier(definitions={CAPABILITY:EXTERNAL_MODEL_INFERENCE_DEFINITION},ledger=ledger)
    admission=authority.issue(admission_id="test-admission",capability_id=CAPABILITY,definition_version=1,subsystem_kind=CAPABILITY,principal_id=request.principal.principal_id,principal_kind="deterministic_external_model_inference_controller",effects=("bounded_external_model_network_egress",),subject_id=f"{request.service_id}:{request.endpoint_id}",request_configuration_digest=digest({"request":request.binding_digest,"configuration":entry.configuration_digest}),provenance="operator-test-fixture",issued_sequence=3,valid_through_sequence=5,affirmative_preconditions=EXTERNAL_MODEL_INFERENCE_DEFINITION.approval_requirements)
    backend=backend or FakeBackend({("service-a","credential-a"):SECRET})
    resolver=GovernedCredentialResolver(catalog=catalog,registry=registry,admission_verifier=verifier,backend=backend,admission_capability_id=capability)
    return entry,catalog,registry,request,handle,receipts,authority,verifier,admission,backend,resolver

def reveal(parts, request=None, handle=None, admission="default", sequence=4):
    req=request or parts[3]; h=handle or parts[4]; adm=parts[8] if admission=="default" else admission
    return parts[10].use_for_invocation(request=req,credential_handle=h,admission=adm,current_sequence=sequence,consumer=bytes)

def test_exact_admitted_invocation_resolves_only_bound_secret(tmp_path):
    p=governed(tmp_path); assert reveal(p)==SECRET; assert p[9].reads==[("service-a","credential-a")]
    assert not any(hasattr(p[10],x) for x in ("list","enumerate","create","update","delete","export","rotate"))

def test_missing_expired_revoked_and_tampered_admissions_fail_before_backend(tmp_path):
    p=governed(tmp_path)
    with pytest.raises(CredentialResolutionError,match="admission_required"): reveal(p,admission=None)
    with pytest.raises(CredentialResolutionError,match="expired"): reveal(p,sequence=6)
    for a in (replace(p[8],principal_id="other"),replace(p[8],capability_id="other"),replace(p[8],effects=("other",)),replace(p[8],subject_id="other"),replace(p[8],request_configuration_digest="sha256:"+"0"*64)):
        with pytest.raises(CredentialResolutionError): reveal(p,admission=a)
    p[6].revoke(p[8].admission_id,sequence=4,reason_category="operator_policy_change",provenance="test")
    with pytest.raises(CredentialResolutionError,match="revoked"): reveal(p)
    assert p[9].reads==[]

@pytest.mark.parametrize("change",[{"service_id":"other"},{"endpoint_id":"other"},{"model_id":"other"},{"credential_ref":"other"},{"payload_digest":"sha256:"+"0"*64}])
def test_service_endpoint_model_request_and_credential_substitution_fail(tmp_path,change):
    p=governed(tmp_path)
    with pytest.raises(CredentialResolutionError): reveal(p,request=replace(p[3],**change))
    assert p[9].reads==[]

def test_disabled_handle_missing_corrupt_and_backend_unavailable_fail_closed(tmp_path):
    p=governed(tmp_path)
    with pytest.raises(CredentialResolutionError,match="binding_mismatch"): reveal(p,handle=replace(p[4],credential_ref="other"))
    disabled=governed(tmp_path/"disabled",enabled=False)
    with pytest.raises(CredentialResolutionError,match="disabled"): reveal(disabled)
    missing=governed(tmp_path/"missing",backend=FakeBackend())
    with pytest.raises(CredentialResolutionError,match="missing"): reveal(missing)
    unavailable=governed(tmp_path/"unavailable",backend=FakeBackend(unavailable=True))
    with pytest.raises(CredentialResolutionError,match="backend_unavailable") as error: reveal(unavailable)
    assert "private backend" not in str(error.value)
    class Corrupt:
        def read_exact(self,**_): return "not mutable secret"
    corrupt=governed(tmp_path/"corrupt",backend=Corrupt())
    with pytest.raises(CredentialResolutionError,match="corrupt"): reveal(corrupt)

def test_secret_is_short_lived_redacted_and_absent_from_custody(tmp_path,caplog):
    p=governed(tmp_path); assert reveal(p)==SECRET; assert p[9].returned==bytearray(len(SECRET))
    public=canonical_bytes({"entry":p[0].payload(),"request":p[3].to_dict(),"handle":asdict(p[4]),"admission":asdict(p[8])})
    assert SECRET not in public and SECRET.decode() not in repr(p[10])+caplog.text; assert not p[5].path.exists()

def test_controller_resolves_only_for_credentialed_transport_and_null_stays_null(tmp_path):
    class CredentialedFake:
        seen=None
        def invoke_with_credential(self,invocation,credential): self.seen=bytes(credential); return TransportEvidence(invocation.request.binding_digest,False,False,False,None,None,True)
    p=governed(tmp_path); transport=CredentialedFake()
    ExternalModelInferenceController(catalog=p[1],registry=p[2],transport=transport,receipts=p[5],admission_verifier=p[7],credential_resolver=p[10]).execute(p[3],credential_handle=p[4],admission=p[8],current_sequence=4)
    assert transport.seen==SECRET
    backend=FakeBackend(unavailable=True); resolver=GovernedCredentialResolver(catalog=p[1],registry=p[2],admission_verifier=p[7],backend=backend)
    null=ExternalModelInferenceController(catalog=p[1],registry=p[2],transport=NullExternalModelTransport(),receipts=p[5],admission_verifier=p[7],credential_resolver=resolver)
    with pytest.raises(CustodyValidationError,match="transport_unavailable"): null.execute(p[3],credential_handle=p[4],admission=p[8],current_sequence=4)
    assert backend.reads==[]

def test_production_backend_definition_and_transport_surface_remain_narrow():
    assert authority_definition_digest(EXTERNAL_MODEL_INFERENCE_DEFINITION)=="539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c"
    assert [n for n,v in inspect.getmembers(OSKeyringCredentialBackend,inspect.isfunction) if not n.startswith("_")]==["read_exact"]
    source=inspect.getsource(__import__("sentientos.external_model_execution_custody",fromlist=["*"]))
    for forbidden in ("import requests","import urllib","import aiohttp","import httpx","import socket","subprocess","set_password","delete_password"): assert forbidden not in source
    assert not hasattr(ExternalModelInferenceController,"issue_admission") and not hasattr(ExternalModelInferenceController,"issue_grant")
