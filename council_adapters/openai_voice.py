"""OpenAI council adapter."""
from __future__ import annotations

import os

from .base_voice import MeshVoice, _CloudVoiceMixin


class OpenAIVoice(_CloudVoiceMixin, MeshVoice):
    """Adapter for OpenAI advisory participation."""

    def __init__(self, name: str = "openai", *, model: str | None = None) -> None:
        model_name = model or os.getenv("OPENAI_MESH_MODEL", "gpt-4o-mini")
        super().__init__(
            name,
            advisory=True,
            env_prefix="OPENAI",
            base_limit=3,
            requires_key=True,
        )
        self.model = model_name

    def _persona(self) -> str:
        return f"OpenAI {self.model}"
