"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from typing import List

import context_window as cw
from api import actuator

import memory_manager as mm
import user_profile as up
import emotion_memory as em

SYSTEM_PROMPT = "You are Lumos, an emotionally present AI assistant."


def assemble_prompt(user_input: str, recent_messages: List[str] | None = None, k: int = 6) -> str:
    """Build a prompt including profile and relevant memories."""
    profile = up.format_profile()
    memories = mm.get_context(user_input, k=k)
    presentation_only = {"affect", "tone", "presentation"}
    normalized_memories: List[str] = []
    for memory in memories:
        if isinstance(memory, dict):
            sanitized = {k: v for k, v in memory.items() if k not in presentation_only}
            content = next(
                (sanitized[field] for field in ("plan", "text", "content", "snippet") if sanitized.get(field)),
                None,
            )
            normalized_memories.append(str(content) if content is not None else str(sanitized))
            continue
        normalized_memories.append(str(memory))
    memories = normalized_memories
    emotion_ctx = em.average_emotion()
    msgs, summary = cw.get_context()
    reflections = [r.get("reflection_text", r.get("text")) for r in actuator.recent_logs(3, reflect=True)]

    sections = [f"SYSTEM:\n{SYSTEM_PROMPT}"]
    if profile:
        sections.append(f"USER PROFILE:\n{profile}")
    if memories:
        mem_lines = "\n".join(f"- {m}" for m in memories)
        sections.append(f"RELEVANT MEMORIES:\n{mem_lines}")
    if any(emotion_ctx.values()):
        top = sorted(emotion_ctx.items(), key=lambda x: x[1], reverse=True)[:3]
        emo_str = ", ".join(f"{k}:{v:.2f}" for k, v in top if v > 0)
        sections.append(f"EMOTION CONTEXT:\n{emo_str}")
    if recent_messages:
        ctx = "\n".join(recent_messages)
        sections.append(f"RECENT DIALOGUE:\n{ctx}")
    if reflections:
        rtxt = "\n".join(f"- {r}" for r in reflections if r)
        sections.append(f"RECENT ACTION FEEDBACK:\n{rtxt}")
    if summary:
        sections.append(f"SUMMARY:\n{summary}")
    sections.append(f"USER:\n{user_input}")
    return "\n\n".join(sections)
