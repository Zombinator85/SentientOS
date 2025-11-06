"""DeepSeek council adapter."""
from __future__ import annotations

import os

from .base_voice import MeshVoice, _CloudVoiceMixin


class DeepSeekVoice(_CloudVoiceMixin, MeshVoice):
    """Adapter for DeepSeek advisory council participation."""

    def __init__(self, name: str = "deepseek", *, model: str | None = None) -> None:
        model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        super().__init__(
            name,
            advisory=True,
            env_prefix="DEEPSEEK",
            base_limit=3,
            requires_key=True,
        )
        self.model = model_name

    def _persona(self) -> str:
        return f"DeepSeek {self.model}"
