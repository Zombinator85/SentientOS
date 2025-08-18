"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

class DeepSeekAdapter:
    name = "deepseek_stub"
    def answer(self, prompt: str) -> str:
        return f"[deepseek] {prompt}"
    def critique(self, text: str) -> str:
        return f"[deepseek critique] {text}"
