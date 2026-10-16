"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations


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


def test_demo_recorder_headless_uses_synthetic_frame(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    monkeypatch.chdir(tmp_path)
    rec = dr_mod.DemoRecorder()

    commands = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: commands.append(args[0]))

    rec.start()
    rec.stop()

    assert len(rec.frames) == 1
    assert rec._stream is None
    assert rec._screen_thread is None
    assert rec.frames[0].suffix == ".ppm"
    assert rec.frames[0].read_bytes().startswith(b"P6\n640 360\n255\n")
    out = rec.export()
    assert out.name.endswith(".mp4")
    assert "-vf" not in commands[0]
    assert list((tmp_path / f".demo_{out.stem}").glob("frame_*.ppm"))
