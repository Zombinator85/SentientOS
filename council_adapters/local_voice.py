"""Local deterministic council voice."""
from __future__ import annotations

from .base_voice import MeshVoice


class LocalVoice(MeshVoice):
    """Local mesh voice that always participates."""

    def __init__(self, name: str = "local", *, base_limit: int = 12) -> None:
        super().__init__(name, advisory=False, env_prefix="LOCAL_VOICE", base_limit=base_limit)

    def identity(self) -> str:
        return f"local:{self.name}"  # pragma: no cover - trivial accessor

    def _persona(self) -> str:
        return "SentientOS local analyst"
