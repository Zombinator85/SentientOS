"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


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


def test_plan_order_ignores_affect_metadata(monkeypatch):
    from importlib import reload

    reload(pa)
    monkeypatch.setattr(pa.up, "format_profile", lambda: "")
    monkeypatch.setattr(pa.em, "average_emotion", lambda: {})
    monkeypatch.setattr(pa.cw, "get_context", lambda: ([], ""))
    monkeypatch.setattr(pa.actuator, "recent_logs", lambda *args, **kwargs: [])

    plans_with_affect = [
        {"plan": "alpha", "affect": "calm", "tone": "soft"},
        {"plan": "beta", "presentation": "flowery"},
    ]

    monkeypatch.setattr(pa.mm, "get_context", lambda _query, k=6: plans_with_affect)
    prompt_with_affect = pa.assemble_prompt("run plan", [])

    monkeypatch.setattr(pa.mm, "get_context", lambda _query, k=6: [{"plan": "alpha"}, {"plan": "beta"}])
    prompt_without_affect = pa.assemble_prompt("run plan", [])

    assert prompt_with_affect == prompt_without_affect
    assert "affect" not in prompt_with_affect
    assert "tone" not in prompt_with_affect
    assert "presentation" not in prompt_with_affect


def test_prompt_inputs_repeat_without_leak(monkeypatch):
    from importlib import reload

    reload(pa)

    monkeypatch.setattr(pa.up, "format_profile", lambda: "name: Allen")
    monkeypatch.setattr(pa.em, "average_emotion", lambda: {})
    monkeypatch.setattr(pa.cw, "get_context", lambda: (["msg-1"], "summary"))
    monkeypatch.setattr(pa.actuator, "recent_logs", lambda *args, **kwargs: [])

    calls: list[list[dict[str, object]]] = []

    def deterministic_context(_query, k=6):
        payload = [{"plan": "alpha", "affect": "calm"}, {"plan": "beta", "text": "delta"}]
        calls.append(payload)
        return payload

    monkeypatch.setattr(pa.mm, "get_context", deterministic_context)

    first = pa.assemble_prompt("reflect", ["hi"], k=2)
    second = pa.assemble_prompt("reflect", ["hi"], k=2)

    assert first == second
    assert calls[0] == calls[1]
