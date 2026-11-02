"""Bound chat inference while the operator is using a latency-sensitive workload."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal, Mapping

from .governed_local_model_invocation import LocalModelInvocationBudget

WorkloadMode = Literal["normal", "gaming"]
SUPPORTED_WORKLOAD_MODES = frozenset({"normal", "gaming"})


class GamingWorkloadPolicy:
    """Apply conservative per-turn ceilings without changing model authority."""

    GAMING_MAX_INPUT_CHARS = 4000
    GAMING_MAX_OUTPUT_CHARS = 1200
    GAMING_MAX_NEW_TOKENS = 96
    GAMING_TIMEOUT_SECONDS = 12.0

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
    def apply_to_chat_invocation(cls, mode: WorkloadMode,
                                 requested: LocalModelInvocationBudget,
                                 serving_lineage: Mapping[str, Any]
                                 ) -> tuple[LocalModelInvocationBudget, dict[str, Any]]:
        """Return the bounded budget and digest-bound lineage for one call."""
        return cls.constrain_budget(mode, requested), {
            **dict(serving_lineage), "workload_mode": mode,
        }
