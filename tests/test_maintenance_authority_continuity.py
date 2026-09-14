import copy
import json
from pathlib import Path

import pytest

from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_authority_continuity as c

pytestmark = pytest.mark.no_legacy_skip
NOW="2030-01-02T00:00:00Z"

def write(path:Path, value:dict)->Path:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(c.canonical_bytes(value)+b"\n"); return path

def sealed(value:dict,key:str)->dict:
    value[key]=c.digest(value,key); return value

def setup(tmp_path:Path):
    repo=tmp_path/"repo"; repo.mkdir(); root=tmp_path/"custody"; base="a"*40
    m=profiles.manifest_template(); m.update(template_no_authority=False,manifest_id="line-generation-0",repository_identity="repo",repository_root=str(repo.resolve()),base_sha=base,allowed_candidate_kinds=["repair"],allowed_path_prefixes=["sentientos/"],forbidden_paths=[".git/**"],authority_classes=["repository_commit","local_repository_base_advance"],budgets={"maximum_file_count":2,"maximum_changed_line_count":20,"maximum_implementation_seconds":10,"maximum_validation_seconds":20,"maximum_wall_clock_seconds":40,"maximum_attempts":1,"maximum_corrective_retries":0,"publication_retry_backoff_seconds":1,"maximum_actions":2},operator_reference="operator",approval_reference="approval",not_before="2030-01-01T00:00:00Z",expires_at="2030-02-01T00:00:00Z",state_root=str((tmp_path/"state").resolve()),workspace_root=str((tmp_path/"work").resolve()),scratch_root=str((tmp_path/"scratch").resolve()),inbox_root=str((tmp_path/"inbox").resolve()),codex_home=str((tmp_path/"codex").resolve()),codex_executable=str(Path("/bin/false").resolve()),git_executable=str(Path("/bin/false").resolve()),python_executable=str(Path("/bin/false").resolve()),validation_bounds={"aggregate_validation_ceiling_seconds":20,"per_command_default_ceiling_seconds":10,"terminal_reserve_seconds":1,"heartbeat_interval_seconds":1,"output_tail_limit":100,"output_byte_limit":1000,"maximum_controller_cycles":1,"require_declared_behavioral_test":True},publication_mode="local_fast_forward_base_ref",remote_name="origin",tracked_base_ref="refs/heads/main",base_ref="refs/heads/main",head_ref_prefix="maint/",publication_client_executable=None,commit_identity={"author_name":"a","author_email":"a@b","committer_name":"a","committer_email":"a@b","reference":"r"},commit_title_policy={"prefix":"[maintenance]"},output_directory=str((root/"profile-0").resolve()))
    m["manifest_digest"]=profiles.digest(m,"manifest_digest"); mp=write(root/"manifest-0.json",m); rendered=profiles.render_profile_bundle(mp)
    p=sealed({"schema_version":c.POLICY_SCHEMA,"policy_id":"policy","policy_digest":"","lineage_id":"line","repository_identity":"repo","generation_root":str(root.resolve()),"receipt_root":str((root/"receipts").resolve()),"initial_generation_path":str((root/"generation-0.json").resolve()),"operator_reference":"operator","approval_reference":"approval","created_at":NOW,"constraints":["same_or_narrower","local_fast_forward_base_ref","no_runtime_adoption"]},"policy_digest")
    g={"schema_version":c.GENERATION_SCHEMA,"generation_id":"line:generation:0","generation_digest":"","lineage_id":"line","ordinal":0,"base_sha":base,"manifest_path":str(mp.resolve()),"manifest_digest":m["manifest_digest"],"profile_bundle_digest":rendered["bundle_digest"],"predecessor_generation_digest":"","prior_receipt_digest":"","created_at":NOW}; g["generation_digest"]=c._generation_digest(g)
    return write(root/"policy.json",p),write(root/"generation-0.json",g),g,root

