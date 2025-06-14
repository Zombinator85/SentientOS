"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
import demo_recorder as dr_mod
import parliament_bus
try:
    import sounddevice as sd
except Exception:  # pragma: no cover - optional
    from types import SimpleNamespace
    sd = SimpleNamespace(InputStream=lambda *a, **k: None)
import subprocess
import time


def test_demo_recorder_basic(tmp_path, monkeypatch):
    rec = dr_mod.DemoRecorder()

    def fake_capture():
        fp = tmp_path / 'f.png'
        fp.write_bytes(b'0')
        return fp

    class DummyStream:
        def start(self) -> None: pass
        def stop(self) -> None: pass
        def close(self) -> None: pass

    monkeypatch.setattr(sd, 'InputStream', lambda *a, **k: DummyStream())

    monkeypatch.setattr(rec, '_capture_screen', fake_capture)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: None)

    rec.start()
    asyncio.run(parliament_bus.bus.publish({'speaker': 'assistant', 'text': 'hello'}))
    time.sleep(0.1)
    rec.stop()
    out = rec.export()
    assert out.name.endswith('.mp4')


def test_demo_recorder_running_property(tmp_path, monkeypatch):
    rec = dr_mod.DemoRecorder()

    class DummyStream:
        def start(self) -> None: pass
        def stop(self) -> None: pass
        def close(self) -> None: pass

    monkeypatch.setattr(sd, 'InputStream', lambda *a, **k: DummyStream())
    monkeypatch.setattr(rec, '_capture_screen', lambda: tmp_path / 'f.png')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: None)

    assert not rec.running
    rec.start()
    assert rec.running
    rec.stop()
    assert not rec.running
