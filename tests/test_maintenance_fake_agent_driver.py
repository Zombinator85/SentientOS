import pytest
pytestmark = pytest.mark.no_legacy_skip
from pathlib import Path
import pytest
from sentientos import maintenance_implementation_agent as mia
from tests.test_maintenance_implementation_agent_adapter import setup
NOW='2026-08-05T00:00:00+00:00'

def start(tmp_path, plan=None):
    lease,req,drv,p=setup(tmp_path); drv=mia.FakeScriptedDriver(plan or p); r=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); return lease,req,drv,r

def test_fake_plan_is_closed_bounded_and_deterministic():
    p=mia.seal_fake_plan([{'kind':'heartbeat','progress_ordinal':1},{'kind':'complete','progress_ordinal':2}]); assert mia.validate_fake_plan(p)['plan_digest']==p['plan_digest']
    with pytest.raises(ValueError): mia.validate_fake_plan({'schema_version':mia.FAKE_PLAN_SCHEMA,'steps':[{'kind':'sleep'}]})

def test_fake_driver_emits_one_step_per_explicit_poll(tmp_path):
    lease,req,drv,r=start(tmp_path); a=mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); assert a['status']=='agent_session_running'

def test_fake_completion_reports_synthetic_no_effect(tmp_path):
    lease,req,drv,r=start(tmp_path); mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); out=mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); result=mia.inspect_result(state_root=tmp_path,session_id=r['session_id'],repo_root=Path.cwd()); assert result['effect_class']=='synthetic_no_effect' and not result['repository_mutation_performed'] and out['status']=='agent_session_completed'

def test_fake_failure_binds_immutable_result(tmp_path):
    plan=mia.seal_fake_plan([{'kind':'fail','progress_ordinal':1,'terminal_reason':'synthetic_fail'}]); lease,req,drv,r=start(tmp_path,plan); out=mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); assert out['status']=='agent_session_failed'; assert mia.inspect_result(state_root=tmp_path,session_id=r['session_id'],repo_root=Path.cwd())['terminal_event_type']=='implementation_failed'

def test_explicit_evaluation_time_produces_deterministic_timeout(tmp_path):
    lease,req,drv,r=start(tmp_path); out=mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time='2026-08-06T00:00:00+00:00',repo_root=Path.cwd()); assert out['status']=='agent_session_timed_out'

def test_cancel_is_idempotent_and_does_not_revoke_lease(tmp_path):
    lease,req,drv,r=start(tmp_path); a=mia.cancel_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,cancellation_reference='op:cancel',repo_root=Path.cwd()); b=mia.cancel_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,cancellation_reference='op:cancel',repo_root=Path.cwd()); assert a['status']=='agent_session_cancelled' and b['status']=='agent_session_already_terminal'
