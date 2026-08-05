import pytest
pytestmark = pytest.mark.no_legacy_skip
from pathlib import Path
import json
import pytest
from sentientos import maintenance_implementation_agent as mia
from sentientos import maintenance_task_journal as mtj
from sentientos import maintenance_task_authority_lease as l
from tests.maintenance_lease_fixtures import admitted, NOW


def setup(tmp_path, auth=('code_edit','implementation_agent_session'), max_attempts=2):
    c,cs,sel,g,r=admitted(tmp_path, auth=auth, max_attempts=max_attempts)
    lease=r['lease']; plan=mia.seal_fake_plan([{'kind':'heartbeat','progress_ordinal':1},{'kind':'complete','progress_ordinal':2,'terminal_reason':'synthetic_complete','summary':'done'}])
    drv=mia.FakeScriptedDriver(plan)
    req=mia.seal_request({'request_id':'req1','task_id':lease['task_id'],'lease_id':lease['lease_id'],'lease_digest':lease['lease_digest'],'candidate_id':lease['candidate_id'],'candidate_revision_digest':lease['candidate_revision_digest'],'canonical_candidate_digest':lease['canonical_candidate_digest'],'admitted_scope_digest':lease['admitted_scope_digest'],'repository_identity':lease['repository_identity'],'base_sha':lease['base_sha'],'driver_id':'fake_scripted_default','driver_kind':'fake_scripted','attempt_ordinal':1,'corrective_retry_ordinal':0,'implementation_contract_digest':lease['candidate_revision_digest'],'bounded_objective':'bounded','subject_paths':list(lease['admitted_subject_paths']),'validation_expectations':list(lease['validation_expectations']),'requested_authority_classes':['implementation_agent_session'],'implementation_time_ceiling_seconds':1,'wall_clock_deadline':'2026-08-05T01:00:00+00:00','explicit_constraints':['metadata-only']})
    return lease,req,drv,plan

def test_request_digest_tampering_is_rejected(tmp_path):
    lease,req,drv,plan=setup(tmp_path); req['base_sha']='bad'
    with pytest.raises(ValueError): mia.verify_request(req)

def test_start_requires_active_matching_lease(tmp_path):
    lease,req,drv,plan=setup(tmp_path); req=mia.seal_request({**req,'lease_digest':'sha256:'+'0'*64})
    assert mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd())['status']=='agent_session_lease_invalid'

def test_start_requires_implementation_agent_session_authority(tmp_path):
    lease,req,drv,plan=setup(tmp_path, auth=('code_edit',));
    assert mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd())['status']=='agent_session_blocked'

def test_start_creates_one_attempt_and_one_session_binding(tmp_path):
    lease,req,drv,plan=setup(tmp_path); res=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd())
    assert res['status']=='agent_session_ready'; assert Path(res['session_path']).exists()
    ev=mtj.replay_journal(mtj.journal_path_for(tmp_path, lease['task_id'], repo_root=Path.cwd())).events
    assert [e.event_type for e in ev].count('attempt_started')==1 and [e.event_type for e in ev].count('agent_session_bound')==1

def test_exact_start_retry_is_idempotent(tmp_path):
    lease,req,drv,plan=setup(tmp_path); a=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); b=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd())
    assert b['status']=='agent_session_already_ready'; assert a['session_id']==b['session_id']

def test_later_attempt_requires_terminal_prior_attempt_and_remaining_budget(tmp_path):
    lease,req,drv,plan=setup(tmp_path, max_attempts=1); req2=mia.seal_request({**req,'request_id':'req2','attempt_ordinal':2})
    assert mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req2,driver=drv,evaluation_time=NOW,repo_root=Path.cwd())['status']=='agent_session_blocked'
