import json, pytest
from sentientos import maintenance_loop_watchdog as watchdog
from tests.maintenance_watchdog_implementation_fixtures import NOW,setup
pytestmark=pytest.mark.no_legacy_skip

def admitted(tmp_path):
    cfg,roots,_=setup(tmp_path); watchdog.tick(cfg,evaluation_time=NOW); watchdog.tick(cfg,evaluation_time=NOW); return cfg,roots

def test_admitted_task_creates_exact_brief_and_request(tmp_path):
    cfg,roots=admitted(tmp_path); result=watchdog.tick(cfg,evaluation_time=NOW)
    assert result['transition']=='prepare_implementation' and result['status']=='implementation_prepared'
    brief=next((roots['state']/'maintenance_implementation_briefs').glob('*.json'))
    request=next((roots['state']/'maintenance_implementation_requests').glob('*.json'))
    assert json.loads(brief.read_text())['lease_digest']==json.loads(request.read_text())['lease_digest']
    instruction=next((roots['state']/'maintenance_implementation_instructions').glob('*.txt')).read_text()
    assert 'Do not commit, push, publish, access credentials, expand scope, or wait for hosted checks.' in instruction

def test_exact_preparation_retry_reuses_identical_artifacts(tmp_path):
    cfg,roots=admitted(tmp_path); watchdog.tick(cfg,evaluation_time=NOW)
    paths=list((roots['state']/'maintenance_implementation_briefs').glob('*'))+list((roots['state']/'maintenance_implementation_requests').glob('*'))+list((roots['state']/'maintenance_implementation_instructions').glob('*'))
    before={p:p.read_bytes() for p in paths}; scan=watchdog.scan(cfg,evaluation_time=NOW)
    watchdog._prepare_implementation(cfg,scan,NOW)
    assert before=={p:p.read_bytes() for p in paths}
