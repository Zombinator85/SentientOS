from typing import List

import memory_manager as mm
import user_profile as up

SYSTEM_PROMPT = "You are Lumos, an emotionally present AI assistant."


def assemble_prompt(user_input: str, recent_messages: List[str] | None = None, k: int = 6) -> str:
    """Build a prompt including profile and relevant memories."""
    profile = up.format_profile()
    memories = mm.get_context(user_input, k=k)

    sections = [f"SYSTEM:\n{SYSTEM_PROMPT}"]
    if profile:
        sections.append(f"USER PROFILE:\n{profile}")
    if memories:
        mem_lines = "\n".join(f"- {m}" for m in memories)
        sections.append(f"RELEVANT MEMORIES:\n{mem_lines}")
    if recent_messages:
        ctx = "\n".join(recent_messages)
        sections.append(f"RECENT DIALOGUE:\n{ctx}")
    sections.append(f"USER:\n{user_input}")
    return "\n\n".join(sections)
