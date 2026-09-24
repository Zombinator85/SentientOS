from __future__ import annotations
import json
from types import SimpleNamespace
import pytest
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_runtime_provisioning import semantic_digest
pytestmark = pytest.mark.no_legacy_skip

from sentientos.resident_cognitive_model_serving import (ACTION, CONFIG_SCHEMA, ResidentCognitiveModelServingController, ResidentCognitiveModelServingError, load_config)

class Kernel:
    def __init__(self, outcome=AdmissionOutcome.ALLOW): self.outcome, self.requests = outcome, []
    def admit(self, request):
        self.requests.append(request)
        return SimpleNamespace(outcome=self.outcome, authority_class=request.authority_class, actor=request.actor, action_kind=request.action_kind, target_subsystem=request.target_subsystem, correlation_id=request.metadata["correlation_id"], admission_decision_ref="resident-serving-admission")
class Model:
    def __init__(self, identity): self.active_identity, self.closed = identity, False
    def close(self): self.closed=True

def evidence(generation=1):
    state={"installation_identity":"install-1","generation":generation,"model_id":"model-1","artifact_id":"artifact-1","artifact_path":"/models/exact.gguf","artifact_sha256":"a"*64,"artifact_size_bytes":42,"route_id":"route-1","runtime_id":"runtime-1","interpreter_path":"/runtime/python","load_configuration":{"n_ctx":1024,"n_gpu_layers":0},"authority_map_digest":"authority-1","commissioning_receipt_id":"commissioning-1","commissioning_receipt_semantic_digest":"commissioning-digest"}; state["state_semantic_digest"]=semantic_digest(state)
    return {"active_state":state,"activation_receipt":{"receipt_id":"activation-1","receipt_semantic_digest":"activation-digest","resulting_state_digest":state["state_semantic_digest"]},"catalog_proof":{"proof_semantic_digest":"proof-digest"}}
def identity(**changes):
    values=dict(engine="llama_cpp",resolved_artifact_path="/models/exact.gguf",semantic_artifact_identity="sha256:"+"a"*64,model_content_sha256="a"*64,artifact_size_bytes=42,sidecar_metadata_digest=None,configuration_digest="config-1",candidate_index=0,posture="production",fallback=False); values.update(changes); return ActiveModelIdentity(**values)
def make(monkeypatch,tmp_path, sequence, outcome=AdmissionOutcome.ALLOW):
    handle=InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("install-1"),create=True); values=iter(sequence); monkeypatch.setattr("sentientos.resident_cognitive_model_serving.verify_current_activation",lambda *a,**k:next(values)); model=Model(identity()); kernel=Kernel(outcome); ctl=ResidentCognitiveModelServingController(handle,kernel,model_factory=lambda *_:model,config_digest="c"*64); monkeypatch.setattr(ctl,"_commissioning_identity",lambda _:identity().to_dict()); return ctl,handle,model,kernel

def test_exact_current_activation_establishes_separate_zero_inference_receipt(monkeypatch,tmp_path):
    current=evidence(); ctl,handle,model,kernel=make(monkeypatch,tmp_path,[current,current,current]); session=ctl.establish(operation_id="resident-operation-1",expected_activation_state_digest=current["active_state"]["state_semantic_digest"])
    receipt=json.loads(handle.read_regular(handle.fixed_object("local-model/resident-cognitive-serving/receipts/"+handle.list_regular_names(handle.fixed_object("local-model/resident-cognitive-serving/receipts"))[0])))
    assert kernel.requests[0].action_kind==ACTION and kernel.requests[0].authority_class is AuthorityClass.MODEL_SERVING
    assert receipt["resident_serving_bound"] is True and receipt["inference_performed"] is False
    assert receipt["canonical_activation_mutated"] is False and receipt["production_chat_serving_mutated"] is False and receipt["cognitive_model_transition_performed"] is False
    assert session.binding["serving_config_digest"]=="c"*64 and not model.closed

def test_activation_change_invalidates_without_automatic_rebind(monkeypatch,tmp_path):
    one,two=evidence(1),evidence(2); ctl,handle,model,kernel=make(monkeypatch,tmp_path,[one,one,two]); ctl.establish(operation_id="resident-operation-1"); assert ctl.current_session() is None and model.closed; assert len(kernel.requests)==1
    assert handle.list_regular_names(handle.fixed_object("local-model/resident-cognitive-serving/invalidations"))

def test_denial_prevents_construction(monkeypatch,tmp_path):
    current=evidence(); ctl,_,_,_=make(monkeypatch,tmp_path,[current],AdmissionOutcome.DENY)
    with pytest.raises(ResidentCognitiveModelServingError,match="control_plane_not_allowed"): ctl.establish(operation_id="resident-operation-1")

def test_config_is_opt_in_and_never_selects_model(tmp_path):
    disabled=tmp_path/"disabled.json"; disabled.write_text(json.dumps({"schema_version":CONFIG_SCHEMA,"enabled":False}))
    assert load_config(str(disabled)).enabled is False
    valid=tmp_path/"valid.json"; valid.write_text(json.dumps({"schema_version":CONFIG_SCHEMA,"enabled":True,"installation_identity":"install-1","serving_operation_id":"resident-op","expected_activation_state_digest":"a"*64}))
    assert load_config(str(valid)).installation_identity=="install-1"
    for key in ("model_path","runtime_path","fallback_model","activation_path"):
        bad=tmp_path/(key+".json"); bad.write_text(json.dumps({"schema_version":CONFIG_SCHEMA,"enabled":True,key:"x"}))
        with pytest.raises(ResidentCognitiveModelServingError): load_config(str(bad))
