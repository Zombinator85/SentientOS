import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import autonomous_reflector as ar
import memory_manager as mm
from api import actuator
from importlib import reload


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("ACT_PLUGINS_DIR", "plugins")
    reload(mm)
    reload(actuator)
    reload(ar)


def test_micro_agent_completes_goal(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    mm.add_goal("say hi", intent={"type": "hello", "name": "Ada"})
    ar.run_loop(interval=0.01, iterations=1)
    goals = mm.get_goals(open_only=False)
    assert goals and goals[0]["status"] == "completed"
    refl = mm.recent_reflections(limit=1)
    assert refl


def test_micro_agent_escalation(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    mm.add_goal("fail", intent={"type": "shell", "cmd": "rm"})
    ar.run_loop(interval=0.01, iterations=3)
    goal = mm.get_goals(open_only=False)[0]
    assert goal["status"] == "stuck"
    assert goal.get("failure_count", 0) >= 3
    esc = mm.recent_escalations(limit=1)
    assert esc


def test_multi_goal_priority(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    mm.add_goal("low", intent={"type": "hello", "name": "Low"}, priority=1)
    mm.add_goal("high", intent={"type": "hello", "name": "High"}, priority=5)
    ar.run_loop(interval=0.01, iterations=1)
    goals = mm.get_goals(open_only=False)
    assert any(g["text"] == "high" and g["status"] == "completed" for g in goals)
    open_goals = [g for g in goals if g["status"] == "open"]
    assert open_goals and open_goals[0]["text"] == "low"


def test_self_patch_created(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    actuator.WHITELIST = {"shell": [], "http": [], "timeout": 5}
    mm.add_goal("fail", intent={"type": "shell", "cmd": "rm"})
    ar.run_loop(interval=0.01, iterations=1)
    patches = mm.recent_patches(limit=1)
    assert patches
