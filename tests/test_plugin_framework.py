import importlib


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
