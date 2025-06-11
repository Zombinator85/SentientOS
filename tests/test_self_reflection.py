"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import memory_manager as mm
import notification
import self_patcher
from api import actuator
import self_reflection
from importlib import reload
import pytest


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    reload(mm)
    reload(notification)
    reload(self_patcher)
    reload(actuator)
    reload(self_reflection)


def test_reflection_on_patch(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    self_patcher.apply_patch("note", auto=False)
    mgr = self_reflection.SelfHealingManager()
    mgr.run_cycle()
    refls = mm.recent_reflections(limit=1, plugin="self_heal")
    assert refls and "Patch event" in refls[0]["reason"]


def test_reflection_on_failure(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    actuator.act({"type": "shell", "cmd": "ls"})  # not allowed -> failure
    mgr = self_reflection.SelfHealingManager()
    mgr.run_cycle()
    refls = mm.recent_reflections(limit=1, plugin="self_heal")
    notes = mm.recent_patches(limit=1)
    assert refls and refls[0]["reason"].startswith("Failure:")
    assert notes


def test_reflection_on_system_control(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    pol = tmp_path / "pol.yml"
    pol.write_text('{"policies":[{"conditions":{"event":"input.type_text"},"actions":[{"type":"deny"}]}]}')
    import importlib
    import policy_engine as pe
    import input_controller as ic
    importlib.reload(pe)
    importlib.reload(ic)
    engine = pe.PolicyEngine(str(pol))
    ctrl = ic.InputController(policy_engine=engine)
    with pytest.raises(PermissionError):
        ctrl.type_text("hi")
    mgr = self_reflection.SelfHealingManager()
    mgr.run_cycle()
    refls = mm.recent_reflections(limit=1, plugin="self_heal")
    assert refls and refls[0]["next"] == "undo"
