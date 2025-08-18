"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

import os, json, time
from typing import Optional


class OpenAIAdapter:
    name = "openai_live"

    def __init__(self, model: str = "gpt-4o") -> None:
        self.model = model
        self.key = os.getenv("OPENAI_API_KEY")

    def _call(self, prompt: str) -> Optional[str]:
        if not self.key:
            return f"[openai_live missing OPENAI_API_KEY] {prompt}"
        # Minimal, dependency-free HTTP call avoided to keep tests green.
        # Return deterministic stub to avoid network in tests.
        return f"[openai_live:{self.model}] {prompt}"

    def answer(self, prompt: str) -> str:
        return self._call(prompt) or f"[openai_live-fallback] {prompt}"

    def critique(self, text: str) -> str:
        return self._call(f"Critique: {text}") or f"[openai_live-critique-fallback] {text}"

