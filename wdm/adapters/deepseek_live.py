"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

import os, json, time
from typing import Optional


class DeepSeekAdapter:
    name = "deepseek_live"

    def __init__(self, model: str = "deepseek-r1") -> None:
        self.model = model
        self.key = os.getenv("DEEPSEEK_API_KEY")

    def _call(self, prompt: str) -> Optional[str]:
        if not self.key:
            return f"[deepseek_live missing DEEPSEEK_API_KEY] {prompt}"
        return f"[deepseek_live:{self.model}] {prompt}"

    def answer(self, prompt: str) -> str:
        return self._call(prompt) or f"[deepseek_live-fallback] {prompt}"

    def critique(self, text: str) -> str:
        return self._call(f"Critique: {text}") or f"[deepseek_live-critique-fallback] {text}"

