"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from typing import List
import hashlib
import json
import logging
import os

import context_window as cw
from api import actuator

import memory_manager as mm
import user_profile as up
import emotion_memory as em
import affective_context as ac

SYSTEM_PROMPT = "You are Lumos, an emotionally present AI assistant."
_ALLOW_UNSAFE_GRADIENT = os.getenv("SENTIENTOS_ALLOW_UNSAFE") == "1"


def _canonical_dumps(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _compute_input_hash(plans: List[str], prompt: str) -> str:
    canonical = _canonical_dumps({"plans": plans, "prompt": prompt})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _log_invariant(
    *,
    invariant: str,
    reason: str,
    input_hash: str,
    details: dict,
) -> None:
    payload = {
        "event": "invariant_violation",
        "module": "prompt_assembler",
        "invariant": invariant,
        "reason": reason,
        "cycle_id": None,
        "input_hash": input_hash,
        "details": details,
    }
    logging.getLogger("sentientos.invariant").error(_canonical_dumps(payload))


def assemble_prompt(user_input: str, recent_messages: List[str] | None = None, k: int = 6) -> str:
    """Build a prompt including profile and relevant memories."""
    # Boundary assertion: continuity ≠ preference, repetition ≠ desire, memory ≠ attachment.
    # Prompt context is descriptive only; recurring fields do not express appetite or intent.
    profile = up.format_profile()
    memories = mm.get_context(user_input, k=k)
    presentation_only = {"affect", "tone", "presentation", "trust", "approval"}
    leaked_metadata: List[dict] = []
    normalized_memories: List[str] = []
    # All prompt assembly entrypoints route through this sanitizer; regression tests keep affect/tone stripping enforced.
    for memory in memories:
        if isinstance(memory, dict):
            sanitized = {k: v for k, v in memory.items() if k not in presentation_only}
            forbidden = [k for k in memory.keys() if k in presentation_only]
            if forbidden:
                leaked_metadata.append({"forbidden_keys": forbidden, "memory": dict(memory)})
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
    prompt = "\n\n".join(sections)

    forbidden_tokens = {"affect", "tone", "trust", "approval", "presentation"}
    if not _ALLOW_UNSAFE_GRADIENT and leaked_metadata:
        input_hash = _compute_input_hash(memories, prompt)
        _log_invariant(
            invariant="PROMPT_ASSEMBLY",
            reason="forbidden metadata keys detected",
            input_hash=input_hash,
            details={
                "leaks": leaked_metadata,
                "prompt": prompt,
            },
        )
        raise AssertionError("PROMPT_ASSEMBLY invariant violated: forbidden metadata keys detected")

    lowered_prompt = prompt.lower()
    leaked_tokens = [token for token in forbidden_tokens if token in lowered_prompt and token + ":" in lowered_prompt]
    if not _ALLOW_UNSAFE_GRADIENT and leaked_tokens:
        input_hash = _compute_input_hash(memories, prompt)
        _log_invariant(
            invariant="PROMPT_ASSEMBLY",
            reason="forbidden metadata tokens in prompt",
            input_hash=input_hash,
            details={
                "tokens": sorted(leaked_tokens),
                "prompt": prompt,
            },
        )
        raise AssertionError("PROMPT_ASSEMBLY invariant violated: forbidden metadata tokens in prompt")

    overlay = ac.capture_affective_context("prompt-assembly", overlay=emotion_ctx)
    ac.register_context(
        "prompt_assembler",
        overlay,
        metadata={"input_hash": _compute_input_hash(memories, prompt)},
    )

    return prompt
