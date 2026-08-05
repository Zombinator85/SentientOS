import subprocess, pytest
from sentientos import maintenance_commit_publication as m
from tests.maintenance_commit_publication_fixtures import setup,NOW
pytestmark=pytest.mark.no_legacy_skip
def res(tmp_path): r,w,s,l,v,p=setup(tmp_path); return r,w,s,l,v,p,m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW)
def test_commit_tree_exactly_matches_validated_worktree(tmp_path):
 *_,out=res(tmp_path); proof=out['commit_result']['object_verification']; assert proof['parent_matches'] and proof['manifest_matches']
def test_commit_uses_external_index_and_moves_no_ref(tmp_path):
 r,w,s,l,v,p,out=res(tmp_path); assert out['commit_result']['external_index_path'].startswith(str(s)); assert out['commit_result']['commit_sha'] not in subprocess.run(['git','show-ref','--heads'],cwd=w,text=True,capture_output=True).stdout
def test_detached_worktree_head_remains_at_base(tmp_path):
 r,w,s,l,v,p,out=res(tmp_path); assert subprocess.run(['git','rev-parse','HEAD'],cwd=w,text=True,capture_output=True).stdout.strip()==v['base_sha']
def test_exact_commit_retry_is_idempotent(tmp_path):
 r,w,s,l,v,p,out=res(tmp_path); again=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); assert again['commit_result']['commit_sha']==out['commit_result']['commit_sha']
def test_conflicting_commit_plan_fails_closed(tmp_path):
 r,w,s,l,v,p,out=res(tmp_path); l['landing_terms']['commit_title']='[codex:sentientos] other'; pytest.raises(m.MaintenanceLandingError,m.create_commit_and_enqueue,state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW)
