"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio

import reasoning_engine as re
from reason_graph import build_graph


def _reg_models() -> None:
    re.MODEL_REGISTRY.clear()

    async def _a(msg: str) -> str:
        return msg + "a"

    async def _b(msg: str) -> str:
        return msg + "b"

    async def _c(msg: str) -> str:
        return msg + "c"

    re.register_model("a", _a)
    re.register_model("b", _b)
    re.register_model("c", _c)


def _collect_turns() -> list[re.Turn]:
    turns: list[re.Turn] = []
    while not re.parliament_bus.empty():
        turns.append(re.parliament_bus.get())
    return turns


def test_build_graph_cycles() -> None:
    _reg_models()
    while not re.parliament_bus.empty():
        re.parliament_bus.get()
    chain = ["a", "b", "c"] * 2
    asyncio.run(re.parliament("x", chain, profile="none"))
    turns = _collect_turns()
    g = build_graph(turns)
    assert g.number_of_nodes() == 3
    assert g.number_of_edges() == 6
