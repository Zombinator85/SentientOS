"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import types
import importlib

import gui.cathedral_gui as cg
import profile_manager as pm


def test_save_triggers_profile_switch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = tmp_path / ".env"

    importlib.reload(cg)
    monkeypatch.setattr(cg, "ENV_PATH", env, raising=False)
    monkeypatch.setitem(cg.__dict__, "END", "end")
    monkeypatch.setattr(cg, "messagebox", types.SimpleNamespace(showerror=lambda *a, **k: None))

    called = {}

    def _switch(name: str) -> None:
        called["name"] = name

    monkeypatch.setattr(pm, "switch_profile", _switch)

    gui = types.SimpleNamespace(
        key_var=types.SimpleNamespace(get=lambda: "k"),
        model_var=types.SimpleNamespace(get=lambda: cg.MODEL_OPTIONS[0]),
        prompt_txt=types.SimpleNamespace(get=lambda *a, **k: "prompt"),
        url_var=types.SimpleNamespace(get=lambda: "http://u"),
        profile_var=types.SimpleNamespace(get=lambda: "default"),
    )
    cg.RelayGUI.save(gui)

    assert called["name"] == "default"
    data = env.read_text()
    assert "MODEL_SLUG" in data
