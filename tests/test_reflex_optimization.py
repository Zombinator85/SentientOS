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
    monkeypatch.setattr(sys, "argv", ["rd", "--log", "0"])
    rd.run_dashboard()
    out = capsys.readouterr().out
    assert "exp" in out

