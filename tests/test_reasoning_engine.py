from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations

import asyncio
import os
from queue import SimpleQueue

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
