import pytest
from pathlib import Path
from sentientos import maintenance_commit_publication as m
from tests.maintenance_commit_publication_fixtures import setup,NOW
pytestmark=pytest.mark.no_legacy_skip
def test_commit_enqueues_without_remote_process(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); out=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); assert out['terminal_status']=='commit_ready_publication_queued' and out['remote_operations']==0
def test_exact_publication_request_is_idempotent(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); a=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); b=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); assert a['publication_request']['publication_request_digest']==b['publication_request']['publication_request_digest']
def test_conflicting_publication_request_fails_closed(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); a=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); q=Path(s)/'maintenance_publication_requests'/(a['publication_request']['publication_id']+'.json'); q.write_text('{"conflict":true}'); pytest.raises(m.MaintenanceLandingError,m.create_commit_and_enqueue,state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW)
def test_queue_state_is_derived_from_request_and_terminal_result(tmp_path):
 r,w,s,l,v,p=setup(tmp_path); a=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); assert m.list_queued_requests(s,repo_root=r); (Path(s)/'maintenance_publication_results').mkdir(); (Path(s)/'maintenance_publication_results'/(a['publication_request']['publication_id']+'.json')).write_text('{"terminal_classification":"publication_succeeded"}'); assert not m.list_queued_requests(s,repo_root=r)
