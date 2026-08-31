from __future__ import annotations
import copy
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import pytest

from sentientos.exact_artifact_acquisition import StreamResponse
from sentientos.local_model_artifact_acquisition import (ModelArtifactAcquisitionError, acquire_model_artifact,
    authorization_for, compose_acquisition_plan, verify_acquisition_receipt)
from sentientos.local_model_catalog import validate_local_model_catalog
from sentientos.local_model_selection import GIB, LocalInferenceHardwareProfile, plan_local_model_selection_catalog
from sentientos.local_runtime_provisioning import semantic_digest

pytestmark = pytest.mark.no_legacy_skip

class FakeTransport:
    def __init__(self, data: bytes, *, length: int | None = None, hosts=("models.sentientos.org",), error=None):
        self.data, self.length, self.hosts, self.error, self.calls, self.urls = data, length, hosts, error, 0, []
    def __call__(self, url: str) -> StreamResponse:
        self.calls += 1; self.urls.append(url)
        if self.error: raise self.error
        headers = {} if self.length is None else {"Content-Length": str(self.length)}
        return StreamResponse(io.BytesIO(self.data), headers, self.hosts, max(0, len(self.hosts)-1))

def case(tmp_path: Path, *, backend="cpu", data=b"synthetic opaque GGUF bytes"):
    digest = hashlib.sha256(data).hexdigest(); filename=f"synthetic-{digest}.gguf"
    route = {"route_id":backend, "engine":"llama_cpp", "backend_family":backend, "route_priority":1}
    if backend == "cuda": route["accelerator_vendor"] = "nvidia"
    catalog = validate_local_model_catalog({"schema_version":"sentientos.local_model_catalog:v1", "models":[{
        "model_id":"synthetic", "priority":1, "license_id":"apache-2.0", "source_repository":"example/synthetic",
        "source_revision":"a"*40, "source_artifact_filename":"weights/synthetic.gguf",
        "artifact_filename":filename, "artifact_sha256":digest, "artifact_size_bytes":len(data),
        "artifact_content_address":f"sha256:{digest}", "artifact_urls":[f"https://models.sentientos.org/{filename}"],
        "requirements":{"architecture":"x86_64","ram_gb_min":1,"avx":False,"avx2":False,"avx512":False,"quantization":"q4"},
        "execution_routes":[route]}]})
    profile=LocalInferenceHardwareProfile(source_inventory_id="i",source_inventory_digest="0"*64,os_family="linux",
        architecture="x86_64",total_ram_bytes=8*GIB,avx=True,avx2=True,avx512=False,
        accelerator_observed=backend != "cpu", accelerator_vendor="nvidia" if backend=="cuda" else None)
    selection=plan_local_model_selection_catalog(profile,catalog)
    selected=selection["selected"]
    provision={"schema_version":"sentientos.local_runtime_provisioning:v1","status":"selected",
        "selection_plan_digest":selection["plan_digest"],"selected_model_id":selected["model_id"],
        "selected_model_artifact_sha256":selected["artifact_sha256"],"selected_route_id":selected["route_id"],
        "engine":selected["engine"],"backend_family":selected["backend_family"],"runtime_id":f"runtime-{backend}"}
    provision["provisioning_plan_digest"]=semantic_digest(provision)
    receipt={"schema_version":"sentientos.local_runtime_backend_verification_receipt:v1","status":"runtime_backend_verified",
        "runtime_provisioning_plan_digest":provision["provisioning_plan_digest"],"runtime_id":provision["runtime_id"],
        "engine":backend and "llama_cpp","backend_family":backend,"selected_backend_verified":True,
        "backend_runtime_visibility_verified":True,"model_load_performed":False,"inference_performed":False}
    receipt["receipt_semantic_digest"]=semantic_digest(receipt)
    plan=compose_acquisition_plan(selection,provision,receipt,catalog,tmp_path/"escrow")
    return data,catalog,selection,provision,receipt,plan

def execute(data, plan, transport=None, free=10**9):
    return acquire_model_artifact(plan,execute=True,authorization=authorization_for(plan,operator_confirmed=True),
        transport=transport or FakeTransport(data),disk_usage_provider=lambda _:SimpleNamespace(free=free))

def test_deterministic_cross_bound_plan_and_inspection_are_zero_effect(tmp_path: Path):
    *_, plan=case(tmp_path)
    assert plan == compose_acquisition_plan(*case(tmp_path)[2:5],case(tmp_path)[1],tmp_path/"escrow")
    result=acquire_model_artifact(plan)
    assert result["status"]=="inspection_ready" and not (tmp_path/"escrow").exists()
    assert plan["model_loaded"] is plan["inference_authority_granted"] is plan["provider_invoked"] is False

@pytest.mark.parametrize(("which","code"),[("selection","local_model_selection_invalid"),
    ("provision","runtime_provisioning_invalid"),("backend","backend_verification_receipt_invalid")])
