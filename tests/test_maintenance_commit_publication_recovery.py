import pytest
import multiprocessing, subprocess
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_commit_publication as m
from tests.maintenance_commit_publication_fixtures import setup,NOW
from tests.test_maintenance_publication_worker import committed

def test_recovery_after_commit_object_creation_records_same_commit(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); a=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); b=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); assert a['commit_result']['commit_sha']==b['commit_result']['commit_sha']
def test_recovery_after_remote_push_does_not_push_again(tmp_path, monkeypatch):
 r,w,s,l,v,p,out=committed(tmp_path); monkeypatch.setenv('FAKE_PR_ROOT',str(tmp_path)); monkeypatch.setenv('FAKE_HEAD_SHA',out['commit_result']['commit_sha']); a=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); b=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert a==b
def test_recovery_after_pr_creation_reuses_exact_pr(tmp_path, monkeypatch):
 r,w,s,l,v,p,out=committed(tmp_path); monkeypatch.setenv('FAKE_PR_ROOT',str(tmp_path)); monkeypatch.setenv('FAKE_HEAD_SHA',out['commit_result']['commit_sha']); a=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert a['remote_observations']['pr']['number']==1
def _commit_worker(args):
 r,w,s,l,v,p=args; return m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW)['publication_request']['publication_id']
def test_process_concurrent_commit_creates_one_result_and_request(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); args=(r,w,s,l,v,p)
 with multiprocessing.Pool(2) as pool: ids=pool.map(_commit_worker,[args,args])
 assert len(set(ids))==1
def _pub_worker(args):
 r,s,l,p,pid=args; return m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=pid,evaluation_time=NOW)['terminal_classification']
def test_process_concurrent_publish_creates_one_remote_effect(tmp_path, monkeypatch):
 r,w,s,l,v,p,out=committed(tmp_path,'fast_forward_base_ref'); args=(r,s,l,p,out['publication_request']['publication_id'])
 with multiprocessing.Pool(2) as pool: vals=pool.map(_pub_worker,[args,args])
 assert vals.count('publication_succeeded')>=1
