"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()



import os
import sys
import importlib
import json
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def setup(tmp_path, monkeypatch, plugin_dir=None):
    monkeypatch.setenv("TRUST_DIR", str(tmp_path/"trust"))
    if plugin_dir is None:
        plugin_dir = "gp_plugins"
    monkeypatch.setenv("GP_PLUGINS_DIR", str(plugin_dir))
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
    client.post('/api/disable', json_body={'plugin':'wave_hand'})
    body = client.post('/api/plugins').data
    body = body if isinstance(body, str) else body.decode()
    data = json.loads(body)
    status = {p['id']:p['enabled'] for p in data}
    assert not status['wave_hand']
    client.post('/api/enable', json_body={'plugin':'wave_hand'})
    body = client.post('/api/plugins').data
    body = body if isinstance(body, str) else body.decode()
    data = json.loads(body)
    status = {p['id']:p['enabled'] for p in data}
    assert status['wave_hand']
    client.post('/api/test', json_body={'plugin':'wave_hand'})
    body = client.post('/api/logs').data
    body = body if isinstance(body, str) else body.decode()
    logs = json.loads(body)
    assert logs


def test_dashboard_health_and_proposals(tmp_path, monkeypatch):
    pd = setup(tmp_path, monkeypatch)
    pf = importlib.import_module("plugin_framework")
    class Bad(pf.BasePlugin):
        allowed_postures = ["normal"]
        requires_epoch = True
        capabilities = []
        def simulate(self, event, context=None):
            raise RuntimeError("x")
    pf.register_plugin("bad", Bad())
    pf.PLUGINS_INFO["bad"] = "internal test"
    client = pd.app.test_client()
    client.post("/api/test", json_body={"plugin": "bad"})
    assert "bad" in client.post("/api/health").get_json()
    sample = tmp_path / "samp.py"
    sample.write_text("raise AssertionError('must not execute')", encoding="utf-8")
    pf.propose_plugin("samp", str(sample), user="model")
    props = client.post("/api/proposals").get_json()
    assert any(item["name"] == "samp" for item in props)
    response = client.post("/api/approve", json_body={"name": "samp"})
    assert response.status_code == 409
    assert pf.list_proposals()["samp"]["status"] == "external_activation_unsupported"