def test_tampered_evidence_fails_closed(tmp_path: Path,which,code):
    _,catalog,selection,provision,backend,_=case(tmp_path); values={"selection":selection,"provision":provision,"backend":backend}
    values[which][next(k for k in values[which] if k not in {"plan_digest","provisioning_plan_digest","receipt_semantic_digest"})]="tampered"
    with pytest.raises(ModelArtifactAcquisitionError,match=code):
        compose_acquisition_plan(selection,provision,backend,catalog,tmp_path/"e")

def test_crossed_route_provisioning_and_backend_fail(tmp_path: Path):
    _,catalog,selection,provision,backend,_=case(tmp_path)
    crossed=dict(provision); crossed["backend_family"]="cuda"; crossed["provisioning_plan_digest"]=semantic_digest({k:v for k,v in crossed.items() if k!="provisioning_plan_digest"})
    with pytest.raises(ModelArtifactAcquisitionError,match="selection_provisioning_binding_mismatch"):
        compose_acquisition_plan(selection,crossed,backend,catalog,tmp_path/"e")
    wrong=dict(backend); wrong["backend_family"]="cuda"; wrong["receipt_semantic_digest"]=semantic_digest({k:v for k,v in wrong.items() if k!="receipt_semantic_digest"})
    with pytest.raises(ModelArtifactAcquisitionError,match="provisioning_backend_binding_mismatch"):
        compose_acquisition_plan(selection,provision,wrong,catalog,tmp_path/"e")

def test_catalog_artifact_and_route_substitution_fail(tmp_path: Path):
    _,catalog,selection,provision,backend,_=case(tmp_path)
    for mutation in ("artifact","route"):
        changed=copy.deepcopy(catalog)
        if mutation=="artifact": changed["models"][0]["artifact_size_bytes"]+=1
        else: changed["models"][0]["execution_routes"][0]["route_id"]="other"
        changed.pop("local_model_catalog_digest",None)
        with pytest.raises(ModelArtifactAcquisitionError):
            compose_acquisition_plan(selection,provision,backend,changed,tmp_path/"e")

def test_authorization_and_space_fail_before_network(tmp_path: Path):
    data,*_,plan=case(tmp_path); transport=FakeTransport(data)
    with pytest.raises(ModelArtifactAcquisitionError,match="authorization"):
        acquire_model_artifact(plan,execute=True,transport=transport)
    assert transport.calls==0
    with pytest.raises(ModelArtifactAcquisitionError,match="insufficient"):
        execute(data,plan,transport,free=0)
    assert transport.calls==0

def test_stream_publish_receipt_and_verified_cache_hit(tmp_path: Path):
    data,*_,plan=case(tmp_path); transport=FakeTransport(data,length=len(data))
    first=execute(data,plan,transport); assert first["status"]=="model_artifact_acquired_verified"
    assert transport.urls==[plan["canonical_source_url"]] and verify_acquisition_receipt(first,plan)
    assert all(first[k] is False for k in ("runtime_installation_performed","runtime_import_performed","backend_probe_performed",
        "gguf_compatibility_verified","model_loaded","model_commissioned","inference_performed","inference_authority_granted",
        "prompt_assembly_performed","provider_invoked"))
    second_transport=FakeTransport(b"bad")
    second=execute(data,plan,second_transport)
    assert second["status"]=="already_present_verified" and second["receipt_semantic_digest"]==first["receipt_semantic_digest"]
    assert second_transport.calls==0

@pytest.mark.parametrize(("payload","length","code"),[(b"short",5,"model_artifact_size_mismatch"),
    (b"synthetic opaque GGUF bytez",None,"model_artifact_hash_mismatch"),
    (b"synthetic opaque GGUF bytes-extra",None,"model_artifact_size_mismatch")])
def test_exact_stream_failures_leave_no_canonical_artifact(tmp_path: Path,payload,length,code):
    data,*_,plan=case(tmp_path)
    with pytest.raises(ModelArtifactAcquisitionError,match=code): execute(data,plan,FakeTransport(payload,length=length))
    assert not (Path(plan["escrow_root"])/plan["final_relative_escrow_path"]).exists()

def test_corrupt_existing_symlink_and_concurrent_publication(tmp_path: Path):
    data,*_,plan=case(tmp_path); final=Path(plan["escrow_root"])/plan["final_relative_escrow_path"]
    final.mkdir(parents=True); (final/"junk").write_text("x")
    with pytest.raises(ModelArtifactAcquisitionError,match="conflict"): execute(data,plan)
    import shutil; shutil.rmtree(Path(plan["escrow_root"])); target=tmp_path/"target";target.mkdir();Path(plan["escrow_root"]).symlink_to(target,True)
    with pytest.raises(ModelArtifactAcquisitionError,match="unsafe"): execute(data,plan)
    Path(plan["escrow_root"]).unlink()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:execute(data,plan),range(2)))
    assert sorted(r["status"] for r in results)==["already_present_verified","model_artifact_acquired_verified"]

def test_tampered_receipt_is_not_downstream_authority(tmp_path: Path):
    data,*_,plan=case(tmp_path); receipt=execute(data,plan); bad=dict(receipt);bad["model_loaded"]=True
    with pytest.raises(ModelArtifactAcquisitionError,match="receipt_invalid"): verify_acquisition_receipt(bad,plan)
