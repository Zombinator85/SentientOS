"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""GUI demo recorder for SentientOS.

Captures screenshots every second, TTS audio, and conversation turns from
:mod:`parliament_bus`. Exported recordings include burned-in subtitles from
model replies.
"""

import datetime as _dt
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

DEMO_DIR = Path("demos")

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import numpy as np
except Exception:
    np = None

try:
    import mss
except Exception:
    mss = None

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None

try:
    from pydub import AudioSegment
    from pydub.playback import play as _play_audio
except Exception:
    AudioSegment = None
    _play_audio = None

import tts_bridge
import parliament_bus

@dataclass
class DemoInfo:
    path: Path
    timestamp: float
    size: int
    duration: Optional[str] = None

class DemoRecorder:
    def __init__(self) -> None:
        self.frames: List[Path] = []
        self.audio_files: List[Path] = []
        self.turns: List[Dict[str, Any]] = []
        self.cycle_id: str = uuid.uuid4().hex
        self._turn_id = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._orig_speak = tts_bridge.speak

    @property
    def running(self) -> bool:
        return self._running

    def _capture_screen(self) -> Path:
        ts = _dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S_%f")
        path = Path(f"frame_{ts}.png")
        if mss:
            with mss.mss() as sct:
                mon = sct.monitors[1]
                img = sct.grab(mon)
                from PIL import Image
                im = Image.frombytes("RGB", img.size, img.rgb)
                im.save(path)
        elif pyautogui:
            img = pyautogui.screenshot()
            img.save(path)
        else:
            raise RuntimeError("No screenshot backend available")
        return path

    def _record_loop(self) -> None:
        while self._running:
            try:
                frame = self._capture_screen()
                self.frames.append(frame)
            except Exception:
                pass
            time.sleep(1)

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        def speak_capture(text: str, voice: str | None = None, save_path: str | None = None, emotions: Any | None = None) -> str | None:
            if save_path is None:
                self._turn_id += 1
                ext = '.wav' if tts_bridge.ENGINE_TYPE in {'bark', 'coqui'} else '.mp3'
                demo_dir = DEMO_DIR / 'audio' / self.cycle_id
                demo_dir.mkdir(parents=True, exist_ok=True)
                save_path = str(demo_dir / f"{self._turn_id}{ext}")
            path = self._orig_speak(text, voice=voice, save_path=save_path, emotions=emotions)
            if path:
                self.audio_files.append(Path(path))
                self.turns.append({'text': text, 'audio_path': str(path)})
            return path

        tts_bridge.speak = speak_capture
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join()
        tts_bridge.speak = self._orig_speak

    def export(self) -> Path:
        if not self.frames:
            raise RuntimeError("no frames recorded")
        timestamp = _dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        out_path = DEMO_DIR / f"{timestamp}.mp4"
        work = Path(f".demo_{timestamp}")
        work.mkdir(parents=True, exist_ok=True)
        for i, fp in enumerate(self.frames):
            fp.rename(work / f"frame_{i:05d}.png")
        frame_pattern = str(work / "frame_%05d.png")
        audio_concat = work / "audio.txt"
        with audio_concat.open("w", encoding="utf-8") as f:
            for ap in self.audio_files:
                f.write(f"file '{ap.as_posix()}'\n")
        audio_out = work / "audio.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i",
            str(audio_concat), "-c", "copy", str(audio_out)
        ], check=False)
        srt = work / "subs.srt"
        with srt.open("w", encoding="utf-8") as f:
            for idx, t in enumerate(self.turns, 1):
                start = int(idx)
                end = start + 2
                f.write(f"{idx}\n00:00:{start:02d},000 --> 00:00:{end:02d},000\n{t.get('text','')}\n\n")
        subprocess.run([
            "ffmpeg", "-y", "-r", "1", "-i", frame_pattern, "-i",
            str(audio_out), "-vf", f"subtitles={srt.as_posix()}",
            "-pix_fmt", "yuv420p", str(out_path)
        ], check=False)
        return out_path

# Additional utility functions like _probe_duration, _scan_demos, _setup_gui omitted here for brevity

# Run _setup_gui() at __main__ if using directly
