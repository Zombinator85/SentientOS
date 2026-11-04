"""Deterministic guards for unsupported gameplay claims in gaming replies."""
from __future__ import annotations

import re
from typing import Any, Mapping

from .governed_local_model_invocation import digest_payload

GROUNDING_POLICY_ID = "gaming_unobserved_claim_correction_v1"
GROUNDING_CORRECTION = (
    "I can’t see the game this turn, but I’m here with you."
)

SCREEN_CAPABILITY_POLICY_ID = "screen_observation_unconfigured_correction_v2"
SOCIAL_INSTRUCTION_ECHO_POLICY_ID = "social_instruction_echo_correction_v1"
SOCIAL_CHECK_IN_POLICY_ID = "social_check_in_grounding_correction_v1"
CURRENT_GAME_STATUS_POLICY_ID = "verified_foreground_only_game_status_v1"
_UNSUPPORTED_SELF_STATE = re.compile(
    r"\bI(?:'m| am)\s+(?:doing\s+(?:well|great|fine)|"
    r"(?:pretty\s+)?(?:good|great|fine|happy|excited|sad|tired))\b",
    re.IGNORECASE,
)
_SOCIAL_INSTRUCTION_ECHO = re.compile(
    r"\bdo not claim feelings\b|\binfer user activity from (?:a )?foreground app\b"
    r"|\bready to chat;\s*do not\b",
    re.IGNORECASE,
)
_SOCIAL_CHECK_IN = re.compile(
    r"\bhow\s+(?:are you|(?:is|'s)\s+your\s+(?:day|evening|morning|night))\b"
    r"|\bhow(?:'s| is)\s+it\s+going\b",
    re.IGNORECASE,
)
_GAME_STATUS_QUESTION = re.compile(
    r"\bwhat\b.{0,48}\b(?:tell|know|see|notice)\b.{0,64}\b"
    r"(?:cronos|game|gameplay|screen)\b",
    re.IGNORECASE,
)
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
    re.compile(
        r"\bI(?: can| could| will)\s+(?:share|describe|tell you)\s+"
        r"(?:what you(?:'re| are) experiencing|what(?:'s| is) happening)\b",
        re.IGNORECASE,
    ),
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


def corrected_unobserved_game_status(
    output: str, *, user_message: str,
    verified_runtime_context: Mapping[str, Any],
    screen_observation_provenance: Mapping[str, Any] | None,
) -> tuple[str, dict[str, str] | None]:
    """Answer live game-status questions from foreground evidence only."""
    if (not _GAME_STATUS_QUESTION.search(user_message)
            or isinstance(screen_observation_provenance, Mapping)):
        return output, None
    workload = verified_runtime_context.get("workload")
    if not isinstance(workload, Mapping) or workload.get("game_foreground") is not True:
        return output, None
    names = workload.get("configured_game_process_names")
    if (not isinstance(names, list) or not names
            or not isinstance(names[0], str) or not names[0]):
        return output, None
    process_name = names[0]
    label = re.sub(r"[-_]win64[-_]shipping$", "", process_name.rsplit(".", 1)[0],
                   flags=re.IGNORECASE)
    label = re.sub(r"[-_]+", " ", label).strip().title() or process_name
    return (
        f"{label} is the foreground app. I don’t have a screen observation for this turn, "
        "so I can’t describe the gameplay.",
        {
            "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
            "reason_code": "foreground_only_no_screen_observation",
        },
    )


def corrected_social_instruction_echo(
    output: str, *, user_message: str,
) -> tuple[str, dict[str, str] | None]:
    """Replace a leaked rule or unsupported self-state claim with a natural reply."""
    check_in = _SOCIAL_CHECK_IN.search(user_message) is not None
    instruction_echo = _SOCIAL_INSTRUCTION_ECHO.search(output) is not None
    unsupported_state = check_in and _UNSUPPORTED_SELF_STATE.search(output) is not None
    if not instruction_echo and not unsupported_state:
        return output, None
    if check_in:
        corrected = "I’m here and ready to chat. How’s your evening going?"
    elif _GAME_STATUS_QUESTION.search(user_message):
        corrected = (
            "I can confirm the game is in the foreground, but I can’t see its gameplay "
            "in this turn."
        )
    else:
        corrected = "I’m here as SentientOS and ready to chat. What would you like to know?"
    return corrected, {
        "policy_id": (SOCIAL_CHECK_IN_POLICY_ID if unsupported_state
                      else SOCIAL_INSTRUCTION_ECHO_POLICY_ID),
        "reason_code": ("unsupported_subjective_self_state" if unsupported_state
                        else "model_repeated_system_instruction"),
    }


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
