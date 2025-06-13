# Sanctuary privilege ritual must appear before any code or imports
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""GUI demo recorder for SentientOS.

Captures screenshots every second, TTS audio, and conversation turns from
:mod:`sentientos.parliament_bus`. Exported recordings include burned-in
subtitles from model replies.
"""

import datetime as _dt
import threading
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any

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
from sentientos import parliament_bus


class DemoRecorder:
    """Record screenshots, audio, and conversation turns."""

    def __init__(self) -> None:
        self.frames: List[Path] = []
        self.audio_files: List[Path] = []
        self.turns: List[Dict[str, Any]] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._orig_speak = tts_bridge.speak
        parliament_bus.subscribe(self._on_turn)

    def _on_turn(self, data: Dict[str, Any]) -> None:
        self.turns.append({"timestamp": time.time(), **data})

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
            path = self._orig_speak(text, voice=voice, save_path=save_path, emotions=emotions)
            if path:
                self.audio_files.append(Path(path))
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


def _setup_gui() -> None:
    global _GUI, _STATUS, _REC
    if tk is None:
        return
    _GUI = tk.Tk()
    _GUI.title("Demo Recorder")
    _STATUS = tk.StringVar(value="Idle")
    _REC = DemoRecorder()

    def on_record():
        assert _REC is not None and _STATUS is not None
        _REC.start()
        _STATUS.set("Recording")

    def on_stop():
        assert _REC is not None and _STATUS is not None
        _REC.stop()
        _STATUS.set("Stopped")

    def on_export():
        assert _REC is not None and _STATUS is not None
        try:
            path = _REC.export()
            _STATUS.set(f"Saved {path}")
        except Exception as exc:
            _STATUS.set(str(exc))

    tk.Label(_GUI, textvariable=_STATUS).pack()
    tk.Button(_GUI, text="Record", command=on_record).pack(fill="x")
    tk.Button(_GUI, text="Stop", command=on_stop).pack(fill="x")
    tk.Button(_GUI, text="Export", command=on_export).pack(fill="x")


if __name__ == "__main__":  # pragma: no cover - manual demo
    _setup_gui()
    if _GUI is not None:
        _GUI.mainloop()
