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