def evidence(tmp_path:Path,g:dict,n:int):
    sha=f"{n+1:x}"*40
    cm=sealed({"schema_version":c.COMPLETION_SCHEMA,"evidence_id":f"done{n}","evidence_digest":"","generation_digest":g["generation_digest"],"task_id":f"task{n}","lease_id":f"lease{n}","lease_digest":"sha256:l","admission_status":"admitted","implementation_status":"implemented","implementation_evidence_digest":"sha256:i","validation_status":"passed","validation_evidence_digest":"sha256:v","validated_commit_sha":sha,"commit_status":"committed","commit_evidence_digest":"sha256:c","landing_status":"landed","landing_evidence_digest":"sha256:l2","terminal_status":"completed","closure_evidence_digest":"sha256:t","integrity_status":"verified"},"evidence_digest")
    s=sealed({"schema_version":c.SUCCESSOR_SCHEMA,"evidence_id":f"next{n}","evidence_digest":"","mode":"local_fast_forward_base_ref","predecessor_base_sha":g["base_sha"],"successor_sha":sha,"validated_commit_sha":sha,"commit_parent_sha":g["base_sha"],"expected_old_sha":g["base_sha"],"base_ref":"refs/heads/main","base_ref_after":sha,"canonical_tracked_ref":"refs/heads/main","canonical_tracked_ref_sha":sha,"checkout_synchronization":"synchronized","checkout_head_sha":sha,"current_repository_sha":sha,"current_repository_clean":True,"network_performed":False,"runtime_adoption_performed":False},"evidence_digest")
    return write(tmp_path/f"completion{n}.json",cm),write(tmp_path/f"successor{n}.json",s),cm,s

def test_two_generation_inheritance_and_exact_retry(tmp_path:Path):
    policy,_,g0,root=setup(tmp_path); cp,sp,_,_=evidence(tmp_path,g0,0)
    one=c.derive_next(policy,cp,sp,NOW); assert one["status"]=="successor_generation_ready"
    assert c.derive_next(policy,cp,sp,NOW)["write_status"]=="reused"
    g1=json.loads((root/"generation-1.json").read_text()); cp2,sp2,_,_=evidence(tmp_path,g1,1)
    two=c.derive_next(policy,cp2,sp2,NOW); assert two["status"]=="successor_generation_ready"
    assert json.loads((root/"generation-2.json").read_text())["ordinal"]==2
    assert not any("adoption" in p.name for p in root.iterdir())

@pytest.mark.parametrize("field,value",[("admission_status","waiting"),("validation_status","failed"),("landing_status","publication_requested"),("terminal_status","paused")])
def test_incomplete_failed_or_unlanded_rejected(tmp_path:Path,field:str,value:object):
    policy,_,g,_=setup(tmp_path); cp,sp,cm,_=evidence(tmp_path,g,0); cm[field]=value; sealed(cm,"evidence_digest"); write(cp,cm)
    assert c.derive_next(policy,cp,sp,NOW)["status"]=="continuity_not_ready"

@pytest.mark.parametrize("field,value",[("mode","pull_request"),("commit_parent_sha","f"*40),("current_repository_sha","f"*40),("base_ref_after","f"*40),("current_repository_clean",False)])
def test_nonexact_successor_rejected(tmp_path:Path,field:str,value:object):
    policy,_,g,_=setup(tmp_path); cp,sp,_,s=evidence(tmp_path,g,0); s[field]=value; sealed(s,"evidence_digest"); write(sp,s)
    assert c.derive_next(policy,cp,sp,NOW)["status"]=="continuity_not_ready"

def test_expired_predecessor_and_conflicting_output_fail_closed(tmp_path:Path):
    policy,_,g,root=setup(tmp_path); cp,sp,_,_=evidence(tmp_path,g,0)
    assert c.derive_next(policy,cp,sp,"2031-01-01T00:00:00Z")["status"]=="continuity_not_ready"
    (root/"generation-1.json").write_text("{}")
    assert c.derive_next(policy,cp,sp,NOW)["status"]=="continuity_not_ready"

def test_same_or_narrower_mechanical_widening_checks(tmp_path:Path):
    _,_,_,root=setup(tmp_path); old=json.loads((root/"manifest-0.json").read_text())
    mutations=[("authority_classes",old["authority_classes"]+["remote_ref_publish"]),("allowed_candidate_kinds",old["allowed_candidate_kinds"]+["feature"]),("allowed_path_prefixes",old["allowed_path_prefixes"]+["docs/"]),("expires_at","2031-01-01T00:00:00Z")]
    for key,value in mutations:
        new=copy.deepcopy(old); new[key]=value; assert not c._same_or_narrower(old,new)
    for key in old["budgets"]:
        new=copy.deepcopy(old); new["budgets"][key]+=1; assert not c._same_or_narrower(old,new)

def test_corrupt_lineage_and_controller_has_no_effect_authority(tmp_path:Path):
    policy,_,g,root=setup(tmp_path); cp,sp,_,_=evidence(tmp_path,g,0); assert c.derive_next(policy,cp,sp,NOW)["status"]=="successor_generation_ready"
    receipt=json.loads((root/"receipts/receipt-1.json").read_text()); receipt["completed_task_id"]="tampered"; write(root/"receipts/receipt-1.json",receipt)
    assert c.inspect(policy)["status"]=="continuity_blocked"
    source=Path(c.__file__).read_text(); assert "subprocess" not in source and "requests" not in source and "sentientosd" not in source
