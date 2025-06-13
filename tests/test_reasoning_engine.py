from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
import os
from queue import SimpleQueue
import random
from pathlib import Path
import emotion_fallback

import reasoning_engine as re


async def model_a(msg: str) -> str:
    return msg + "1"


async def model_b(msg: str) -> str:
    return msg + "2"


def test_parliament(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    re.register_model("a", model_a)
    re.register_model("b", model_b)
    # clear bus
    while not re.parliament_bus.empty():
        re.parliament_bus.get()
    result = asyncio.run(re.parliament("a", ["a", "b"], cycles=2))
    turns = []
    while not re.parliament_bus.empty():
        turns.append(re.parliament_bus.get())
    assert result == "a1212"
    assert len(turns) == 4
    assert turns[0].model == "a" and turns[0].reply == "a1"
    assert turns[-1].model == "b" and turns[-1].reply == "a1212"


def test_persona_emotion(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    cfg_dir = tmp_path / "profiles" / "test"
    cfg_dir.mkdir(parents=True)
    cfg = cfg_dir / "fallback_emotion.yaml"
    cfg.write_text("joy: 1.0\n")
    re.register_model("a", model_a)
    while not re.parliament_bus.empty():
        re.parliament_bus.get()
    rng = random.Random(0)
    asyncio.run(
        re.parliament(
            "x",
            ["a"],
            cycles=1,
            profile="test",
            agent_emotion_map=None,
            rng=rng,
        )
    )
    turn = re.parliament_bus.get()
    assert turn.emotion == "joy"
