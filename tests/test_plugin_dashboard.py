from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
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


def test_dashboard_health_and_proposals(tmp_path, monkeypatch):
    plugins = tmp_path / 'gp_plugins'
    plugins.mkdir()
    failing = plugins / 'bad.py'
    failing.write_text("""from plugin_framework import BasePlugin\nclass B(BasePlugin):\n    def execute(self,e): raise RuntimeError('x')\n    def simulate(self,e): raise RuntimeError('x')\n\ndef register(r): r('bad', B())\n""", encoding='utf-8')
    pd = setup(tmp_path, monkeypatch, plugins)
    client = pd.app.test_client()
    client.post('/api/plugins')
    client.post('/api/test', json={'plugin':'bad'})
    res = client.post('/api/health')
    data = json.loads(res.data if isinstance(res.data, str) else res.data.decode())
    assert 'bad' in data
    pd_cli = pd.app.test_client()
    sample = tmp_path / 'samp.py'
    sample.write_text("""from plugin_framework import BasePlugin\nclass S(BasePlugin):\n    def execute(self,e): return {'ok':True}\n    def simulate(self,e): return {'ok':True}\n\ndef register(r): r('samp', S())\n""", encoding='utf-8')
    pf = importlib.import_module('plugin_framework')
    pf.propose_plugin('samp', str(sample), user='model')
    res = pd_cli.post('/api/proposals')
    props = json.loads(res.data if isinstance(res.data, str) else res.data.decode())
    assert any(p['name']=='samp' for p in props)
