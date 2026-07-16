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
