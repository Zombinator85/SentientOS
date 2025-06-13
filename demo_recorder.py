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


@dataclass
class DemoInfo:
    path: Path
    timestamp: float
    size: int
    duration: Optional[str] = None

try:  # optional screenshot libraries
    import mss
except Exception:  # pragma: no cover - optional dependency
    mss = None

try:
    import pyautogui
except Exception:  # pragma: no cover - optional dependency
    pyautogui = None

try:
    import tkinter as tk
except Exception:  # pragma: no cover - headless env
    tk = None  # type: ignore[assignment]

try:
    from pydub import AudioSegment
    from pydub.playback import play as _play_audio
except Exception:  # pragma: no cover - optional dependency
    AudioSegment = None
    _play_audio = None

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

        def speak_capture(
            text: str,
            voice: str | None = None,
            save_path: str | None = None,
            emotions: Any | None = None,
        ) -> str | None:
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
        if self._thread is not None:
            self._thread.join()
        tts_bridge.speak = self._orig_speak

    def export(self) -> Path:
        if not self.frames:
            raise RuntimeError("no frames recorded")
        timestamp = _dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        out_dir = DEMO_DIR
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


def _probe_duration(path: Path) -> Optional[str]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
        seconds = float(out)
        return str(_dt.timedelta(seconds=int(seconds)))
    except Exception:
        return None


def _scan_demos() -> List[DemoInfo]:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    demos: List[DemoInfo] = []
    for fp in DEMO_DIR.iterdir():
        if not fp.is_file():
            continue
        stat = fp.stat()
        demos.append(
            DemoInfo(
                path=fp,
                timestamp=stat.st_mtime,
                size=stat.st_size,
                duration=_probe_duration(fp),
            )
        )
    demos.sort(key=lambda d: d.timestamp, reverse=True)
    return demos


def _refresh_demos() -> None:
    global _DEMO_INFOS
    if _DEMO_LIST is None:
        return
    _DEMO_LIST.delete(0, tk.END)
    _DEMO_INFOS = _scan_demos()
    for info in _DEMO_INFOS:
        dt_str = _dt.datetime.fromtimestamp(info.timestamp).strftime("%Y-%m-%d %H:%M")
        size_kb = info.size // 1024
        dur = info.duration or "?"
        _DEMO_LIST.insert(tk.END, f"{info.path.name} | {dt_str} | {size_kb} KB | {dur}")


def _on_select(event=None) -> None:
    global _SELECTED
    if _DEMO_LIST is None:
        return
    sel = _DEMO_LIST.curselection()
    _SELECTED = _DEMO_INFOS[sel[0]] if sel else None


def _launch(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        if _STATUS is not None:
            _STATUS.set(str(exc))


def _play_demo() -> None:
    if _SELECTED is None:
        return
    _launch(_SELECTED.path)


def _open_folder() -> None:
    if _SELECTED is None:
        return
    _launch(_SELECTED.path.parent)


def _delete_demo() -> None:
    global _SELECTED
    if _SELECTED is None:
        return
    try:
        _SELECTED.path.unlink()
    except Exception as exc:
        if _STATUS is not None:
            _STATUS.set(str(exc))
    _SELECTED = None
    _refresh_demos()


_GUI: tk.Tk | None = None
_STATUS: tk.StringVar | None = None
_REC: DemoRecorder | None = None
_DEMO_LIST: tk.Listbox | None = None
_DEMO_INFOS: List[DemoInfo] = []
_SELECTED: Optional[DemoInfo] = None


def _find_last_demo() -> Path | None:
    demos = sorted(
        Path("demos").glob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return demos[0] if demos else None


def _playback_meter(path: Path) -> None:
    if AudioSegment is None or _play_audio is None or tk is None or _GUI is None:
        raise RuntimeError("Preview requires ffmpeg or pydub")

    audio = AudioSegment.from_file(path)
    meter = tk.Toplevel(_GUI)
    meter.title("Playback Meter")
    canvas = tk.Canvas(meter, width=300, height=50)
    canvas.pack(fill="both", expand=True)

    chunk_ms = 100
    chunks = [audio[i : i + chunk_ms] for i in range(0, len(audio), chunk_ms)]
    max_amp = audio.max_possible_amplitude or 1

    def update_meter(idx: int = 0) -> None:
        if idx >= len(chunks):
            meter.destroy()
            return
        chunk = chunks[idx]
        level = chunk.rms / max_amp
        canvas.delete("bar")
        canvas.create_rectangle(0, 50 - level * 50, 300, 50, fill="green", tags="bar")
        meter.after(chunk_ms, update_meter, idx + 1)

    threading.Thread(target=_play_audio, args=(audio,), daemon=True).start()
    update_meter()



def _setup_gui() -> None:
    global _GUI, _STATUS, _REC
    if tk is None:
        return
    _GUI = tk.Tk()
    _GUI.title("Demo Recorder")
    _STATUS = tk.StringVar(value="Idle")
    _REC = DemoRecorder()

    def on_record() -> None:
        assert _REC is not None and _STATUS is not None
        _REC.start()
        _STATUS.set("Recording")

    def on_stop() -> None:
        assert _REC is not None and _STATUS is not None
        _REC.stop()
        _STATUS.set("Stopped")

    def on_export() -> None:
        assert _REC is not None and _STATUS is not None
        try:
            path = _REC.export()
            _STATUS.set(f"Saved {path}")
        except Exception as exc:
            _STATUS.set(str(exc))

    def on_preview() -> None:
        assert _STATUS is not None
        demo = _find_last_demo()
        if demo is None:
            _STATUS.set("No demo found")
            return
        try:
            subprocess.run(["ffplay", "-autoexit", str(demo)], check=True)
            _STATUS.set(f"Played {demo.name}")
            return
        except Exception:
            try:
                _playback_meter(demo)
                _STATUS.set(f"Playing {demo.name}")
            except Exception as exc:
                _STATUS.set(str(exc))

    tk.Label(_GUI, textvariable=_STATUS).pack()
    tk.Button(_GUI, text="Record", command=on_record).pack(fill="x")
    tk.Button(_GUI, text="Stop", command=on_stop).pack(fill="x")
    tk.Button(_GUI, text="Export", command=on_export).pack(fill="x")
    tk.Button(_GUI, text="\u25B6 Preview Last Demo", command=on_preview).pack(fill="x")

    browser_frame = tk.Frame(_GUI)
    listbox = tk.Listbox(browser_frame, width=60)
    listbox.pack(side="left", fill="both", expand=True)
    scroll = tk.Scrollbar(browser_frame, command=listbox.yview)
    scroll.pack(side="right", fill="y")
    listbox.config(yscrollcommand=scroll.set)
    browser_frame.pack(fill="both", expand=True)

    btn_row = tk.Frame(_GUI)
    tk.Button(btn_row, text="\u25B6 Play", command=_play_demo).pack(side="left")
    tk.Button(btn_row, text="\U0001F4C1 Open Folder", command=_open_folder).pack(side="left")
    tk.Button(btn_row, text="\U0001F5D1 Delete", command=_delete_demo).pack(side="left")
    btn_row.pack(fill="x")

    global _DEMO_LIST
    _DEMO_LIST = listbox
    _refresh_demos()
    _DEMO_LIST.bind("<<ListboxSelect>>", _on_select)


if __name__ == "__main__":  # pragma: no cover - manual demo
    _setup_gui()
    if _GUI is not None:
        _GUI.mainloop()
