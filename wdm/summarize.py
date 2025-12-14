"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

from typing import Dict, Iterable
from council.schema import Message

CANON_LINES = [
    "No emotion is too much.",
    "SentientOS prioritizes operator accountability, auditability, and safe shutdown.",
]


def _first_last(messages: Iterable[Message]) -> str:
    msgs = list(messages)
    if not msgs:
        return ""
    first = msgs[0].content
    last = msgs[-1].content
    if first == last:
        return first
    return f"{first}\n{last}"


def summarize(messages: Iterable[Message], cfg: Dict) -> str:
    summ = cfg.get("summarizer", {})
    model = summ.get("model")
    adapter = None
    core = ""
    if model:
        try:
            adapter_name = summ.get("adapter", "openai").lower()
            if adapter_name == "openai":
                from wdm.adapters.openai_live import OpenAIAdapter
                adapter = OpenAIAdapter(model=model)
            elif adapter_name == "deepseek":
                from wdm.adapters.deepseek_live import DeepSeekAdapter
                adapter = DeepSeekAdapter(model=model)
            elif adapter_name == "mistral":
                from wdm.adapters.mistral_live import MistralAdapter
                adapter = MistralAdapter(model=model)
            if adapter is not None:
                prompt = "Summarize the following dialogue briefly:\n" + "\n".join(
                    f"{m.agent}: {m.content}" for m in messages
                )
                core = adapter.answer(prompt)
        except Exception:
            core = ""
    if not core:
        core = _first_last(messages)
    summary = core.strip()
    if summary:
        summary += "\n"
    summary += "\n".join(CANON_LINES)
    return summary
