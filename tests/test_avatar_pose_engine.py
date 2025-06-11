"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import importlib
import importlib
import sys
import types
import json
from pathlib import Path

import sentientos.avatar_pose_engine as ape


class DummyBpy(types.ModuleType):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.context = types.SimpleNamespace(object=types.SimpleNamespace(name="rig", pose_marker=""))
        class WM:
            def __init__(self, outer):
                self.outer = outer
            def open_mainfile(self, filepath: str) -> None:
                self.outer.context.object.path = filepath
            def save_as_mainfile(self, filepath: str) -> None:
                Path(filepath).write_text("blend")
        self.ops = types.SimpleNamespace(wm=WM(self))


def test_set_pose_with_bpy(tmp_path, monkeypatch):
    log = tmp_path / "pose.jsonl"
    monkeypatch.setitem(sys.modules, "bpy", DummyBpy("bpy"))
    importlib.reload(ape)
    monkeypatch.setattr(ape, "LOG_PATH", log)
    ape.set_pose("a.blend", "wave")
    assert log.exists()
    entry = json.loads(log.read_text())
    assert entry["pose"] == "wave"
    assert ape.bpy.context.object.pose_marker == "wave"


def test_set_pose_no_bpy(tmp_path, monkeypatch):
    log = tmp_path / "pose.jsonl"
    monkeypatch.setitem(sys.modules, "bpy", None)
    importlib.reload(ape)
    monkeypatch.setattr(ape, "LOG_PATH", log)
    res = ape.set_pose("a.blend", "wave")
    assert res["context"].get("note")
    assert log.exists()

