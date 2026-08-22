from __future__ import annotations
import copy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from sentientos.exact_artifact_acquisition import StreamResponse
from sentientos.local_runtime_dependencies import plan_runtime_dependencies, semantic_digest
from sentientos.local_runtime_dependency_acquisition import DependencyAcquisitionError, acquire_dependency_bundle, authorization_for, receipt_semantic_digest

pytestmark = pytest.mark.no_legacy_skip

def profile():
    return {"schema_version":"sentientos.local_runtime_environment_profile:v2","os_family":"linux","architecture":"x86_64",
        "python_implementation":"cpython","python_major":3,"python_minor":10,"python_abi":"cp310","source_identity":"synthetic",
        "source_digest":"a"*64,"missing_fact_codes":[],"libc_family":"glibc","libc_version":"2.17","macos_version":""}

def fixture():
    catalog=json.loads(Path("manifests/local-runtime-dependency-catalog-v1.json").read_text())
    bundle=next(b for b in catalog["environment_bundles"] if b["environment_id"]=="cpython310-linux-x86_64")
    payloads={artifact_id:("exact-"+artifact_id).encode() for artifact_id in bundle["artifact_ids"]}
    for item in catalog["artifacts"]:
        if item["artifact_id"] in payloads:
            data=payloads[item["artifact_id"]]; item["artifact_sha256"]=hashlib.sha256(data).hexdigest(); item["artifact_size_bytes"]=len(data)
            item["artifact_url"]="https://files.pythonhosted.org/packages/"+item["artifact_filename"]
    bundle["bundle_digest"]=semantic_digest({k:v for k,v in bundle.items() if k!="bundle_digest"})
    catalog["catalog_digest"]=semantic_digest({k:v for k,v in catalog.items() if k!="catalog_digest"})
    return catalog, plan_runtime_dependencies(catalog,profile()), payloads

class Transport:
    def __init__(self,payloads): self.payloads=payloads; self.calls=0
    def __call__(self,url):
        self.calls+=1; filename=url.rsplit("/",1)[1]
        data=self.by_filename[filename]
        return StreamResponse(io.BytesIO(data),{"Content-Length":str(len(data))},("files.pythonhosted.org",),0)
    by_filename={}

def test_inspection_authorization_end_to_end_and_zero_network_cache_hit(tmp_path):
    catalog,plan,payloads=fixture(); transport=Transport(payloads)
    transport.by_filename={a["artifact_filename"]:payloads[a["artifact_id"]] for a in plan["artifacts"]}
    root=tmp_path/"dependencies"
    inspection=acquire_dependency_bundle(plan,catalog=catalog,escrow_root=root)
    assert inspection["missing_artifact_count"]==5 and not root.exists()
    auth=authorization_for(plan,root,operator_confirmed=True)
    first=acquire_dependency_bundle(plan,catalog=catalog,escrow_root=root,authorization=auth,execute=True,
        transport=transport,disk_usage_provider=lambda _:SimpleNamespace(free=10**9))
    assert first["artifact_count"]==5 and first["dependency_bundle_availability_status"]=="acquired_verified"
    assert first["package_install_performed"] is first["runtime_import_performed"] is first["model_load_performed"] is False
    calls=transport.calls
    second=acquire_dependency_bundle(plan,catalog=catalog,escrow_root=root,authorization=auth,execute=True,transport=transport)
    assert second["status"]=="dependency_bundle_already_present_verified" and transport.calls==calls and not second["network_performed"]

def test_invalid_plan_and_authorization_fail_before_network(tmp_path):
    catalog,plan,payloads=fixture(); transport=Transport(payloads)
    changed=copy.deepcopy(plan); changed["status"]="blocked"
    with pytest.raises(DependencyAcquisitionError,match="dependency_plan_not_selected"):
        acquire_dependency_bundle(changed,catalog=catalog,escrow_root=tmp_path/"x",execute=True,transport=transport)
    with pytest.raises(DependencyAcquisitionError,match="invalid_dependency_acquisition_authorization"):
        acquire_dependency_bundle(plan,catalog=catalog,escrow_root=tmp_path/"x",execute=True,transport=transport)
    assert transport.calls==0

def test_missing_byte_space_preflight_and_digest_determinism(tmp_path):
    catalog,plan,payloads=fixture(); transport=Transport(payloads); root=tmp_path/"x"
    with pytest.raises(DependencyAcquisitionError,match="insufficient_dependency_escrow_space"):
        acquire_dependency_bundle(plan,catalog=catalog,escrow_root=root,authorization=authorization_for(plan,root,operator_confirmed=True),
            execute=True,transport=transport,disk_usage_provider=lambda _:SimpleNamespace(free=sum(a["artifact_size_bytes"] for a in plan["artifacts"])-1))
    assert transport.calls==0 and receipt_semantic_digest({"a":1,"retrieved_at":"x"})==receipt_semantic_digest({"retrieved_at":"y","a":1})
