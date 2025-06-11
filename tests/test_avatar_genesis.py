"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import sys
import types
from pathlib import Path
import pytest


import avatar_genesis as ag


class DummyBpy(types.ModuleType):
    class ops:
        class wm:
            @staticmethod
            def read_factory_settings(use_empty: bool = True) -> None:
                pass

            @staticmethod
            def save_as_mainfile(filepath: str) -> None:
                Path(filepath).write_text("blend")

        class mesh:
            @staticmethod
            def primitive_uv_sphere_add(radius: int = 1) -> None:
                pass

    class data:
        class materials:
            materials_list = []

            @classmethod
            def new(cls, name: str):
                mat = types.SimpleNamespace(name=name, diffuse_color=None)
                cls.materials_list.append(mat)
                return mat

    class context:
        object = types.SimpleNamespace(name="", data=types.SimpleNamespace(materials=[]))


def test_generate_and_log(tmp_path, monkeypatch):
    log = tmp_path / "gen.jsonl"
    out = tmp_path / "a.blend"
    monkeypatch.setenv("AVATAR_GENESIS_LOG", str(log))
    monkeypatch.setenv("AVATAR_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "bpy", DummyBpy("bpy"))
    importlib.reload(ag)
    ag.generate_avatar("joy", out)
    ag._log_blessing("joy", out)
    assert out.exists()
    lines = log.read_text().splitlines()
    assert len(lines) == 1

