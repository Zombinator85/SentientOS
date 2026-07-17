import json
from apps.dashboard.main import app
from fastapi.testclient import TestClient

def test_world_state_dashboard_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv('SENTIENTOS_DASHBOARD_TOKEN','tok')
    p=tmp_path/'latest.json'; p.write_text(json.dumps({'summary':{},'entities':[{'subject':{'subject_id':'a'}}],'conflicts':[]}))
    monkeypatch.setenv('SENTIENTOS_WORLD_STATE_BOARD_PATH', str(p))
    c=TestClient(app); h={'Authorization':'Bearer tok'}
    assert c.get('/api/world-state', headers=h).status_code==200
    assert c.get('/api/world-state/entities/a', headers=h).status_code==200
    assert c.get('/api/world-state/conflicts', headers=h).json()['total']==0
    assert c.post('/api/world-state', headers=h).status_code in {404,405}


def test_host_execution_readiness_dashboard_projection_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv('SENTIENTOS_DASHBOARD_TOKEN','tok')
    p=tmp_path/'latest.json'
    p.write_text(json.dumps({
        'summary': {'counts': {'staleness_posture': {'fresh': 1}}},
        'entities': [],
        'conflicts': [],
        'facts': [
            {'subject': {'subject_id': 'erm_1', 'subject_kind': 'host_execution_readiness_manifest'}, 'payload': {'readiness_status': 'execution_readiness_incomplete', 'authorization_review_status': 'authorization_review_incomplete', 'effect_domain': 'filesystem', 'missing_gates': ['operator_approval_required'], 'blocked_actions': ['filesystem_cleanup'], 'findings': []}},
            {'subject': {'subject_id': 'noise', 'subject_kind': 'host_resource_snapshot'}, 'payload': {'readiness_status': 'ready'}},
        ],
    }, sort_keys=True))
    monkeypatch.setenv('SENTIENTOS_WORLD_STATE_BOARD_PATH', str(p))
    c=TestClient(app); h={'Authorization':'Bearer tok'}
    payload=c.get('/api/world-state/host-execution-readiness', headers=h).json()
    assert payload['status'] == 'recorded'
    assert payload['source_rehearsal_count'] == 1
    assert payload['read_only'] is True
    assert payload['review_only'] is True
    assert payload['authorization_granted'] is False
    assert payload['execution_triggered'] is False
    assert payload['host_mutation_performed'] is False
    assert payload['most_common_missing_proof_gates'] == ['operator_approval_required']
