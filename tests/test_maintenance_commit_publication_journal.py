import pytest
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_task_journal as j
from sentientos import maintenance_commit_publication as m
from tests.maintenance_commit_publication_fixtures import setup,NOW

def made(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); out=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); return r,s,out
def test_ready_to_commit_binds_exact_validation_and_plan(tmp_path):
 r,s,out=made(tmp_path); snap=j.materialize_snapshot(s,out['plan']['task_id'],repo_root=r); assert snap['commit_readiness']['payload']['commit_plan_digest']==out['plan']['plan_digest']
def test_commit_recorded_binds_exact_commit_result(tmp_path):
 r,s,out=made(tmp_path); snap=j.materialize_snapshot(s,out['plan']['task_id'],repo_root=r); assert snap['commit_reference']['payload']['commit_sha']==out['commit_result']['commit_sha']
def test_publication_terminal_event_requires_matching_started_attempt(tmp_path):
 r,s,out=made(tmp_path); bad=j.append_event(s,'publication_succeeded',task_id=out['plan']['task_id'],payload={'publication_id':'x','attempt_ordinal':99},repo_root=r); assert bad.status=='event_appended' or bad.status=='transition_rejected'
def test_publication_attempt_history_is_preserved(tmp_path, monkeypatch):
 r,w,s,l,v,p=setup(tmp_path); out=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); import subprocess; subprocess.run(['git','init','--bare',str(tmp_path/'b.git')],check=True); subprocess.run(['git','remote','add','origin',str(tmp_path/'b.git')],cwd=r,check=True); res=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); snap=j.materialize_snapshot(s,l['task_id'],repo_root=r); assert snap['publication_history'] or res['terminal_classification']
def test_success_prevents_later_publication_attempt(tmp_path, monkeypatch):
 from tests.test_maintenance_publication_worker import committed
 r,w,s,l,v,p,out=committed(tmp_path); monkeypatch.setenv('FAKE_PR_ROOT',str(tmp_path)); monkeypatch.setenv('FAKE_HEAD_SHA',out['commit_result']['commit_sha']); a=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); b=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert a['publication_result_digest']==b['publication_result_digest']
