"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

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


def test_apply_analytics(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import reflex_manager as rm
    import workflow_controller as wc
    import workflow_analytics as wa
    importlib.reload(rm)
    importlib.reload(wc)
    importlib.reload(wa)

    steps = [{"name": "s1", "action": lambda: (_ for _ in ()).throw(RuntimeError("x"))}]
    wc.register_workflow("bad", steps)
    for _ in range(3):
        try:
            wc.run_workflow("bad")
        except Exception:
            pass
    data = wa.analytics()
    mgr = rm.ReflexManager()
    mgr.apply_analytics(data)
    assert any(r.name == "retry_bad" for r in mgr.rules)


def test_audit_attribution_and_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLEX_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    import reflex_manager as rm
    import importlib

    importlib.reload(rm)
    rule = rm.ReflexRule(rm.OnDemandTrigger(), [], name="multi")
    mgr = rm.ReflexManager()
    mgr.add_rule(rule)
    import final_approval
    monkeypatch.setattr(final_approval, "request_approval", lambda d: True)
    mgr.promote_rule("multi", by="alice", persona="P", policy="pol1", reviewer="bob")
    entries = mgr.get_audit("multi", agent="alice")
    assert entries and entries[-1]["persona"] == "P"
    assert entries[-1]["policy"] == "pol1"
    assert entries[-1]["reviewer"] == "bob"
