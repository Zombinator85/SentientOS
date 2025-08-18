"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

import os, json, time
from typing import Optional


class MistralAdapter:
    name = "mistral_live"

    def __init__(self, model: str = "mistral-large") -> None:
        self.model = model
        self.key = os.getenv("MISTRAL_API_KEY")

    def _call(self, prompt: str) -> Optional[str]:
        if not self.key:
            return f"[mistral_live missing MISTRAL_API_KEY] {prompt}"
        return f"[mistral_live:{self.model}] {prompt}"

    def answer(self, prompt: str) -> str:
        return self._call(prompt) or f"[mistral_live-fallback] {prompt}"

    def critique(self, text: str) -> str:
        return self._call(f"Critique: {text}") or f"[mistral_live-critique-fallback] {text}"

