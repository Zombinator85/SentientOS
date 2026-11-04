"""Deterministic guards for unsupported gameplay claims in gaming replies."""
from __future__ import annotations

import re
from typing import Any, Mapping

from .governed_local_model_invocation import digest_payload

GROUNDING_POLICY_ID = "gaming_unobserved_claim_correction_v1"
GROUNDING_CORRECTION = (
    "SentientOS correction: I can’t see the game in this turn, but I’m here with you."
)

SCREEN_CAPABILITY_POLICY_ID = "screen_observation_unconfigured_correction_v2"
SCREEN_CAPABILITY_CORRECTION = (
    "I can’t see the game in this session because screen observation isn’t configured; "
    "the per-message option alone won’t change that. I can still reason from what you "
    "describe, suggest next checks, and use clues you share in this conversation."
)
_SCREEN_CAPABILITY_QUESTION = re.compile(
    r"\b(?:can|could|do|would|are)\s+you\b.{0,120}\b"
    r"(?:see|view|observe|access|watch)\b.{0,120}\b"
    r"(?:screen|display|game|gameplay)\b", re.IGNORECASE
)

_UNOBSERVED_CLAIM_PATTERNS = (
    re.compile(r"\bkeep(?:ing)? an eye on\b", re.IGNORECASE),
    re.compile(r"\b(?:watch(?:ing)?|monitor(?:ing)?)\b.{0,48}\b(?:game|gameplay|screen|session)\b", re.IGNORECASE),
    re.compile(r"\b(?:game|gameplay|screen|session)\b.{0,48}\b(?:watch(?:ing)?|monitor(?:ing)?)\b", re.IGNORECASE),
    re.compile(r"\bI(?:'m| am) enjoying (?:your |the )?(?:game|gameplay|session)\b", re.IGNORECASE),
    re.compile(r"\byou(?:'re| are) doing great\b", re.IGNORECASE),
    re.compile(
        r"\b(?:your|the)\s+(?:gameplay|play|performance)\s+"
        r"(?:is|looks|seems|feels)\s+(?:great|good|excellent|impressive|"
        r"engaging|fun|smooth|strong|fantastic|amazing)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:nice|great|good|impressive)\s+(?:shot|move|play|dodge|"
        r"parry|kill|combo|run)\b",
        re.IGNORECASE,
    ),
)


def unobserved_gameplay_claim(output: str, *, workload_mode: str,
                              screen_observation_provenance: Mapping[str, Any] | None) -> bool:
    """Whether a gaming answer makes a visual/performance claim without screen evidence."""
    if workload_mode != "gaming" or isinstance(screen_observation_provenance, Mapping):
        return False
    return any(pattern.search(output) for pattern in _UNOBSERVED_CLAIM_PATTERNS)


def corrected_screen_capability_output(
    output: str, *, user_message: str, screen_observation_configured: bool,
    screen_observation_provenance: Mapping[str, Any] | None,
) -> tuple[str, dict[str, str] | None]:
    """Answer direct visibility questions from actual screen-source configuration."""
    if (screen_observation_configured
            or isinstance(screen_observation_provenance, Mapping)
            or not _SCREEN_CAPABILITY_QUESTION.search(user_message)):
        return output, None
    return SCREEN_CAPABILITY_CORRECTION, {
        "policy_id": SCREEN_CAPABILITY_POLICY_ID,
        "reason_code": "screen_observation_not_configured",
    }


def corrected_gaming_output(output: str, *, workload_mode: str,
                            screen_observation_provenance: Mapping[str, Any] | None
                            ) -> tuple[str, dict[str, str] | None]:
    """Replace only a known unsupported claim with a fixed, attributed correction."""
    if not unobserved_gameplay_claim(output, workload_mode=workload_mode,
            screen_observation_provenance=screen_observation_provenance):
        return output, None
    return GROUNDING_CORRECTION, {
        "policy_id": GROUNDING_POLICY_ID,
        "reason_code": "unobserved_gameplay_claim",
    }


def corrected_output_lineage(*, invocation_output_digest: str, text: str,
                             output_truncated: bool, policy_id: str = GROUNDING_POLICY_ID,
                             reason_code: str = "unobserved_gameplay_claim") -> dict[str, Any]:
    return {
        "status": "grounding_policy_fallback",
        "invocation_output_digest": invocation_output_digest,
        "transcript_text_digest": digest_payload({"text": text}),
        "output_truncated": output_truncated,
        "policy_id": policy_id,
        "reason_code": reason_code,
    }
