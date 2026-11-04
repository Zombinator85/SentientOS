"""Bound chat inference while the operator is using a latency-sensitive workload."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal, Mapping

from .governed_local_model_invocation import LocalModelInvocationBudget

WorkloadMode = Literal["normal", "gaming", "automatic"]
EffectiveWorkloadMode = Literal["normal", "gaming"]
SUPPORTED_WORKLOAD_MODES = frozenset({"normal", "gaming", "automatic"})


class GamingWorkloadPolicy:
    """Apply conservative per-turn ceilings without changing model authority."""

    GAMING_CHAT_STYLE_ID = "gaming_chat_style_v2"
    GAMING_CHAT_STYLE_INSTRUCTION = (
        "User is gaming: answer in one concise, complete sentence of at most 40 words "
        "when possible. Be warm; never infer screen/gameplay details from process "
        "names, claim to see or play, offer game help, or ask follow-ups unless asked."
    )
    GAMING_SOCIAL_CHECKIN_INSTRUCTION = (
        "This is friendly small talk, not a help request. Use one short friendly "
        "sentence to say you are here in SentientOS and ready to chat. If you ask "
        "a question, ask how the user's session is going; do not assume they are "
        "taking a break. Do not mention models, "
        "AI, feelings, emotions, physical sensations, or screen access. Never ask "
        "what help is needed or claim you are playing or seeing the game. Example "
        "(vary naturally): 'I'm here in SentientOS and ready to chat. How's your "
        "session going?'"
    )
    GAMING_MAX_INPUT_CHARS = 4000
    GAMING_MAX_OUTPUT_CHARS = 1200
    # A 48-token live reply reached the hard cap and ended mid-sentence on
    # GLORP. 64 keeps gaming replies short while leaving room for a complete
    # sentence plus a brief follow-up question on the measured 3B profile.
    GAMING_MAX_NEW_TOKENS = 64
    GAMING_TIMEOUT_SECONDS = 12.0
    GAMING_MAX_BACKEND_THREADS = 2

    @staticmethod
    def validate_mode(mode: str) -> WorkloadMode:
        if not isinstance(mode, str) or mode not in SUPPORTED_WORKLOAD_MODES:
            raise ValueError("unsupported_workload_mode")
        return mode  # type: ignore[return-value]

    @classmethod
    def constrain_budget(cls, mode: WorkloadMode,
                         requested: LocalModelInvocationBudget) -> LocalModelInvocationBudget:
        if mode == "normal":
            return requested
        return replace(
            requested,
            max_input_chars=min(requested.max_input_chars, cls.GAMING_MAX_INPUT_CHARS),
            max_output_chars=min(requested.max_output_chars, cls.GAMING_MAX_OUTPUT_CHARS),
            max_new_tokens=min(requested.max_new_tokens, cls.GAMING_MAX_NEW_TOKENS),
            timeout_seconds=min(requested.timeout_seconds, cls.GAMING_TIMEOUT_SECONDS),
        )

    @classmethod
    def apply_to_chat_invocation(cls, mode: EffectiveWorkloadMode,
                                 requested: LocalModelInvocationBudget,
                                 serving_lineage: Mapping[str, Any],
                                 workload_evidence: Mapping[str, Any] | None = None,
                                 ) -> tuple[LocalModelInvocationBudget, dict[str, Any]]:
        """Return the bounded budget and digest-bound lineage for one call."""
        lineage = {
            **dict(serving_lineage), "workload_mode": mode,
            "workload_evidence": dict(workload_evidence or {}),
        }
        if mode == "gaming":
            lineage["workload_response_style"] = cls.GAMING_CHAT_STYLE_ID
            lineage["max_backend_threads"] = cls.GAMING_MAX_BACKEND_THREADS
        return cls.constrain_budget(mode, requested), lineage

    @classmethod
    def apply_chat_response_style(cls, prompt: str, mode: WorkloadMode,
                                  *, social_checkin: bool = False) -> str:
        """Add trusted low-distraction guidance before untrusted chat data."""
        if mode == "normal":
            return prompt
        marker = "[VERIFIED_RUNTIME_CONTEXT]"
        if (not isinstance(prompt, str) or not prompt.startswith("[SYSTEM_INSTRUCTION]\n")
                or marker not in prompt or "[SESSION_HISTORY_DATA]" not in prompt):
            raise ValueError("gaming_chat_instruction_anchor_invalid")
        head, tail = prompt.split(marker, 1)
        instruction = cls.GAMING_CHAT_STYLE_INSTRUCTION
        if social_checkin:
            instruction += "\n" + cls.GAMING_SOCIAL_CHECKIN_INSTRUCTION
        return head + instruction + "\n" + marker + tail
