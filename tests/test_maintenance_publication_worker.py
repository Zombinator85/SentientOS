import os, subprocess
from pathlib import Path
import pytest
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_commit_publication as m
from tests.maintenance_commit_publication_fixtures import setup,NOW

def bare(tmp_path, r, base):
 b=tmp_path/'remote.git'; subprocess.run(['git','init','--bare',str(b)],check=True); subprocess.run(['git','remote','add','origin',str(b)],cwd=r,check=True); subprocess.run(['git','push','origin',f'{base}:refs/heads/main'],cwd=r,check=True); return b
def committed(tmp_path, mode='pull_request'):
 r,w,s,l,v,p=setup(tmp_path,mode); out=m.create_commit_and_enqueue(state_root=s,repository_root=r,worktree_root=w,lease=l,validation_result=v,landing_policy=p,evaluation_time=NOW); bare(tmp_path,r,v['base_sha']); return r,w,s,l,v,p,out

def test_fast_forward_mode_publishes_only_when_remote_base_matches_parent(tmp_path):
 r,w,s,l,v,p,out=committed(tmp_path,'fast_forward_base_ref'); res=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert res['terminal_classification']=='publication_succeeded'; assert res['remote_observations']['remote_oid']==out['commit_result']['commit_sha']
def test_fast_forward_mode_never_force_pushes(tmp_path):
 r,w,s,l,v,p,out=committed(tmp_path,'fast_forward_base_ref'); res=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert '--force' not in ' '.join(res['remote_observations'].get('push_argv',[])) and res['force_push_used'] is False
def test_pull_request_mode_pushes_exact_head_and_creates_exact_pr(tmp_path, monkeypatch):
 r,w,s,l,v,p,out=committed(tmp_path); monkeypatch.setenv('FAKE_PR_ROOT',str(tmp_path)); monkeypatch.setenv('FAKE_HEAD_SHA',out['commit_result']['commit_sha']); res=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert res['terminal_classification']=='publication_succeeded' and res['remote_observations']['pr']['headRefOid']==out['commit_result']['commit_sha']
def test_existing_exact_remote_ref_and_pr_are_reused(tmp_path, monkeypatch):
 r,w,s,l,v,p,out=committed(tmp_path); monkeypatch.setenv('FAKE_PR_ROOT',str(tmp_path)); monkeypatch.setenv('FAKE_HEAD_SHA',out['commit_result']['commit_sha']); a=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); b=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert b['publication_result_digest']==a['publication_result_digest']
def test_conflicting_remote_ref_or_pr_fails_closed(tmp_path):
 r,w,s,l,v,p,out=committed(tmp_path); subprocess.run(['git','push','origin',f"{v['base_sha']}:refs/heads/{out['publication_request']['head_ref']}"],cwd=r,check=True); res=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert res['terminal_classification']=='publication_remote_conflict'
def test_authentication_failure_is_classified_without_login(tmp_path, monkeypatch):
 r,w,s,l,v,p,out=committed(tmp_path); monkeypatch.setenv('FAKE_PR_MODE','auth'); res=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert res['terminal_classification']=='publication_authentication_unavailable'
def test_publication_waits_for_no_hosted_checks(tmp_path, monkeypatch):
 r,w,s,l,v,p,out=committed(tmp_path); monkeypatch.setenv('FAKE_PR_ROOT',str(tmp_path)); monkeypatch.setenv('FAKE_HEAD_SHA',out['commit_result']['commit_sha']); res=m.publish_one_maintenance_request(state_root=s,repository_root=r,lease=l,landing_policy=p,publication_id=out['publication_request']['publication_id'],evaluation_time=NOW); assert res['hosted_checks_waited'] is False
