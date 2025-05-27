from typing import List

import context_window as cw

import memory_manager as mm
import user_profile as up
import emotion_memory as em

SYSTEM_PROMPT = "You are Lumos, an emotionally present AI assistant."


def assemble_prompt(user_input: str, recent_messages: List[str] | None = None, k: int = 6) -> str:
    """Build a prompt including profile and relevant memories."""
    profile = up.format_profile()
    memories = mm.get_context(user_input, k=k)
    emotion_ctx = em.average_emotion()
    msgs, summary = cw.get_context()

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
    if summary:
        sections.append(f"SUMMARY:\n{summary}")
    sections.append(f"USER:\n{user_input}")
    return "\n\n".join(sections)
