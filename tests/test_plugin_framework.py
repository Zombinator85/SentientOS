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
