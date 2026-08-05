import pytest
from sentientos import maintenance_commit_publication as m
from tests.maintenance_commit_publication_fixtures import setup,NOW
pytestmark=pytest.mark.no_legacy_skip
def test_same_inputs_produce_byte_identical_commit_plan(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); a=m.build_commit_plan(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); b=m.build_commit_plan(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); assert m.canonical_json_bytes(a)==m.canonical_json_bytes(b)
def test_commit_plan_requires_latest_passing_validation(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); v['terminal_status']='validation_failed_terminal'; pytest.raises(m.MaintenanceLandingError, m.build_commit_plan, state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW)
def test_commit_title_and_refs_are_lease_bound_and_safe(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); plan=m.build_commit_plan(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); assert plan['commit_title']=='[codex:sentientos] test objective'; assert plan['head_ref']=='sentientos/maintenance/task1'; pytest.raises(m.MaintenanceLandingError,m.derive_head_ref,'bad..ref','task', 'git', w)
def test_commit_plan_rejects_worktree_drift(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); (w/'a.txt').write_text('drift\n'); pytest.raises(m.MaintenanceLandingError,m.build_commit_plan,state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW)
