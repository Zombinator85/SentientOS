"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import prompt_assembler as pa
import user_profile as up
import memory_manager as mm


def test_assemble_prompt_includes_profile_and_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    # reload modules with new env
    from importlib import reload
    reload(up)
    reload(mm)
    reload(pa)

    up.update_profile(name="Allen")
    mm.append_memory("Allen likes cats", tags=["test"], source="unit")

    prompt = pa.assemble_prompt("cats", [])
    assert "Allen likes cats" in prompt
    assert "name: Allen" in prompt


def test_prompt_includes_reflection(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    reload(up)
    reload(mm)
    reload(pa)
    from api import actuator
    actuator.WHITELIST = {"shell": ["echo"], "http": [], "timeout": 5}
    actuator.act({"type": "shell", "cmd": "echo hi"})
    prompt = pa.assemble_prompt("hi", [])
    assert "ACTION FEEDBACK" in prompt
