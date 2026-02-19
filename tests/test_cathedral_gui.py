"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import sys
import types
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class _StreamlitStub:
    def __init__(self) -> None:
        self.sidebar = self
    def set_page_config(self, **kwargs: object) -> None:
        pass
    def title(self, *a: object, **k: object) -> None:
        pass
    def button(self, *a: object, **k: object) -> bool:
        return False
    def write(self, *a: object, **k: object) -> None:
        pass
    def text_area(self, *a: object, **k: object) -> None:
        pass
    def subheader(self, *a: object, **k: object) -> None:
        pass


def test_module_loads(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", _StreamlitStub())
    import gui.cathedral_gui as cg
    importlib.reload(cg)
    assert cg.st is not None


def test_fetch_status(monkeypatch):
    class Resp:
        status_code = 200
        def raise_for_status(self) -> None:
            pass
        def json(self) -> dict[str, str]:
            return {"uptime": "0d 00:00:01", "last_heartbeat": "Tick 1"}
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=lambda url, timeout=2: Resp()))
    import gui.cathedral_gui as cg
    importlib.reload(cg)
    status = cg.fetch_status("http://x/status")
    assert status["uptime"] == "0d 00:00:01"
    assert status["last_heartbeat"] == "Tick 1"


def test_gui_import_survives_missing_experiment_tracker(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", _StreamlitStub())
    monkeypatch.delitem(sys.modules, "experiment_tracker", raising=False)
    import builtins

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "experiment_tracker":
            raise ModuleNotFoundError("missing experiment_tracker")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    import gui.cathedral_gui as cg
    importlib.reload(cg)
    assert cg.forge_panel_registered() is True
