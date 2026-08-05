import pytest
pytestmark = pytest.mark.no_legacy_skip
import json, subprocess, sys
from pathlib import Path
from sentientos import maintenance_implementation_agent as mia
from tests.test_maintenance_implementation_agent_adapter import setup
NOW='2026-08-05T00:00:00+00:00'

def write(tmp_path, name, obj):
    p=tmp_path/name; p.write_text(json.dumps(obj)); return p

def run(args): return subprocess.run([sys.executable,'scripts/maintenance_implementation_agent.py',*args],cwd=Path.cwd(),text=True,capture_output=True)

def test_cli_start_poll_complete_round_trip(tmp_path):
    lease,req,drv,plan=setup(tmp_path); rp=write(tmp_path,'req.json',req); pp=write(tmp_path,'plan.json',plan)
    s=run(['start','--state-root',str(tmp_path),'--lease-id',lease['lease_id'],'--request',str(rp),'--fake-plan',str(pp),'--evaluation-time',NOW]); assert s.returncode==0, s.stderr+s.stdout
    sid=json.loads(s.stdout)['session_id']
    assert run(['poll','--state-root',str(tmp_path),'--task-id',lease['task_id'],'--session-id',sid,'--request',str(rp),'--fake-plan',str(pp),'--evaluation-time',NOW]).returncode==0
    c=run(['poll','--state-root',str(tmp_path),'--task-id',lease['task_id'],'--session-id',sid,'--request',str(rp),'--fake-plan',str(pp),'--evaluation-time',NOW]); assert json.loads(c.stdout)['status']=='agent_session_completed'

def test_cli_failure_timeout_and_cancel_results(tmp_path):
    lease,req,drv,plan=setup(tmp_path); fail=mia.seal_fake_plan([{'kind':'fail','progress_ordinal':1}], plan_id='fail'); rp=write(tmp_path,'req.json',req); pp=write(tmp_path,'fail.json',fail)
    s=run(['start','--state-root',str(tmp_path),'--lease-id',lease['lease_id'],'--request',str(rp),'--fake-plan',str(pp),'--evaluation-time',NOW]); sid=json.loads(s.stdout)['session_id']
    assert json.loads(run(['poll','--state-root',str(tmp_path),'--task-id',lease['task_id'],'--session-id',sid,'--request',str(rp),'--fake-plan',str(pp),'--evaluation-time',NOW]).stdout)['status']=='agent_session_failed'

def test_cli_invalid_request_returns_nonzero(tmp_path):
    p=write(tmp_path,'bad.json',{'schema_version':'bad'}); r=run(['verify-request','--request',str(p)]); assert r.returncode!=0
