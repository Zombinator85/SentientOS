"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import demo_recorder as dr_mod
from sentientos import parliament_bus
import tts_bridge
import subprocess
import time


def test_demo_recorder_basic(tmp_path, monkeypatch):
    rec = dr_mod.DemoRecorder()

    def fake_capture():
        fp = tmp_path / 'f.png'
        fp.write_bytes(b'0')
        return fp

    def fake_speak(text, voice=None, save_path=None, emotions=None):
        ap = tmp_path / 'a.mp3'
        ap.write_bytes(b'0')
        return str(ap)

    monkeypatch.setattr(rec, '_capture_screen', fake_capture)
    monkeypatch.setattr(tts_bridge, 'speak', fake_speak)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: None)

    rec.start()
    parliament_bus.publish({'speaker': 'assistant', 'text': 'hello'})
    time.sleep(0.1)
    rec.stop()
    out = rec.export()
    assert out.name.endswith('.mp4')
