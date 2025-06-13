# Sanctuary privilege ritual must appear before any code or imports
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
import threading
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import uuid

try:
    import sounddevice as sd  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional audio dependency
    sd = None  # type: ignore

try:
    import numpy as np  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency
    np = None  # type: ignore

try:  # optional screenshot libraries
    import mss
except Exception:  # pragma: no cover - optional dependency
    mss = None

try:
    import pyautogui  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency
    pyautogui = None

try:
    import tkinter as tk
except Exception:  # pragma: no cover - headless env
    tk = None  # type: ignore

import tts_bridge
import parliament_bus


class DemoRecorder:
    """Record screenshots, audio, and conversation turns."""

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
        """Return ``True`` while recording is active."""
        return self._running


    def _capture_screen(self) -> Path:
        ts = _dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S_%f")
        path = Path(f"frame_{ts}.png")
        if mss is not None:
            with mss.mss() as sct:
                mon = sct.monitors[1]
                img = sct.grab(mon)
                from PIL import Image  # lazy import
                im = Image.frombytes("RGB", img.size, img.rgb)
                im.save(path)
        elif pyautogui is not None:
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

        def speak_capture(text: str, voice=None, save_path=None, emotions=None):
            if save_path is None:
                self._turn_id += 1
                ext = '.wav' if tts_bridge.ENGINE_TYPE in {'bark', 'coqui'} else '.mp3'
                demo_dir = Path('demos') / 'audio' / self.cycle_id
                demo_dir.mkdir(parents=True, exist_ok=True)
                save_path = str(demo_dir / f"{self._turn_id}{ext}")
            path = self._orig_speak(text, voice=voice, save_path=save_path, emotions=emotions)
            if path:
                self.audio_files.append(Path(path))
                self.turns.append({'text': text, 'audio_path': str(path)})
            return path

        tts_bridge.speak = speak_capture  # type: ignore[assignment]
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread is not None:
            self._thread.join()
        tts_bridge.speak = self._orig_speak  # type: ignore[assignment]

    def export(self) -> Path:
        if not self.frames:
            raise RuntimeError("no frames recorded")
        timestamp = _dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        out_dir = Path("demos")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{timestamp}.mp4"
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
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(audio_concat),
            "-c",
            "copy",
            str(audio_out),
        ], check=False)
        srt = work / "subs.srt"
        with srt.open("w", encoding="utf-8") as f:
            for idx, t in enumerate(self.turns, 1):
                start = int(idx)
                end = start + 2
                f.write(f"{idx}\n00:00:{start:02d},000 --> 00:00:{end:02d},000\n{t.get('text','')}\n\n")
        cmd = [
            "ffmpeg",
            "-y",
            "-r",
            "1",
            "-i",
            frame_pattern,
            "-i",
            str(audio_out),
            "-vf",
            f"subtitles={srt.as_posix()}",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ]
        subprocess.run(cmd, check=False)
        return out_path


_GUI: tk.Tk | None = None
_STATUS: tk.StringVar | None = None
_REC: DemoRecorder | None = None
_METER_VAR: tk.BooleanVar | None = None
_AUDIO_LEVEL: tk.DoubleVar | None = None
_METER_THREAD: threading.Thread | None = None
_METER_RUNNING = False


def _meter_loop() -> None:
    """Update audio level every 100ms while recording."""
    global _METER_RUNNING
    if sd is None or np is None or _AUDIO_LEVEL is None:
        return
    try:
        rate = int(sd.query_devices(None, 'input')['default_samplerate'])
    except Exception:
        rate = 44100
    block = int(rate * 0.1)
    try:
        with sd.InputStream(channels=1, samplerate=rate, blocksize=block) as stream:
            while _METER_RUNNING:
                data, _ = stream.read(block)
                level = float(np.sqrt(np.mean(np.square(data))))
                if _GUI is not None:
                    _GUI.after(0, _AUDIO_LEVEL.set, min(level * 10.0, 1.0))
    except Exception:
        pass
    finally:
        _METER_RUNNING = False


def _start_meter() -> None:
    global _METER_THREAD, _METER_RUNNING
    if _METER_RUNNING or _METER_VAR is None or not _METER_VAR.get():
        return
    if sd is None or np is None:
        return
    _METER_RUNNING = True
    _METER_THREAD = threading.Thread(target=_meter_loop, daemon=True)
    _METER_THREAD.start()


def _stop_meter() -> None:
    global _METER_RUNNING, _METER_THREAD
    if not _METER_RUNNING:
        return
    _METER_RUNNING = False
    if _METER_THREAD is not None:
        _METER_THREAD.join()
    _METER_THREAD = None
    if _AUDIO_LEVEL is not None:
        _AUDIO_LEVEL.set(0.0)


def _setup_gui() -> None:
    global _GUI, _STATUS, _REC, _METER_VAR, _AUDIO_LEVEL
    if tk is None:
        return
    _GUI = tk.Tk()
    _GUI.title("Demo Recorder")
    _STATUS = tk.StringVar(value="Idle")
    _REC = DemoRecorder()
    _METER_VAR = tk.BooleanVar(value=False)
    _AUDIO_LEVEL = tk.DoubleVar(value=0.0)

    def on_record():
        assert _REC is not None and _STATUS is not None
        _REC.start()
        if _METER_VAR.get():
            _start_meter()
        _STATUS.set("Recording")

    def on_stop():
        assert _REC is not None and _STATUS is not None
        _REC.stop()
        _stop_meter()
        _STATUS.set("Stopped")

    def on_export():
        assert _REC is not None and _STATUS is not None
        try:
            path = _REC.export()
            _STATUS.set(f"Saved {path}")
        except Exception as exc:
            _STATUS.set(str(exc))

    meter = None
    if tk is not None:
        try:
            from tkinter import ttk
            meter = ttk.Progressbar(
                _GUI,
                orient="horizontal",
                mode="determinate",
                maximum=1.0,
                variable=_AUDIO_LEVEL,
            )
        except Exception:  # pragma: no cover - tkinter optional
            meter = None

    def toggle_meter() -> None:
        if meter is None:
            return
        if _METER_VAR.get():
            meter.pack(fill="x")
            if _REC.running:
                _start_meter()
        else:
            meter.pack_forget()
            _stop_meter()

    tk.Label(_GUI, textvariable=_STATUS).pack()
    tk.Checkbutton(_GUI, text="Show Meter", variable=_METER_VAR, command=toggle_meter).pack(fill="x")
    if meter is not None:
        meter.pack_forget()
    tk.Button(_GUI, text="Record", command=on_record).pack(fill="x")
    tk.Button(_GUI, text="Stop", command=on_stop).pack(fill="x")
    tk.Button(_GUI, text="Export", command=on_export).pack(fill="x")


if __name__ == "__main__":  # pragma: no cover - manual demo
    _setup_gui()
    if _GUI is not None:
        _GUI.mainloop()
