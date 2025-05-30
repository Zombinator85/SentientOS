import os
import sys
import json
import importlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import reflex_manager as rm
import reflection_stream as rs


def test_ab_autopromotion(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLEX_EXPERIMENTS", str(tmp_path / "exp.json"))
    monkeypatch.setenv("REFLECTION_DIR", str(tmp_path / "logs"))
    importlib.reload(rs)
    importlib.reload(rm)

    rule_a = rm.ReflexRule(rm.OnDemandTrigger(), [], name="A")
    rule_b = rm.ReflexRule(rm.OnDemandTrigger(), [], name="B")
    mgr = rm.ReflexManager(autopromote_trials=1)
    mgr.add_rule(rule_a)
    mgr.add_rule(rule_b)
    mgr.ab_test(rule_a, rule_b)

    exp = json.loads((tmp_path / "exp.json").read_text())
    assert "A_vs_B" in exp
    logs = rs.recent_reflex_learn(3)
    assert any("promotion" in l["data"] for l in logs)


def test_manual_promotion(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLEX_EXPERIMENTS", str(tmp_path / "exp.json"))
    monkeypatch.setenv("REFLECTION_DIR", str(tmp_path / "logs"))
    importlib.reload(rs)
    importlib.reload(rm)

    rule = rm.ReflexRule(rm.OnDemandTrigger(), [], name="X")
    mgr = rm.ReflexManager()
    mgr.add_rule(rule)
    mgr.promote_rule("X", by="alice")
    assert rule.status == "preferred"
    logs = rs.recent_reflex_learn(1)
    assert logs and logs[0]["data"]["by"] == "alice"


def test_dashboard_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REFLEX_EXPERIMENTS", str(tmp_path / "exp.json"))
    (tmp_path / "exp.json").write_text(json.dumps({"exp": {"rules": {}}}))
    import reflex_dashboard as rd
    import reflex_manager as rm
    importlib.reload(rm)
    importlib.reload(rd)
    rd.st = None
    monkeypatch.setattr(sys, "argv", ["rd", "--log", "0", "--list-experiments"])
    rd.run_dashboard()
    out = capsys.readouterr().out
    assert "exp" in out


def test_trial_autopromotion_and_demote(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REFLEX_EXPERIMENTS", str(tmp_path / "exp.json"))
    monkeypatch.setenv("REFLECTION_DIR", str(tmp_path / "logs"))
    import reflex_manager as rm
    import reflection_stream as rs
    from api import actuator
    import importlib
    importlib.reload(rs)
    importlib.reload(rm)
    importlib.reload(actuator)

    monkeypatch.setattr(actuator, "act", lambda *a, **k: None)
    rule = rm.ReflexRule(rm.OnDemandTrigger(), [{"type": "shell"}], name="T")
    mgr = rm.ReflexManager(autopromote_trials=1)
    mgr.add_rule(rule)
    rule.execute()
    assert rule.status == "preferred"

    def fail(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(actuator, "act", fail)
    rule.execute()
    assert rule.status == "inactive"

    import reflex_dashboard as rd
    importlib.reload(rd)
    rd.st = None
    monkeypatch.setattr(sys, "argv", ["rd", "--history", "T"])
    rd.run_dashboard()
    hist_out = capsys.readouterr().out
    assert "\"rule\": \"T\"" in hist_out


def test_cli_demote(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REFLEX_EXPERIMENTS", str(tmp_path / "exp.json"))
    (tmp_path / "exp.json").write_text(json.dumps({"exp": {"rules": {}}}))
    import reflex_dashboard as rd
    import reflex_manager as rm
    importlib.reload(rm)
    importlib.reload(rd)
    rd.st = None
    called = {}

    def fake_demote(self, name, by="system", experiment=None):
        called["name"] = name

    monkeypatch.setattr(rm.ReflexManager, "demote_rule", fake_demote)
    monkeypatch.setattr(sys, "argv", ["rd", "--demote", "exp"])
    rd.run_dashboard()
    assert called.get("name") == "exp"


def test_annotation_and_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLEX_EXPERIMENTS", str(tmp_path / "exp.json"))
    monkeypatch.setenv("REFLEX_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    importlib.reload(rm)

    rule = rm.ReflexRule(rm.OnDemandTrigger(), [], name="ann")
    mgr = rm.ReflexManager()
    mgr.add_rule(rule)
    mgr.annotate("ann", "check", tags=["needs review"], by="bob")
    audit = mgr.get_audit("ann")
    assert audit and audit[-1]["action"] == "annotate"
    mgr.promote_rule("ann", by="bob")
    mgr.revert_rule("ann")
    trail = mgr.get_audit("ann")
    assert any(e["action"] == "manual_revert" for e in trail)


def test_workflow_reflex_audit_link(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("REFLEX_EXPERIMENTS", str(tmp_path / "exp.json"))
    monkeypatch.setenv("REFLEX_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    import workflow_controller as wc
    importlib.reload(wc)
    importlib.reload(rm)
    from api import actuator
    import importlib as il
    il.reload(actuator)

    mgr = rm.ReflexManager(autopromote_trials=1)
    rm.set_default_manager(mgr)
    rule = rm.ReflexRule(rm.OnDemandTrigger(), [{"type": "shell"}], name="link")
    mgr.add_rule(rule)
    monkeypatch.setattr(actuator, "act", lambda *a, **k: None)
    steps = [{"name": "trial", "action": "run:reflex", "params": {"rule": "link"}}]
    wc.register_workflow("wfl", steps)
    assert wc.run_workflow("wfl")
    events = (tmp_path / "events.jsonl").read_text().splitlines()
    assert any('"workflow.reflex"' in ev and '"review"' in ev for ev in events)


def test_workflow_triggered_trials(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REFLEX_EXPERIMENTS", str(tmp_path / "exp.json"))
    monkeypatch.setenv("REFLECTION_DIR", str(tmp_path / "logs"))
    import reflex_manager as rm
    import workflow_controller as wc
    from api import actuator
    import importlib

    importlib.reload(rm)
    importlib.reload(wc)
    importlib.reload(actuator)

    mgr = rm.ReflexManager(autopromote_trials=1)
    rm.set_default_manager(mgr)
    rule = rm.ReflexRule(rm.OnDemandTrigger(), [{"type": "shell"}], name="wtest")
    mgr.add_rule(rule)

    monkeypatch.setattr(actuator, "act", lambda *a, **k: None)
    steps = [{"name": "trial", "action": "run:reflex", "params": {"rule": "wtest"}}]
    wc.register_workflow("demo_reflex", steps)
    assert wc.run_workflow("demo_reflex")
    assert steps[0].get("reflex_status") == "preferred"

    def fail(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(actuator, "act", fail)
    wc.run_workflow("demo_reflex")
    assert steps[0].get("reflex_status") == "inactive"

    import reflex_dashboard as rd
    importlib.reload(rd)
    rd.st = None
    monkeypatch.setattr(sys, "argv", ["rd", "--list-experiments"])
    rd.run_dashboard()
    out = capsys.readouterr().out
    assert "wtest" in out

    # experiment history should be recorded and viewable via CLI
    monkeypatch.setattr(sys, "argv", ["rd", "--history", "wtest"])
    rd.run_dashboard()
    hist_out = capsys.readouterr().out
    assert "\"rule\": \"wtest\"" in hist_out

    exp = json.loads((tmp_path / "exp.json").read_text())
    assert exp.get("wtest", {}).get("history")

