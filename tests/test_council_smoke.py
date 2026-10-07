"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations


from council.runner import run

def test_council_smoke():
    msgs = run("Seed", rounds=1)
    assert any("openai" in m.agent for m in msgs)
    assert any("deepseek" in m.agent for m in msgs)
    assert any("mistral" in m.agent for m in msgs)
