import pytest
pytestmark = pytest.mark.no_legacy_skip
from pathlib import Path
import os,json,pytest
from sentientos import maintenance_implementation_agent as mia
from tests.test_maintenance_implementation_agent_adapter import setup
NOW='2026-08-05T00:00:00+00:00'

def test_interruption_after_descriptor_persistence_recovers_exact_session(tmp_path):
    lease,req,drv,plan=setup(tmp_path); a=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd(),interruption_point='after_descriptor_persistence'); b=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); assert a['session_id']==b['session_id']

def test_interruption_after_attempt_start_recovers_session_binding(tmp_path):
    lease,req,drv,plan=setup(tmp_path); a=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd(),interruption_point='after_attempt_started'); b=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); assert b['status'] in {'agent_session_already_ready','agent_session_recovered'}

def test_interruption_after_result_persistence_recovers_terminal_event(tmp_path):
    lease,req,drv,plan=setup(tmp_path); r=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); a=mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd(),interruption_point='after_result_persistence'); b=mia.poll_implementation_agent_session(state_root=tmp_path,task_id=lease['task_id'],session_id=r['session_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); assert b['status']=='agent_session_completed'

def test_conflicting_session_or_result_artifact_fails_closed(tmp_path):
    lease,req,drv,plan=setup(tmp_path); r=mia.start_implementation_agent_session(state_root=tmp_path,lease_id=lease['lease_id'],request=req,driver=drv,evaluation_time=NOW,repo_root=Path.cwd()); p=Path(r['session_path']); data=json.loads(p.read_text()); data['base_sha']='bad'; p.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        mia.inspect_session(state_root=tmp_path,session_id=r['session_id'],repo_root=Path.cwd())
