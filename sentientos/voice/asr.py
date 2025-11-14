"""Whisper.cpp command-line transcription wrapper."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

LOGGER = logging.getLogger("sentientos.voice.asr")


@dataclass
class AsrConfig:
    whisper_binary_path: Path
    model_path: Path
    language: str = "en"
    max_segment_ms: int = 30000


class WhisperAsr:
    """Invoke the whisper.cpp CLI to transcribe audio files."""

    def __init__(self, config: AsrConfig):
        self._config = config

    @property
    def config(self) -> AsrConfig:
        return self._config

    def _build_command(self, audio_path: Path) -> List[str]:
        cfg = self._config
        return [
            str(cfg.whisper_binary_path),
            "-m",
            str(cfg.model_path),
            "-f",
            str(audio_path),
            "-l",
            cfg.language,
            "--max-segment-length",
            str(cfg.max_segment_ms),
        ]

    def transcribe_file(self, audio_path: Path) -> str:
        """Synchronously transcribe ``audio_path`` with whisper.cpp."""

        path = Path(audio_path)
        command = self._build_command(path)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError:
            LOGGER.warning("Whisper binary not found at %s", self._config.whisper_binary_path)
            return ""
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Failed to invoke whisper.cpp: %s", exc)
            return ""

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            LOGGER.warning(
                "whisper.cpp exited with status %s. %s",
                result.returncode,
                stderr,
            )
            return ""

        stdout = result.stdout or ""
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        return " ".join(lines)
