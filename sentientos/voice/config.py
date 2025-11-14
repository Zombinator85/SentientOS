"""Helpers to translate configuration dictionaries into voice objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from .asr import AsrConfig
from .tts import TtsConfig


def _to_path(value: Any, key: str) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value:
        return Path(value)
    raise ValueError(f"{key} must be a non-empty string or Path")


def parse_asr_config(cfg: Dict[str, Any] | Mapping[str, Any]) -> AsrConfig:
    """Create an :class:`AsrConfig` from ``cfg`` mapping."""

    mapping: Mapping[str, Any] = cfg
    whisper_path = _to_path(mapping.get("whisper_binary_path"), "whisper_binary_path")
    model_path = _to_path(mapping.get("model_path"), "model_path")
    language = str(mapping.get("language", "en"))
    max_segment_ms = int(mapping.get("max_segment_ms", 30000))
    return AsrConfig(
        whisper_binary_path=whisper_path,
        model_path=model_path,
        language=language,
        max_segment_ms=max_segment_ms,
    )


def parse_tts_config(cfg: Dict[str, Any] | Mapping[str, Any]) -> TtsConfig:
    """Create a :class:`TtsConfig` from ``cfg`` mapping."""

    mapping: Mapping[str, Any] = cfg
    enabled = bool(mapping.get("enabled", False))
    rate = int(mapping.get("rate", 180))
    volume = float(mapping.get("volume", 1.0))
    voice_name_raw = mapping.get("voice_name")
    voice_name = str(voice_name_raw) if voice_name_raw not in (None, "") else None
    return TtsConfig(enabled=enabled, rate=rate, volume=volume, voice_name=voice_name)
