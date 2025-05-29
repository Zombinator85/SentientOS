import os
import sys
import importlib
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_env(tmp_path, monkeypatch, headless=True):
    monkeypatch.setenv("TRUST_DIR", str(tmp_path / "trust"))
    monkeypatch.setenv("GP_PLUGINS_DIR", "gp_plugins")
    if headless:
        monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    else:
        monkeypatch.delenv("SENTIENTOS_HEADLESS", raising=False)
    import trust_engine as te
    import plugin_framework as pf
    importlib.reload(te)
    importlib.reload(pf)
    pf.load_plugins()
    return pf, te


def test_wave_hand_headless(tmp_path, monkeypatch):
    pf, te = setup_env(tmp_path, monkeypatch, headless=True)
    assert "wave_hand" in pf.list_plugins()
    res = pf.run_plugin("wave_hand", {"speed": 2}, cause="unit")
    assert res.get("simulated")
    events = te.list_events(limit=1)
    assert events and events[0]["cause"] == "unit" and events[0]["data"]["headless"]


def test_wave_hand_real(tmp_path, monkeypatch):
    pf, te = setup_env(tmp_path, monkeypatch, headless=False)
    res = pf.run_plugin("wave_hand", {"speed": 1}, cause="real")
    assert not res.get("simulated")
    events = te.list_events(limit=1)
    assert events and not events[0]["data"]["headless"]


def test_enable_disable_reload(tmp_path, monkeypatch):
    pf, te = setup_env(tmp_path, monkeypatch)
    assert pf.plugin_status()["wave_hand"]
    pf.disable_plugin("wave_hand", user="test")
    assert not pf.plugin_status()["wave_hand"]
    with pytest.raises(ValueError):
        pf.run_plugin("wave_hand")
    pf.enable_plugin("wave_hand", user="test")
    pf.reload_plugins(user="test")
    res = pf.test_plugin("wave_hand")
    assert res.get("simulated")
    logs = te.list_events(limit=5)
    types = [e["type"] for e in logs]
    assert "plugin_enable" in types and "plugin_disable" in types and "plugin_reload" in types


def test_plugin_self_heal(tmp_path, monkeypatch):
    plugins_dir = tmp_path / "gp_plugins"
    plugins_dir.mkdir()
    failing = plugins_dir / "failer.py"
    failing.write_text("""from plugin_framework import BasePlugin\nclass F(BasePlugin):\n    def execute(self, event):\n        raise RuntimeError('boom')\n    def simulate(self, event):\n        raise RuntimeError('boom')\n\ndef register(r): r('failer', F())\n""", encoding='utf-8')
    monkeypatch.setenv("TRUST_DIR", str(tmp_path / "trust"))
    monkeypatch.setenv("GP_PLUGINS_DIR", str(plugins_dir))
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    import importlib
    import plugin_framework as pf
    import trust_engine as te
    importlib.reload(pf)
    importlib.reload(te)
    pf.load_plugins()
    res = pf.run_plugin('failer')
    assert 'error' in res
    health = pf.list_health()['failer']['status']
    assert health in {'reloaded', 'failed_reload', 'error'}
    assert not pf.plugin_status()['failer']
    events = te.list_events(limit=3)
    types = [e['type'] for e in events]
    assert 'plugin_error' in types and 'plugin_auto_disable' in types


def test_plugin_proposal_flow(tmp_path, monkeypatch):
    plugins_dir = tmp_path / "gp_plugins"
    plugins_dir.mkdir()
    sample = tmp_path / "sample.py"
    sample.write_text("""from plugin_framework import BasePlugin\nclass S(BasePlugin):\n    def execute(self,e):\n        return {'ok':True}\n    def simulate(self,e):\n        return {'ok':True}\n\ndef register(r): r('sample', S())\n""", encoding='utf-8')
    monkeypatch.setenv("TRUST_DIR", str(tmp_path / "trust"))
    monkeypatch.setenv("GP_PLUGINS_DIR", str(plugins_dir))
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    import importlib
    import plugin_framework as pf
    import trust_engine as te
    importlib.reload(pf)
    importlib.reload(te)
    pf.propose_plugin('sample', str(sample), user='model')
    prop = pf.list_proposals()['sample']
    assert prop['status'] == 'pending'
    pf.approve_proposal('sample', user='tester')
    assert 'sample' in pf.list_plugins()
    prop = pf.list_proposals()['sample']
    assert prop['status'] == 'installed'
    pf.propose_plugin('denyme', str(sample), user='model')
    pf.deny_proposal('denyme', user='tester')
    assert pf.list_proposals()['denyme']['status'] == 'denied'
