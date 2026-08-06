import json,os,pytest
from sentientos import maintenance_loop_watchdog as watchdog
from scripts.maintenance_loop_watchdog import main
from tests.maintenance_watchdog_implementation_fixtures import NOW,setup
pytestmark=pytest.mark.no_legacy_skip

def advance(cfg,count): return [watchdog.tick(cfg,evaluation_time=NOW) for _ in range(count)]

def test_watchdog_starts_existing_local_codex_driver_once(tmp_path):
    cfg,roots,_=setup(tmp_path); ticks=advance(cfg,4)
    assert ticks[-1]['transition']=='start_implementation'
    assert len(list((roots['state']/'maintenance_agent_sessions').glob('*.json')))==1

def test_active_session_is_observed_without_duplicate_process(tmp_path):
    cfg,roots,_=setup(tmp_path); advance(cfg,4); result=watchdog.tick(cfg,evaluation_time=NOW)
    assert result['transition']=='observe_process'
    assert len(list((roots['state']/'maintenance_agent_sessions').glob('*.json')))==1
    assert len(list((roots['state']/'maintenance_codex_invocations').glob('*.json')))==1

def test_process_real_fake_codex_reaches_implementation_ready_for_validation(tmp_path):
    cfg,roots,_=setup(tmp_path); ticks=advance(cfg,5)
    result=ticks[-1]['effect_result']
    assert result['status']=='implementation_ready_for_validation' and result['codex_thread_id']=='thread-ok'
    assert result['changed_paths']==['allowed.txt']

def test_production_cli_run_bounded_stops_at_implementation_ready_for_validation(tmp_path,capsys):
    cfg,roots,_=setup(tmp_path); path=tmp_path/'watchdog.json'; path.write_text(json.dumps(cfg,sort_keys=True))
    os.environ['FAKE_CODEX_MODE']='success'
    assert main(['--config',str(path),'--evaluation-time',NOW,'run-bounded'])==0
    result=json.loads(capsys.readouterr().out)
    assert [t['transition'] for t in result['ticks']]==['select_candidate','admit_candidate','prepare_implementation','start_implementation','observe_process','validate']
    assert result['ticks'][-2]['effect_result']['status']=='implementation_ready_for_validation'
    assert result['ticks'][-1]['effect_result']['reason']=='canonical_component_state_not_ready'
