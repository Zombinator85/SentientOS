import pytest
pytestmark = pytest.mark.no_legacy_skip
from pathlib import Path
from multiprocessing import Process, Queue
from sentientos import maintenance_implementation_agent as mia
from sentientos import maintenance_task_journal as mtj
from tests.test_maintenance_implementation_agent_adapter import setup
NOW='2026-08-05T00:00:00+00:00'

def started(tmp_path):
    lease,req,drv,plan=setup(tmp_path); r=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); return lease,req,drv,r

def test_heartbeat_is_idempotent_and_bound_to_session(tmp_path):
    lease,req,drv,r=started(tmp_path); a=mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); b=mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); assert a['session_id']==r['session_id']; assert b['status']=='agent_session_completed'

def test_terminal_event_binds_exact_result_digest(tmp_path):
    lease,req,drv,r=started(tmp_path); mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); out=mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); result=mia.inspect_result(state_root=tmp_path,session_id=r['session_id'],repo_root=Path.cwd()); ev=mtj.replay_journal(mtj.journal_path_for(tmp_path,lease['task_id'],repo_root=Path.cwd())).events; term=[e for e in ev if e.event_type=='implementation_completed'][0]; assert term.payload['result_digest']==result['result_digest']

def test_terminal_session_cannot_receive_more_heartbeats(tmp_path):
    lease,req,drv,r=started(tmp_path); mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); assert mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd())['status']=='agent_session_already_terminal'

def _worker(root, lease, req, plan, q):
    
    try:
        d=mia.FakeScriptedDriver(plan); q.put(mia.start_implementation_agent_session(state_root=root,lease_id=lease['lease_id'],request=req,driver=d,evaluation_time=NOW,repo_root=Path.cwd()))
    except Exception as e:
        q.put({'status':'agent_session_conflict','reason_codes':(str(e),)})

def test_process_concurrent_start_converges_on_one_session(tmp_path):
    lease,req,drv,plan=setup(tmp_path); q=Queue(); ps=[Process(target=_worker,args=(str(tmp_path),lease,req,plan,q)) for _ in range(2)]
    [p.start() for p in ps]; [p.join() for p in ps]; res=[q.get() for _ in ps]; assert len({r['session_id'] for r in res})==1; assert len(list((tmp_path/'maintenance_agent_sessions').glob('*.json')))==1

def test_process_conflicting_fake_plans_have_one_winner(tmp_path):
    lease,req,drv,plan=setup(tmp_path); q=Queue(); p2=mia.seal_fake_plan([{'kind':'fail','progress_ordinal':1}], plan_id='other'); ps=[Process(target=_worker,args=(str(tmp_path),lease,req,pl,q)) for pl in (plan,p2)]
    [p.start() for p in ps]; [p.join() for p in ps]; res=[q.get() for _ in ps]; assert sum(1 for r in res if r['status'] in {'agent_session_ready','agent_session_already_ready'})==1
