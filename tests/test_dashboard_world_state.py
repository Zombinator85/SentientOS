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

def test_host_controlled_authorization_safety_dashboard_projection_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv('SENTIENTOS_DASHBOARD_TOKEN','t')
    path=tmp_path/'ws.json'
    path.write_text('{"facts":[{"subject":{"subject_id":"c1","subject_kind":"host_controlled_authorization_contract"},"disposition":"controlled_authorization_contract_incomplete","payload":{"blocked_actions":["host_mutation"],"missing_gates":["effect_receipt_required"]}},{"subject":{"subject_id":"g1","subject_kind":"host_actuation_safety_gate_assessment"},"disposition":"host_actuation_gate_missing","payload":{"blocked_actions":["fan_pwm_write"],"missing_gates":["effect_receipt_required"]}}],"summary":{"counts":{"staleness_posture":{"fresh":2}}}}', encoding='utf-8')
    monkeypatch.setenv('SENTIENTOS_WORLD_STATE_BOARD_PATH', str(path))
    c=app.test_client(); h={'Authorization':'Bearer t'}
    payload=c.get('/api/world-state/host-controlled-authorization-safety', headers=h).json()
    assert payload['read_only'] is True and payload['review_only'] is True
    assert payload['live_authorization_granted'] is False
    assert payload['execution_triggered'] is False
    assert 'effect_receipt_required' in payload['missing_gates']
    assert 'fan_pwm_write' in payload['blocked_actions']

def test_host_local_authorization_dashboard_projection_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv('SENTIENTOS_DASHBOARD_TOKEN','tok')
    path=tmp_path/'ws.json'
    path.write_text(json.dumps({'facts':[
        {'subject': {'subject_id':'req1','subject_kind':'host_local_authorization_review_request'}, 'payload': {'requested_scope':'future_cooling_scope','expiry':'2030','blocked_actions':['fan_pwm_write'], 'fulfillment_granted': False}},
        {'subject': {'subject_id':'op1','subject_kind':'host_local_authorization_operator_decision'}, 'payload': {'disposition':'approve'}},
        {'subject': {'subject_id':'pol1','subject_kind':'host_local_authorization_policy_decision'}, 'payload': {'disposition':'approve'}},
        {'subject': {'subject_id':'snap1','subject_kind':'host_local_authorization_ledger'}, 'payload': {'active_count':1,'expired_count':0,'revoked_count':0,'conflicted_count':0}},
    ], 'summary': {}}), encoding='utf-8')
    monkeypatch.setenv('SENTIENTOS_WORLD_STATE_BOARD_PATH', str(path))
    c=TestClient(app); h={'Authorization':'Bearer tok'}
    payload=c.get('/api/world-state/host-local-authorization', headers=h).json()
    assert payload['pending_review_request_count'] == 1
    assert payload['decision_counts']['approve'] == 2
    assert payload['grant_counts']['active'] == 1
    assert payload['read_only'] is True
    assert payload['local_authority_metadata_only'] is True
    assert payload['fulfillment_granted'] is False
    assert payload['execution_triggered'] is False
    assert payload['host_mutation_performed'] is False

def test_host_fulfillment_authorization_dashboard_projection_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv('SENTIENTOS_DASHBOARD_TOKEN','tok')
    path=tmp_path/'ws.json'
    path.write_text(json.dumps({'facts':[
        {'stage':'request','subject': {'subject_id':'env1','subject_kind':'host_fulfillment_authorization_request_envelope'}, 'payload': {'fulfillment_granted': False}},
        {'stage':'admission','disposition':'allow','subject': {'subject_id':'plan1','subject_kind':'host_fulfillment_authorization_consumption_admission'}, 'payload': {'outcome':'allow'}},
        {'stage':'receipt','disposition':'recorded','subject': {'subject_id':'rec1','subject_kind':'host_fulfillment_authorization_consumption_receipt'}, 'payload': {'effect_performed': False}},
    ], 'summary': {}}), encoding='utf-8')
    monkeypatch.setenv('SENTIENTOS_WORLD_STATE_BOARD_PATH', str(path))
    c=TestClient(app); h={'Authorization':'Bearer tok'}
    payload=c.get('/api/world-state/host-fulfillment-authorization', headers=h).json()
    assert payload['read_only'] is True
    assert payload['fact_count'] == 3
    assert payload['dedicated_metadata_consumption_admission_required'] is True
    assert payload['backend_invoked'] is False
    assert payload['execution_triggered'] is False
    assert payload['host_mutation_performed'] is False
