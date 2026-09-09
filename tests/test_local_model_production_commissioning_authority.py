from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
pytestmark = pytest.mark.no_legacy_skip
from types import SimpleNamespace
from sentientos.local_model_production_commissioning_authority import (APPROVAL_SCHEMA, EFFECTS, INTENT_SCHEMA, CommissioningAuthorityError, build_intent, child_smoke_correlation, verify_external_approval)
from sentientos.local_runtime_provisioning import semantic_digest

def _handle(tmp_path): return SimpleNamespace(identity=SimpleNamespace(value="machine-one"), root=tmp_path)
def _intent(monkeypatch,tmp_path):
 proof={"installation_identity":"machine-one","custody_identity":"catalog:machine-one","authoritative_catalog_semantic_digest":"d"*64,"proof_semantic_digest":"e"*64,"deployment_receipt_id":"deployment-one","deployment_receipt_semantic_digest":"f"*64}
 plan={"acquisition_plan_digest":"a"*64,"installation_identity":"machine-one","catalog_custody_identity":"catalog:machine-one","local_model_catalog_digest":"d"*64,"authoritative_catalog_proof_digest":"e"*64,"deployment_receipt_id":"deployment-one","deployment_receipt_semantic_digest":"f"*64}
 receipt={"schema_version":"sentientos.local_model_artifact_acquisition_receipt:v2","receipt_semantic_digest":"b"*64}
 chain={"authoritative_evidence":{"acquisition_plan":plan,"acquisition_receipt":receipt},"model_id":"model-one","artifact_id":"artifact-one","artifact_sha256":"c"*64,"artifact_size_bytes":7,"artifact_path":"/custody/model.gguf","route_id":"route-one","engine":"llama_cpp","backend_family":"cpu","runtime_id":"runtime-one","interpreter_path":"/runtime/python"}
 monkeypatch.setattr("sentientos.local_model_production_commissioning_authority.current_proof",lambda handle,plan:proof)
 monkeypatch.setattr("sentientos.local_model_production_commissioning_authority.commissioning_custody",lambda handle:{"commissioning_output_custody_identity":"installation-local-model-commissioning:machine-one","commissioning_domain":"local-model/commissioning","receipt_directory":"local-model/commissioning/receipts","smoke_directory":"local-model/commissioning/smoke"})
 monkeypatch.setattr("sentientos.local_model_artifact_acquisition.verify_acquisition_receipt",lambda receipt,plan:True)
 return build_intent(chain,_handle(tmp_path),correlation_id="commissioning-parent-one")
def _approval(intent,synthetic=False):
 now=datetime(2026,9,8,tzinfo=timezone.utc); keys=("target_principal","target_capability","effects","correlation_id","intent_id","intent_semantic_digest","installation_identity","catalog_custody_identity","authoritative_catalog_proof_digest","deployment_receipt_id","deployment_receipt_semantic_digest","hardened_acquisition_receipt_identity","hardened_acquisition_receipt_digest","model_id","artifact_id","route_id","runtime_id","artifact_sha256","artifact_size_bytes","compatibility_probe_contract","load_configuration","smoke_contract","commissioning_output_custody_identity")
 value={"schema_version":APPROVAL_SCHEMA,"approval_evidence_id":"operator-event-123","operator_identity":"operator-alice","approval_status":"approved","evidence_source":"external-console","evidence_provenance":"signed-event-ledger",**{k:intent[k] for k in keys},"not_before":(now-timedelta(minutes=1)).isoformat(),"expires_at":(now+timedelta(minutes=1)).isoformat(),"approval_timestamp":now.isoformat(),"synthetic_test_evidence":synthetic}; value["approval_semantic_digest"]=semantic_digest(value); return value,now
def test_deterministic_current_commissioning_intent(monkeypatch,tmp_path):
 a=_intent(monkeypatch,tmp_path); b=_intent(monkeypatch,tmp_path); assert a==b and a["schema_version"]==INTENT_SCHEMA and a["effects"]==sorted(EFFECTS)
def test_exact_external_approval_and_distinct_deterministic_child(monkeypatch,tmp_path):
 intent=_intent(monkeypatch,tmp_path); approval,now=_approval(intent); assert verify_external_approval(approval,intent,observation_time=now)["operator_identity"]=="operator-alice"; child=child_smoke_correlation(intent["correlation_id"],intent); assert child!=intent["correlation_id"] and child==child_smoke_correlation(intent["correlation_id"],intent)
@pytest.mark.parametrize("mutation",["subset","duplicate","expired","synthetic","placeholder"])
def test_external_approval_fails_closed(monkeypatch,tmp_path,mutation):
 intent=_intent(monkeypatch,tmp_path); approval,now=_approval(intent)
 if mutation=="subset": approval["effects"]=approval["effects"][:-1]
 elif mutation=="duplicate": approval["effects"]+=[approval["effects"][0]]
 elif mutation=="expired": approval["expires_at"]=(now-timedelta(seconds=1)).isoformat()
 elif mutation=="synthetic": approval["synthetic_test_evidence"]=True
 else: approval["operator_identity"]="placeholder"
 approval["approval_semantic_digest"]=semantic_digest({k:v for k,v in approval.items() if k!="approval_semantic_digest"})
 with pytest.raises(CommissioningAuthorityError): verify_external_approval(approval,intent,observation_time=now)
