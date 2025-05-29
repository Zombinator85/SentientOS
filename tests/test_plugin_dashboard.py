import os
import sys
import importlib
import json
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_DIR", str(tmp_path/"trust"))
    monkeypatch.setenv("GP_PLUGINS_DIR", "gp_plugins")
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    import plugin_framework as pf
    import plugin_dashboard as pd
    importlib.reload(pf)
    importlib.reload(pd)
    return pd

def test_dashboard_toggle(tmp_path, monkeypatch):
    pd = setup(tmp_path, monkeypatch)
    client = pd.app.test_client()
    res = client.post('/api/plugins')
    body = res.data if isinstance(res.data, str) else res.data.decode()
    data = json.loads(body)
    assert any(p['id']=='wave_hand' for p in data)
    client.post('/api/disable', json={'plugin':'wave_hand'})
    body = client.post('/api/plugins').data
    body = body if isinstance(body, str) else body.decode()
    data = json.loads(body)
    status = {p['id']:p['enabled'] for p in data}
    assert not status['wave_hand']
    client.post('/api/enable', json={'plugin':'wave_hand'})
    body = client.post('/api/plugins').data
    body = body if isinstance(body, str) else body.decode()
    data = json.loads(body)
    status = {p['id']:p['enabled'] for p in data}
    assert status['wave_hand']
    client.post('/api/test', json={'plugin':'wave_hand'})
    body = client.post('/api/logs').data
    body = body if isinstance(body, str) else body.decode()
    logs = json.loads(body)
    assert logs
