import os, time, subprocess, pytest
from pathlib import Path
from sentientos.maintenance_local_codex_foreman import *
from tests.local_codex_foreman_fixtures import *
pytestmark=pytest.mark.no_legacy_skip
def bundle(tmp_path, mode='success'):
    repo,sha=make_repo(tmp_path); fake=make_fake_cli(tmp_path,mode); cfg=make_config(tmp_path,repo,fake,mode); lease=make_lease(sha); sess=make_session(lease); art=tmp_path/'art'; art.mkdir(); req=make_request(lease,art); return cfg,lease,req,sess,art,repo,sha
def runmode(tmp_path,mode):
    cfg,lease,req,sess,art,repo,sha=bundle(tmp_path,mode); return run_local_codex_session(cfg,lease,req,sess,art),cfg,lease,sess,repo,sha
def test_local_codex_driver_requires_all_effect_authorities(tmp_path):
    cfg,lease,req,sess,art,*_=bundle(tmp_path); req['requested_authority_classes']=['implementation_agent_session'];
    with pytest.raises(ValueError): run_local_codex_session(cfg,lease,req,sess,art)
def test_successful_run_changes_only_admitted_paths(tmp_path):
    r,*_=runmode(tmp_path,'success'); assert r['status']=='implementation_ready_for_validation' and r['changed_paths']==['allowed.txt']
def test_agent_text_success_without_worktree_change_is_rejected(tmp_path):
    r,*_=runmode(tmp_path,'nochange'); assert r['status']=='implementation_no_change'
def test_out_of_scope_change_fails_closed_and_is_preserved(tmp_path):
    r,c,l,s,*_=runmode(tmp_path,'out_of_scope'); assert r['status']=='implementation_scope_violated'; wt=Path(read_json(c.external_state_root/'maintenance_worktrees'/(s['session_id']+'.json'))['worktree_root']); assert (wt/'outside.txt').exists()
def test_file_and_line_budget_violations_fail_closed(tmp_path):
    r,*_=runmode(tmp_path/'a','many_files'); assert r['status'] in {'implementation_budget_exceeded','implementation_scope_violated'}
    r,*_=runmode(tmp_path/'b','many_lines'); assert r['status']=='implementation_budget_exceeded'
def test_success_records_implementation_completed_with_validation_pending(tmp_path):
    r,c,l,s,*_=runmode(tmp_path,'success'); assert r['validation_pending'] is True and r['measured_effect_flags']['validation_performed'] is False
def test_authentication_failure_is_classified_without_login(tmp_path):
    r,*_=runmode(tmp_path,'auth'); assert r['status']=='foreman_authentication_unavailable'
def test_timeout_terminates_fake_codex_child_and_grandchild(tmp_path):
    r,*_=runmode(tmp_path,'timeout'); assert r['status']=='implementation_timed_out'
def test_cancel_terminates_fake_codex_child_and_grandchild(tmp_path):
    cfg,lease,req,sess,art,*_=bundle(tmp_path,'timeout'); import threading
    t=threading.Thread(target=lambda: run_local_codex_session(cfg,lease,req,sess,art)); t.start(); time.sleep(.2); r=cancel_local_codex_session(cfg,lease['task_id'],sess['session_id']); t.join(3); assert r['status']=='implementation_cancelled'
