import importlib
import sys
import types
import json
from pathlib import Path

import avatar_presence_pulse_animation as apa


class DummyTk(types.ModuleType):
    class Tk:
        def __init__(self) -> None:
            self.updated = 0
        def title(self, title: str) -> None:
            self.title = title
        def update_idletasks(self) -> None:
            self.updated += 1
        def update(self) -> None:
            self.updated += 1
    class DoubleVar:
        def __init__(self, value: float = 0) -> None:
            self.val = value
        def set(self, v: float) -> None:
            self.val = v
        def get(self) -> float:
            return self.val
    class Scale:
        def __init__(self, *a, **k) -> None:
            pass
        def pack(self) -> None:
            pass


def test_animate_once_gui(tmp_path, monkeypatch):
    log = tmp_path / "anim.jsonl"
    monkeypatch.setitem(sys.modules, "tkinter", DummyTk("tkinter"))
    importlib.reload(apa)
    monkeypatch.setattr(apa, "LOG_PATH", log)
    monkeypatch.setattr(apa, "pulse", lambda: 0.5)
    apa.animate_once("a")
    assert log.exists()
    entry = json.loads(log.read_text())
    assert entry["pulse"] == 0.5
    if apa._GUI_VAR is not None:
        assert apa._GUI_VAR.get() == 0.5

