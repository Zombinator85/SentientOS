"""Bridge for sending synthesized speech through two-way camera audio."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from tts_bridge import speak


class CameraTalkback:
    """Stream synthesized audio to a network camera via ffmpeg."""

    def __init__(self, rtsp_url: str | None = None, ffmpeg_path: str | None = None) -> None:
        self.rtsp_url = rtsp_url or os.getenv("CAMERA_TALKBACK_URL", "")
        if not self.rtsp_url:
            raise ValueError("RTSP or talkback URL required")
        self.ffmpeg_path = ffmpeg_path or shutil.which(os.getenv("FFMPEG_BINARY", "ffmpeg"))
        if not self.ffmpeg_path:
            raise FileNotFoundError("ffmpeg binary not found; install ffmpeg or set FFMPEG_BINARY")

    def speak(self, text: str, voice: Optional[str] = None) -> Path:
        if not text.strip():
            raise ValueError("text required for talkback")
        with tempfile.TemporaryDirectory(prefix="talkback_") as tmpdir:
            wav_path = Path(tmpdir) / "speech.wav"
            audio_file = speak(text, voice=voice, save_path=str(wav_path))
            if audio_file is None:
                raise RuntimeError("TTS synthesis failed")
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-re",
                "-i",
                audio_file,
                "-acodec",
                "aac",
                "-f",
                "rtsp",
                self.rtsp_url,
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg exited with {proc.returncode}: {proc.stderr.decode(errors='ignore')}")
            return Path(audio_file)


__all__ = ["CameraTalkback"]
