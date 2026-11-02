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

    GAMING_CHAT_STYLE_ID = "gaming_chat_style_v1"
    GAMING_CHAT_STYLE_INSTRUCTION = (
        "The user is in a gaming workload. Reply like a friendly peer in a brief, "
        "low-distraction style. Stay focused on what they asked; avoid long lists "
        "and unsolicited advice. Workload status does not identify the game, so "
        "do not infer its title or details."
    )
    GAMING_MAX_INPUT_CHARS = 4000
    GAMING_MAX_OUTPUT_CHARS = 1200
    GAMING_MAX_NEW_TOKENS = 96
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
    def apply_chat_response_style(cls, prompt: str, mode: EffectiveWorkloadMode) -> str:
        """Add the trusted low-distraction instruction before untrusted chat data."""
        if mode == "normal":
            return prompt
        marker = "[SESSION_HISTORY_DATA]"
        if (not isinstance(prompt, str) or not prompt.startswith("[SYSTEM_INSTRUCTION]\n")
                or marker not in prompt):
            raise ValueError("gaming_chat_instruction_anchor_invalid")
        head, tail = prompt.split(marker, 1)
        return head + cls.GAMING_CHAT_STYLE_INSTRUCTION + "\n" + marker + tail
