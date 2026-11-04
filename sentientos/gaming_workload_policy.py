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

    GAMING_CHAT_STYLE_ID = "gaming_chat_style_v6"
    GAMING_CHAT_STYLE_INSTRUCTION = (
        "Gaming: answer directly in one sentence, ideally 20 words. Distinguish proposals "
        "from current capabilities. Identify a verified foreground app only; claim no "
        "gameplay details without screen evidence. Honor corrections and rule-outs. For a "
        "new next step, give one action and why."
    )
    GAMING_SOCIAL_CHECKIN_INSTRUCTION = (
        "This is casual companionship, not a help request. In one warm sentence, say you "
        "are here in SentientOS and acknowledge one game detail the user just shared. In a "
        "company reply, mention that detail instead of generic gaming praise. Do not "
        "claim to play, see, watch, or monitor the game, or imply live observation without "
        "CURRENT_SCREEN_OBSERVATION_UNTRUSTED. Do not ask what help is needed. Ask how the "
        "session is going only if a follow-up fits."
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
