"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
import random
import sys
from pathlib import Path
from typing import Optional

import emotion_fallback
import reasoning_engine as re
import pytest


async def model_a(msg: str) -> str:
    return msg + "1"


async def model_b(msg: str) -> str:
    return msg + "2"


def _flet_stub():
    import types

    class Dummy:
        def __init__(self, *a, **k):
            self.controls = []
            self.value = ""
        def update(self):
            pass
    canvas = types.SimpleNamespace(Canvas=Dummy, Circle=Dummy, Line=Dummy)
    stub = types.SimpleNamespace(
        UserControl=Dummy,
        ListView=Dummy,
        TextField=Dummy,
        Switch=Dummy,
        ElevatedButton=Dummy,
        Column=Dummy,
        Row=Dummy,
        Container=Dummy,
        ListTile=Dummy,
        Text=lambda v="": Dummy(),
        AlertDialog=Dummy,
        BarChart=Dummy,
        BarChartRod=Dummy,
        BarChartGroup=Dummy,
        colors=types.SimpleNamespace(GREY="grey"),
        canvas=canvas,
    )
    return stub


def test_fallback_ignored_when_preset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prof = Path("profiles/test")
    prof.mkdir(parents=True)
    (prof / "fallback_emotion.yaml").write_text("sad: 1.0\n")
    re.register_model("a", model_a)
    while not re.parliament_bus.empty():
        re.parliament_bus.get()
    amap = {"a": lambda: "joy"}
    asyncio.run(re.parliament("x", ["a"], profile="test", agent_emotion_map=amap))
    turn = re.parliament_bus.get()
    assert turn.emotion == "joy"


def test_fallback_deterministic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prof = Path("profiles/test")
    prof.mkdir(parents=True)
    (prof / "fallback_emotion.yaml").write_text("happy: 0.7\nangry: 0.3\n")
    re.register_model("a", model_a)
    while not re.parliament_bus.empty():
        re.parliament_bus.get()
    rng = random.Random(0)
    asyncio.run(re.parliament("m", ["a"], profile="test", rng=rng))
    turn = re.parliament_bus.get()
    assert turn.emotion == "angry"


def test_gui_observer(monkeypatch):
    monkeypatch.setitem(sys.modules, "flet", _flet_stub())
    import importlib
    panel_mod = importlib.reload(reasoning_panel)
    bus = panel_mod.ParliamentBus()
    panel = panel_mod.ReasoningPanel(bus)

    async def run() -> None:
        task = asyncio.create_task(panel.subscribe())
        await bus.publish({"turn_id": 1, "agent": "a", "timestamp": 0, "emotion": "joy"})
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    asyncio.run(run())
    assert panel.tone_heading.value == "Current Tone"
    assert panel.timeline.controls[0].trailing.value == "joy"
