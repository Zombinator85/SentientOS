from __future__ import annotations
import copy
from pathlib import Path
from types import SimpleNamespace
import pytest
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model_catalog import local_model_catalog_digest, validate_local_model_catalog
from sentientos.local_model_catalog_consumer_custody import CatalogConsumerCustodyError, construct_authoritative_catalog_consumer_proof
from sentientos.local_model_catalog_deployment import CatalogDeploymentAuthority, CatalogDeploymentRequest, deploy_local_model_catalog
from sentientos.local_model_catalog_deployment_architecture import EFFECTS, EXPECTED_ABSENT, semantic_digest
from sentientos.local_model_selection import GIB, LocalInferenceHardwareProfile, plan_local_model_selection_catalog, plan_local_model_selection_deployed
from sentientos.local_model_artifact_acquisition import ModelArtifactAcquisitionError, acquire_model_artifact, authorization_for, compose_acquisition_plan, compose_deployed_acquisition_plan
from sentientos.model_catalog_custody import ModelCatalogCustody
from sentientos.model_mirror_publication import RECEIPT_SCHEMA

pytestmark = pytest.mark.no_legacy_skip
NOW="2026-09-07T12:00:00Z"

def catalog(priority=1):
 d="a"*64; f=f"fixture-{d}.gguf"
 return validate_local_model_catalog({"schema_version":"sentientos.local_model_catalog:v1","models":[{"model_id":"fixture","priority":priority,"license_id":"apache-2.0","source_repository":"example/fixture","source_revision":"b"*40,"source_artifact_filename":"models/fixture.gguf","artifact_filename":f,"artifact_sha256":d,"artifact_size_bytes":42,"artifact_content_address":f"sha256:{d}","artifact_urls":[f"https://models.sentientos.org/{f}"],"requirements":{"architecture":"x86_64","ram_gb_min":1,"avx":False,"avx2":False,"avx512":False,"quantization":"q4"},"execution_routes":[{"route_id":"cpu","engine":"llama_cpp","backend_family":"cpu","route_priority":1}]}]})

def publication(c):
 m=c["models"][0]; r={"schema_version":RECEIPT_SCHEMA,"model_id":m["model_id"],"artifact_sha256":m["artifact_sha256"],"artifact_size":m["artifact_size_bytes"],"canonical_url":m["artifact_urls"][0],"object_exists":True,"object_verified":True,"remote_verification_method":"complete_streamed_sha256","remote_digest":m["artifact_sha256"],"remote_size":m["artifact_size_bytes"],"final_publication_status":"published_verified","catalog_deployment_eligible":True,"catalog_deployed":False}; r["receipt_id"]="model-publication-"+semantic_digest(r)[:24];r["receipt_semantic_digest"]=semantic_digest(r);return r

def deploy(tmp_path,c,expected=EXPECTED_ABSENT):
 h=InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("fixture"),create=True); cu=ModelCatalogCustody.for_installation(h); d=local_model_catalog_digest(c)
 req=CatalogDeploymentRequest("deterministic_catalog_deployment_controller","sentientos.local_model_catalog.deploy",EFFECTS,"grant","lease",f"corr-{priority(c)}","fixture",cu.custody_identity,d,expected)
 auth=CatalogDeploymentAuthority("grant","lease",req.principal,req.capability_id,EFFECTS,req.correlation_id,"fixture",cu.custody_identity,d,expected,True,"2026-09-07T00:00:00Z","2026-09-08T00:00:00Z",synthetic_test_authority=True)
 assert deploy_local_model_catalog(h,req,auth,c,[publication(c)],now=lambda:NOW).status=="deployed_verified";return h

