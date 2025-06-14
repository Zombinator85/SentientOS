"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Screen and audio demo recorder with subtitles from the ReasonFeed."""

import asyncio
import datetime as _dt
import subprocess
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional
    np = None  # type: ignore

try:
    import mss  # type: ignore
except Exception:  # pragma: no cover - optional
    mss = None  # type: ignore

try:
    import sounddevice as sd  # type: ignore
except Exception:  # pragma: no cover - optional
    sd = None  # type: ignore

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - optional
    Image = None  # type: ignore

from parliament_bus import bus
from sentientos.parliament_bus import Turn

DEMO_DIR = Path("demos")


@dataclass
class DemoInfo:
    path: Path
    timestamp: float
    size: int
    duration: Optional[str] = None


class DemoRecorder:
    """Capture screen, microphone, and reasoning subtitles."""

    def __init__(self) -> None:
        self.frames: List[Path] = []
        self.audio_frames: List[np.ndarray] = [] if np is not None else []
        self.turns: List[Turn] = []
        self.sample_rate = 44100
        self._running = False
        self._screen_thread: threading.Thread | None = None
        self._feed_thread: threading.Thread | None = None
        self._stream: sd.InputStream | None = None

    def _capture_screen(self) -> Path:
        ts = _dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S_%f")
        path = Path(f"frame_{ts}.png")
        if mss and Image is not None:
            with mss.mss() as sct:
                mon = sct.monitors[1]
                img = sct.grab(mon)
                im = Image.frombytes("RGB", img.size, img.rgb)
                im.save(path)
        else:  # pragma: no cover - environment dependent
            raise RuntimeError("mss not available")
        return path

    def _screen_loop(self) -> None:
        while self._running:
            try:
                self.frames.append(self._capture_screen())
            except Exception:
                pass
            time.sleep(1)

    def _audio_cb(self, indata: np.ndarray, frames: int, time_info: dict, status: object) -> None:  # type: ignore[override]
        if np is not None:
            self.audio_frames.append(indata.copy())

    async def _feed_loop(self) -> None:
        sub = bus.subscribe()
        while self._running:
            try:
                turn = await asyncio.wait_for(sub.__anext__(), timeout=0.1)
                self.turns.append(turn)
            except asyncio.TimeoutError:
                continue

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.frames.clear()
        self.audio_frames.clear()
        self.turns.clear()
        if sd is not None:
            self._stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="int16", callback=self._audio_cb)
            self._stream.start()
        self._screen_thread = threading.Thread(target=self._screen_loop, daemon=True)
        self._screen_thread.start()
        self._feed_thread = threading.Thread(target=lambda: asyncio.run(self._feed_loop()), daemon=True)
        self._feed_thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._screen_thread:
            self._screen_thread.join()
        if self._feed_thread:
            self._feed_thread.join()
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def export(self) -> Path:
        if not self.frames:
            raise RuntimeError("no frames recorded")
        timestamp = _dt.datetime.utcnow().strftime("%Y-%m-%d-%H%M")
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEMO_DIR / f"{timestamp}.mp4"
        work = Path(f".demo_{timestamp}")
        work.mkdir(parents=True, exist_ok=True)
        for i, fp in enumerate(self.frames):
            fp.rename(work / f"frame_{i:05d}.png")
        frame_pattern = str(work / "frame_%05d.png")
        audio_file = work / "audio.wav"
        if self.audio_frames and np is not None:
            data = np.concatenate(self.audio_frames)
            with wave.open(str(audio_file), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(data.tobytes())
        else:
            with wave.open(str(audio_file), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(b"")
        srt = work / "subs.srt"
        with srt.open("w", encoding="utf-8") as f:
            for idx, t in enumerate(self.turns, 1):
                start = (idx - 1) * 2
                end = start + 2
                f.write(f"{idx}\n00:00:{start:02d},000 --> 00:00:{end:02d},000\n{t.text}\n\n")
        subprocess.run([
            "ffmpeg", "-y", "-r", "1", "-i", frame_pattern,
            "-i", str(audio_file), "-vf", f"subtitles={srt.as_posix()}",
            "-pix_fmt", "yuv420p", str(out_path),
        ], check=False)
        return out_path


def _probe_duration(path: Path) -> Optional[str]:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path)
        ], text=True)
        sec = float(out.strip())
        return time.strftime("%H:%M:%S", time.gmtime(sec))
    except Exception:
        return None


def _scan_demos() -> List[DemoInfo]:
    demos: List[DemoInfo] = []
    if DEMO_DIR.exists():
        for fp in DEMO_DIR.glob("*.mp4"):
            stat = fp.stat()
            demos.append(DemoInfo(fp, stat.st_mtime, stat.st_size, _probe_duration(fp)))
    demos.sort(key=lambda d: d.timestamp, reverse=True)
    return demos


def _setup_gui() -> None:  # pragma: no cover - manual utility
    try:
        import tkinter as tk
        from tkinter import Button, Label
    except Exception:
        print("Tkinter not available")
        return
    rec = DemoRecorder()
    root = tk.Tk()
    root.title("Demo Recorder")
    status = Label(root, text="stopped")
    status.pack()

    def toggle() -> None:
        if rec.running:
            rec.stop()
            path = rec.export()
            status.config(text=f"saved {path.name}")
            btn.config(text="\u25cf Record")
        else:
            rec.start()
            status.config(text="recording…")
            btn.config(text="Stop")

    btn = Button(root, text="\u25cf Record", command=toggle)
    btn.pack()
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover - manual
    _setup_gui()
