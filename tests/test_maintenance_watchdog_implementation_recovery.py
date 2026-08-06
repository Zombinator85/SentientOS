import json,os,pytest
from sentientos import maintenance_loop_watchdog as watchdog
from tests.maintenance_watchdog_implementation_fixtures import NOW,setup
pytestmark=pytest.mark.no_legacy_skip

def test_interrupted_session_recovers_same_attempt_session_worktree_and_thread(tmp_path):
    cfg,roots,_=setup(tmp_path,'interrupt'); os.environ['FAKE_CODEX_MODE']='interrupt'
    ticks=[watchdog.tick(cfg,evaluation_time=NOW) for _ in range(5)]
    interrupted=ticks[-1]['effect_result']; assert interrupted['status']=='implementation_interrupted'
    session=json.loads(next((roots['state']/'maintenance_agent_sessions').glob('*.json')).read_text())
    worktree_before=json.loads(next((roots['state']/'maintenance_worktrees').glob('*.json')).read_text())
    os.environ['FAKE_CODEX_MODE']='success'; recovered=watchdog.tick(cfg,evaluation_time=NOW)['effect_result']
    worktree_after=json.loads(next((roots['state']/'maintenance_worktrees').glob('*.json')).read_text())
    assert recovered['status']=='implementation_ready_for_validation'
    assert recovered['session_id']==session['session_id'] and recovered['codex_thread_id']==interrupted['codex_thread_id']=='thread-ok'
    assert worktree_after['worktree_digest']==worktree_before['worktree_digest']

def test_missing_recovery_thread_blocks_without_relaunch(tmp_path):
    cfg,roots,_=setup(tmp_path,'auth'); os.environ['FAKE_CODEX_MODE']='auth'
    [watchdog.tick(cfg,evaluation_time=NOW) for _ in range(5)]
    invocations=list((roots['state']/'maintenance_codex_invocations').glob('*.json'))
    result=watchdog.tick(cfg,evaluation_time=NOW)
    assert result['transition']=='recover_implementation' and result['effect_result']=={'status':'blocked','reason':'missing_codex_thread_id'}
    assert list((roots['state']/'maintenance_codex_invocations').glob('*.json'))==invocations