def priority(c): return c["models"][0]["priority"]
def host(): return LocalInferenceHardwareProfile(source_inventory_id="i",source_inventory_digest="0"*64,os_family="linux",architecture="x86_64",total_ram_bytes=8*GIB,avx=True,avx2=True,avx512=False,accelerator_observed=False,accelerator_vendor=None)
def chain(selection):
 s=selection["selected"]; p={"schema_version":"sentientos.local_runtime_provisioning:v1","status":"selected","selection_plan_digest":selection["plan_digest"],"selected_model_id":s["model_id"],"selected_model_artifact_sha256":s["artifact_sha256"],"selected_route_id":s["route_id"],"engine":s["engine"],"backend_family":s["backend_family"],"runtime_id":"runtime-cpu"};p["provisioning_plan_digest"]=semantic_digest(p)
 b={"schema_version":"sentientos.local_runtime_backend_verification_receipt:v1","status":"runtime_backend_verified","runtime_provisioning_plan_digest":p["provisioning_plan_digest"],"runtime_id":"runtime-cpu","engine":"llama_cpp","backend_family":"cpu","selected_backend_verified":True,"backend_runtime_visibility_verified":True,"model_load_performed":False,"inference_performed":False};b["receipt_semantic_digest"]=semantic_digest(b);return p,b

def test_authoritative_deployed_proof_construction(tmp_path):
 h=deploy(tmp_path,catalog()); s=construct_authoritative_catalog_consumer_proof(h); assert s.proof["authoritative_catalog_semantic_digest"]==local_model_catalog_digest(s.catalog);assert s.proof["authority_granted"] is False

def test_production_selection_from_proven_catalog(tmp_path):
 h=deploy(tmp_path,catalog()); p=plan_local_model_selection_deployed(host(),h);assert p["status"]=="selected" and p["authoritative_deployed_catalog_verified"] is True

def test_production_acquisition_plan_bound_to_proof(tmp_path):
 h=deploy(tmp_path,catalog());s=plan_local_model_selection_deployed(host(),h);p,b=chain(s);a=compose_deployed_acquisition_plan(s,p,b,h,tmp_path/"e");assert a["authoritative_catalog_proof_digest"]==s["authoritative_catalog_proof_digest"]

def test_preview_cannot_execute(tmp_path):
 c=catalog();s=plan_local_model_selection_catalog(host(),c);p,b=chain(s);a=compose_acquisition_plan(s,p,b,c,tmp_path/"e")
 with pytest.raises(ModelArtifactAcquisitionError,match="handle_required"): acquire_model_artifact(a,execute=True,authorization=authorization_for(a,operator_confirmed=True))

def test_stale_catalog_proof_rejected_before_effect(tmp_path):
 c=catalog();h=deploy(tmp_path,c);s=plan_local_model_selection_deployed(host(),h);p,b=chain(s);a=compose_deployed_acquisition_plan(s,p,b,h,tmp_path/"e");deploy(tmp_path,catalog(2),local_model_catalog_digest(c)); calls=[]
 with pytest.raises(ModelArtifactAcquisitionError,match="stale_or_untrusted"): acquire_model_artifact(a,execute=True,installation_handle=h,authorization=authorization_for(a,operator_confirmed=True),transport=lambda u:calls.append(u))
 assert calls==[]

def test_absent_and_malformed_authoritative_catalog_fail_closed(tmp_path):
 h=InstallationStateRegistry._for_testing(tmp_path).open(InstallationIdentity("fixture"),create=True);cu=ModelCatalogCustody.for_installation(h);cu.initialize_directories()
 with pytest.raises(CatalogConsumerCustodyError): construct_authoritative_catalog_consumer_proof(h)
 h.durable_create(cu.authoritative_catalog,b"bad")
 with pytest.raises(CatalogConsumerCustodyError): construct_authoritative_catalog_consumer_proof(h)

def test_tampered_receipt_and_finalization_fail_closed(tmp_path):
 h=deploy(tmp_path,catalog());cu=ModelCatalogCustody.for_installation(h);name=h.list_regular_names(cu.deployment_receipts)[0]; path=cu.deployment_receipts.child(name).path; raw=path.read_bytes();path.write_bytes(raw.replace(b'"final_state":"deployed_verified"',b'"final_state":"not_committed"'))
 with pytest.raises(CatalogConsumerCustodyError,match="receipt_invalid"):construct_authoritative_catalog_consumer_proof(h)
