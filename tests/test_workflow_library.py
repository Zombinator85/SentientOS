"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
import importlib
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import workflow_controller as wc
import workflow_library as wl
import memory_manager as mm


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path / "mem"))
    monkeypatch.setenv("ACT_SANDBOX", str(tmp_path / "sb"))
    global mm
    import memory_manager as _mm
    importlib.reload(_mm)
    mm = _mm
    import api.actuator as act
    importlib.reload(act)
    importlib.reload(wc)
    importlib.reload(wl)
    wl.LIB_DIR = tmp_path / "lib"
    wl.LIB_DIR.mkdir()


def test_template_load_and_run(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    tpl = wl.LIB_DIR / "demo.json"
    tpl.write_text(
        json.dumps(
            {
                "name": "greet_user",
                "steps": [
                    {
                        "name": "write",
                        "action": "api.actuator.file_write",
                        "params": {"path": "{file}", "content": "hi {user}"},
                        "undo": "api.actuator.file_write",
                        "undo_params": {"path": "{file}", "content": ""},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    wl.load_template("demo", params={"file": "o.txt", "user": "Ada"})
    assert wc.run_workflow("greet_user")
    out = tmp_path / "sb" / "o.txt"
    assert out.exists() and out.read_text() == "hi Ada"


def test_auto_heal(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    mod = tmp_path / "failer.py"
    mod.write_text(
        """
import json

def act():
    raise RuntimeError('boom')

def undo():
    pass
""",
        encoding="utf-8",
    )
    tpl = wl.LIB_DIR / "fail.json"
    tpl.write_text(
        json.dumps(
            {
                "name": "fail",
                "steps": [
                    {"name": "bad", "action": "failer.act", "undo": "failer.undo"}
                ],
            }
        ),
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    wl.load_template("fail")
    for _ in range(3):
        wc.run_workflow("fail")
    import self_reflection as sr
    importlib.reload(sr)
    mgr = sr.SelfHealingManager()
    mgr.run_cycle()
    data = tpl.read_text()
    assert "skip" in data
    refls = mm.recent_reflections(limit=1, plugin="self_heal")
    assert refls
