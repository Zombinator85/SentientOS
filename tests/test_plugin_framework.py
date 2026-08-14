from __future__ import annotations

import importlib
import pytest


def setup_env(tmp_path, monkeypatch, headless=True):
    monkeypatch.setenv("TRUST_DIR", str(tmp_path / "trust"))
    if headless:
        monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    else:
        monkeypatch.delenv("SENTIENTOS_HEADLESS", raising=False)
    import trust_engine as te
    import plugin_framework as pf
    from resident_kernel import ResidentKernel
    importlib.reload(te); importlib.reload(pf)
    pf.initialize_plugins()
    kernel = ResidentKernel(); pf.set_kernel(kernel)
    return pf, te, kernel


def test_wave_hand_headless(tmp_path, monkeypatch):
    pf, te, kernel = setup_env(tmp_path, monkeypatch)
    assert "wave_hand" in pf.list_plugins()
    with kernel.begin_epoch("test"):
        result = pf.run_plugin("wave_hand", {"speed": 2}, cause="unit", kernel=kernel)
    assert result["simulated"] and result["gesture"] == "wave"
    assert te.list_events(limit=1)[0]["cause"] == "unit"


def test_wave_hand_real(tmp_path, monkeypatch):
    pf, _te, kernel = setup_env(tmp_path, monkeypatch, False)
    with kernel.begin_epoch("test"):
        result = pf.run_plugin("wave_hand", {"speed": 1}, kernel=kernel)
    assert result["gesture"] == "wave" and not result.get("simulated")


def test_enable_disable_reload(tmp_path, monkeypatch):
    pf, te, kernel = setup_env(tmp_path, monkeypatch)
    pf.disable_plugin("wave_hand", user="test")
    with pytest.raises(ValueError): pf.run_plugin("wave_hand", kernel=kernel)
    pf.reload_plugins(user="test")
    assert not pf.plugin_status()["wave_hand"]
    pf.enable_plugin("wave_hand", user="test")
    with kernel.begin_epoch("test"):
        assert pf.test_plugin("wave_hand", kernel=kernel)["simulated"]
    assert {e["type"] for e in te.list_events(limit=8)} >= {"plugin_enable", "plugin_disable", "plugin_reload"}


def test_plugin_self_heal_via_internal_registration(tmp_path, monkeypatch):
    pf, _te, kernel = setup_env(tmp_path, monkeypatch)
    class Failer(pf.BasePlugin):
        allowed_postures=["normal"]; requires_epoch=True; capabilities=[]
        def simulate(self, event, context=None): raise RuntimeError("boom")
    pf.register_plugin("failer", Failer()); pf.PLUGINS_INFO["failer"] = "test"
    with kernel.begin_epoch("test"):
        assert "error" in pf.run_plugin("failer", kernel=kernel)
    assert not pf.plugin_status()["failer"]


def test_plugin_cannot_bypass_admission(tmp_path, monkeypatch):
    pf, _te, kernel = setup_env(tmp_path, monkeypatch)
    import task_executor
    class Bypass(pf.BasePlugin):
        allowed_postures=["normal"]; requires_epoch=True; capabilities=[]
        def simulate(self, event, context=None):
            task=task_executor.Task(task_id="plugin-bypass", objective="bypass", steps=(task_executor.Step(step_id=1, kind="noop", payload=task_executor.NoopPayload()),))
            return task_executor.execute_task(task)
    pf.register_plugin("bypass", Bypass()); pf.PLUGINS_INFO["bypass"]="test"
    with kernel.begin_epoch("test"):
        result=pf.run_plugin("bypass", kernel=kernel)
    assert "MISSING_AUTHORIZATION" in result["error"]


def test_advisory_internal_plugin_does_not_trigger_task_execution(tmp_path, monkeypatch):
    pf, _te, kernel = setup_env(tmp_path, monkeypatch)
    import task_executor
    class Advisory(pf.BasePlugin):
        allowed_postures=["normal"]; requires_epoch=True; capabilities=[]
        def simulate(self, event, context=None): return {"advisory":"observe-only"}
    pf.register_plugin("advisory", Advisory()); pf.PLUGINS_INFO["advisory"]="test"
    monkeypatch.setattr(task_executor, "execute_task", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))
    with kernel.begin_epoch("test"):
        assert pf.run_plugin("advisory", kernel=kernel)["advisory"] == "observe-only"
