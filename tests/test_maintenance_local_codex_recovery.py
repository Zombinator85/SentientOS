import threading, pytest
from pathlib import Path
from sentientos.maintenance_local_codex_foreman import *
from tests.local_codex_foreman_fixtures import *
pytestmark=pytest.mark.no_legacy_skip
def bundle(tmp_path, mode='success'):
    repo,sha=make_repo(tmp_path); fake=make_fake_cli(tmp_path,mode); cfg=make_config(tmp_path,repo,fake,mode); lease=make_lease(sha); sess=make_session(lease); art=tmp_path/'art'; art.mkdir(); req=make_request(lease,art); return cfg,lease,req,sess,art
def test_interrupted_run_resumes_same_thread_and_attempt(tmp_path):
    cfg,lease,req,sess,art=bundle(tmp_path,'interrupt'); r=run_local_codex_session(cfg,lease,req,sess,art); assert r['codex_thread_id']=='thread-ok'; import os; os.environ['FAKE_CODEX_MODE']='success'; r2=resume_local_codex_session(cfg,lease,req,sess,art,'2026'); assert r2['status']=='implementation_ready_for_validation' and r2['codex_thread_id']=='thread-ok'
def test_recovery_without_thread_id_fails_closed(tmp_path):
    cfg,lease,req,sess,art=bundle(tmp_path); assert resume_local_codex_session(cfg,lease,req,sess,art,'2026')['status']=='foreman_recovery_unavailable'
def test_recovery_rejects_changed_worktree_or_expired_lease(tmp_path):
    cfg,lease,req,sess,art=bundle(tmp_path,'interrupt'); run_local_codex_session(cfg,lease,req,sess,art); assert resume_local_codex_session(cfg,{**lease,'expires_at':'2000'},req,sess,art,'2026')['status']=='foreman_recovery_unavailable'
def test_terminal_result_retry_is_idempotent(tmp_path):
    cfg,lease,req,sess,art=bundle(tmp_path,'success'); r=run_local_codex_session(cfg,lease,req,sess,art); r2=resume_local_codex_session(cfg,lease,req,sess,art,'2026'); assert r2['result_digest']==r['result_digest']
def test_process_concurrent_run_starts_one_foreman(tmp_path):
    cfg,lease,req,sess,art=bundle(tmp_path,'success'); outs=[]
    ts=[threading.Thread(target=lambda: outs.append(run_local_codex_session(cfg,lease,req,sess,art))) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]; assert len([o for o in outs if o.get('status')=='implementation_ready_for_validation'])==1 and any(o.get('status')=='foreman_process_conflict' for o in outs)
