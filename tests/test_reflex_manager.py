import importlib
import time

def test_on_demand_trigger(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import reflex_manager as rm
    import memory_manager as mm
    from api import actuator
    importlib.reload(mm)
    importlib.reload(actuator)
    importlib.reload(rm)
    calls = []

    def fake_act(intent, **kwargs):
        calls.append(intent)
        return {"ok": True}

    monkeypatch.setattr(actuator, "act", fake_act)
    trig = rm.OnDemandTrigger()
    rule = rm.ReflexRule(trig, [{"type": "shell", "cmd": "echo hi"}])
    mgr = rm.ReflexManager()
    mgr.add_rule(rule)
    mgr.start()
    trig.fire()
    time.sleep(0.05)
    mgr.stop()
    assert calls and calls[0]["cmd"] == "echo hi"

def test_load_rules(tmp_path):
    cfg = tmp_path / "r.json"
    cfg.write_text("[{\"trigger\":\"on_demand\",\"actions\":[{\"type\":\"shell\",\"cmd\":\"e\"}]}]")
    import reflex_manager as rm
    rules = rm.load_rules(str(cfg))
    assert rules and isinstance(rules[0].trigger, rm.OnDemandTrigger)
