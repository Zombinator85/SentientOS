"""Deterministic guards for unsupported gameplay claims in gaming replies."""
from __future__ import annotations

import re
from typing import Any, Mapping

from .governed_local_model_invocation import digest_payload

GROUNDING_POLICY_ID = "gaming_unobserved_claim_correction_v1"
GROUNDING_CORRECTION = (
    "I can’t see the game this turn, but I’m here with you."
)
SOCIAL_GAMING_GROUNDING_CORRECTION = (
    "I’m here with you in SentientOS. How’s the session going?"
)

SCREEN_CAPABILITY_POLICY_ID = "screen_observation_unconfigured_correction_v2"
SOCIAL_INSTRUCTION_ECHO_POLICY_ID = "social_instruction_echo_correction_v1"
SOCIAL_CHECK_IN_POLICY_ID = "social_check_in_grounding_correction_v1"
CURRENT_GAME_STATUS_POLICY_ID = "verified_foreground_only_game_status_v1"
GAME_PROCESS_STATUS_POLICY_ID = "verified_game_process_status_v1"
SYSTEM_IDENTITY_POLICY_ID = "sentientos_companion_identity_grounding_v1"
UNPROVIDED_SOURCE_POLICY_ID = "unprovided_referenced_source_grounding_v1"
GAMING_NEXT_STEP_POLICY_ID = "gaming_next_step_nonresponsive_fallback_v1"
UNPROVIDED_SOURCE_CORRECTION = (
    "I don’t have the referenced source’s contents in this conversation, so I can’t "
    "summarize its recommendations or assess what the data establish. Share the source "
    "or its key excerpts and I’ll answer from that."
)
_UNSUPPORTED_SELF_STATE = re.compile(
    r"\bI(?:'m| am)\s+(?:doing\s+(?:well|great|fine)|"
    r"(?:pretty\s+)?(?:good|great|fine|happy|excited|sad|tired))\b|"
    r"\bEnjoying your gaming session\b",
    re.IGNORECASE,
)
_UNSOLICITED_SOCIAL_AI_BOILERPLATE = re.compile(
    r"\b(?:as an? (?:ai|artificial intelligence)(?: language)? model|"
    r"i(?:'m| am) (?:just )?an? (?:ai|artificial intelligence)"
    r"(?: language)? model|"
    r"i(?: do not| don't| cannot| can't) have (?:human )?"
    r"(?:feelings|emotions|subjective experiences)|"
    r"(?:my|the) (?:training|knowledge) cutoff (?:is|was)|"
    r"(?:my|the) training (?:only )?goes up to)\b",
    re.IGNORECASE,
)
_TRAINING_CUTOFF_QUESTION = re.compile(
    r"\b(?:training|knowledge) cutoff\b|\bwhen were you trained\b|"
    r"\bwhat (?:is|was) your training\b",
    re.IGNORECASE,
)
_SOCIAL_INSTRUCTION_ECHO = re.compile(
    r"\bdo not claim feelings\b|\binfer user activity from (?:a )?foreground app\b"
    r"|\bready to chat;\s*do not\b",
    re.IGNORECASE,
)
_SYSTEM_INSTRUCTION_ECHO = re.compile(
    r"\bforeground confirms only the app is open\b|"
    r"\b(?:CURRENT_SCREEN_OBSERVATION_UNTRUSTED|VERIFIED_RUNTIME_CONTEXT|"
    r"VERIFIED_CURRENT_WORKLOAD_FACTS|SYSTEM_INSTRUCTION)\b",
    re.IGNORECASE,
)
_NEXT_STEP_ADVICE_REQUEST = re.compile(
    r"\b(?:what should I do next|what do I do next|what is one next step|"
    r"what\'s one next step|one next step based on|what should I check next|"
    r"where should I go next|what do I do now|what should I check)\b",
    re.IGNORECASE,
)
_NEXT_STEP_VISIBILITY_BOILERPLATE = re.compile(
    r"\b(?:without screen observation|no screen observation|cannot confirm gameplay|"
    r"can\'t confirm gameplay|verify (?:the )?foreground app|"
    r"verified foreground app|scene description available)\b",
    re.IGNORECASE,
)
_USER_SHARED_GAME_CLUE = re.compile(
    r"\b(?:note|clue|sign|message|text|label)\s+(?:that\s+)?"
    r"(?:says|reads|states|is)\s+[\"]?([^\"\n.!?]{2,80})",
    re.IGNORECASE,
)
_USER_SAYS_SCENE_UNDESCRIBED = re.compile(
    r"\b(?:have not|haven\'t|did not|didn\'t) described "
    r"(?:the )?(?:current )?(?:game )?(?:scene|screen)\b",
    re.IGNORECASE,
)
_KEEP_IN_MIND_REQUEST = re.compile(
    r"\b(?:keep|remember) (?:that|this|it) in mind\b",
    re.IGNORECASE,
)
_SOCIAL_CHECK_IN = re.compile(
    r"\bhow\s+(?:are you|(?:is|'s)\s+your\s+(?:day|evening|morning|night))\b"
    r"|\bhow(?:'s| is)\s+it\s+going\b",
    re.IGNORECASE,
)
_NONRESPONSIVE_GAMING_CHECK_IN = re.compile(
    r"\b(?:how about you|hope you)\s+(?:enjoy|have fun with)\s+"
    r"(?:your\s+)?(?:gaming session|game|gameplay)\b",
    re.IGNORECASE,
)
_SYSTEM_IDENTITY_QUESTION = re.compile(
    r"\b(?:who are you|what(?:'s| is) your name|what can I call you|"
    r"what are you called|what should I call you)\b",
    re.IGNORECASE,
)
_ACTIVE_MODEL_QUESTION = re.compile(
    r"\b(?:which|what)\s+(?:model|checkpoint)\b|"
    r"\bwhat model (?:are you|is active|powers you)\b",
    re.IGNORECASE,
)
_GAME_OPEN_QUESTION = re.compile(
    r"\b(?:what|which) game (?:is|\'s) open\b|"
    r"\bwhat game are we (?:playing|looking at)\b",
    re.IGNORECASE,
)
_GAME_RUNNING_QUESTION = re.compile(
    r"\b(?:is|are)\b.{0,48}\b(?:cronos|the game|my game|this game)\b"
    r".{0,48}\b(?:still )?(?:running|open|active)\b",
    re.IGNORECASE,
)
_GAME_PROCESS_STATUS_DISTINCTION = re.compile(
    r"\b(?:running|run|open)\b.{0,64}\bforeground\b|"
    r"\bforeground\b.{0,64}\b(?:running|run|open)\b",
    re.IGNORECASE,
)
_GAME_ACTIVITY_QUESTION = re.compile(
    r"\b(?:what|how)\b[^\r\n.!?]{0,64}\b(?:I am|I'm|you are|you're)\s+"
    r"(?:doing|playing|seeing|experiencing)\b[^\r\n.!?]{0,64}\b"
    r"(?:cronos|game|gameplay|screen)\b|"
    r"\bwhat\s+(?:am I|are you)\s+doing\s+(?:in|on)\s+"
    r"(?:cronos|the game|this game)\b",
    re.IGNORECASE,
)
_MODEL_SELF_REFERENCE = re.compile(
    r"\b(?:i am|i['’]m|my name is)\s+(?:currently\s+)?"
    r"(?:called\s+)?$",
    re.IGNORECASE,
)
_GAME_STATUS_QUESTION = re.compile(
    r"\bwhat\b.{0,48}\b(?:tell|know|see|notice)\b.{0,64}\b"
    r"(?:cronos|game|gameplay|screen)\b",
    re.IGNORECASE,
)
_GAME_SCREEN_ACTIVITY_QUESTION = re.compile(
    r"\b(?:what(?:'s| is)\s+(?:happening|going on)|"
    r"can you (?:tell|describe|see)\s+what(?:'s| is)\s+"
    r"(?:happening|going on))\b.{0,100}\b"
    r"(?:cronos|game|gameplay|screen)\b",
    re.IGNORECASE,
)
_VERIFIED_CURRENT_GAME_CONTEXT_QUESTION = re.compile(
    r"\bwhat can (?:sentientos|you) (?:confidently )?"
    r"(?:say|tell|confirm|verify)\b.{0,120}\b"
    r"(?:current situation|current workload|current setup|current moment|this moment|right now)\b"
    r".{0,120}\bwhat can (?:it|you) (?:not|cannot|can\s+not) (?:see|observe)\b",
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
_SCREEN_NOT_CONFIGURED_CLAIM = re.compile(
    r"\b(?:screen|visual|game[- ]screen) observation\b.{0,48}"
    r"\b(?:not configured|is not configured|isn['’]t configured|"
    r"has not been configured|hasn['’]t been configured|disabled)\b",
    re.IGNORECASE,
)
_SCREEN_VISIBILITY_CLARIFICATION_REQUEST = re.compile(
    r"\b(?:be clear|tell me|let me know|explain)\b.{0,80}\b"
    r"(?:if|whether)\s+you\b.{0,24}\b(?:can(?:not|n't)?|"
    r"could(?:not|n't)?|are able to)\b.{0,24}\b"
    r"(?:see|view|observe|access|watch)\b.{0,64}\b"
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


def is_verified_current_game_context_question(user_message: str) -> bool:
    """Whether the user asks what the current system can verify and cannot see."""
    combined_status_question = (
        _GAME_STATUS_QUESTION.search(user_message) is not None
        and _GAME_PROCESS_STATUS_DISTINCTION.search(user_message) is not None
        and _SCREEN_CAPABILITY_QUESTION.search(user_message) is not None
    )
    return (_VERIFIED_CURRENT_GAME_CONTEXT_QUESTION.search(user_message) is not None
            or combined_status_question)


def is_direct_screen_activity_question(user_message: str) -> bool:
    """Whether the user directly asks about current game-screen activity."""
    return (
        _GAME_SCREEN_ACTIVITY_QUESTION.search(user_message) is not None
        or _GAME_ACTIVITY_QUESTION.search(user_message) is not None
        or _SCREEN_CAPABILITY_QUESTION.search(user_message) is not None
        or _SCREEN_VISIBILITY_CLARIFICATION_REQUEST.search(user_message) is not None
        or is_verified_current_game_context_question(user_message)
    )


def _has_readable_screen_text(
    screen_observation_provenance: Mapping[str, Any] | None,
) -> bool:
    """Whether this turn contains OCR text usable as screen evidence."""
    return (isinstance(screen_observation_provenance, Mapping)
            and screen_observation_provenance.get("text_status", "available") == "available")


def unobserved_gameplay_claim(output: str, *, workload_mode: str,
                              screen_observation_provenance: Mapping[str, Any] | None) -> bool:
    """Whether a gaming answer makes a visual/performance claim without screen evidence."""
    if workload_mode != "gaming" or _has_readable_screen_text(screen_observation_provenance):
        return False
    return any(pattern.search(output) for pattern in _UNOBSERVED_CLAIM_PATTERNS)


def corrected_unobserved_game_status(
    output: str, *, user_message: str,
    verified_runtime_context: Mapping[str, Any],
    screen_observation_provenance: Mapping[str, Any] | None,
) -> tuple[str, dict[str, str] | None]:
    """Answer live game-status questions from foreground evidence only."""
    activity_question = (
        _GAME_ACTIVITY_QUESTION.search(user_message) is not None
        or _GAME_SCREEN_ACTIVITY_QUESTION.search(user_message) is not None
        or _SCREEN_VISIBILITY_CLARIFICATION_REQUEST.search(user_message) is not None
        or is_verified_current_game_context_question(user_message)
    )
    if (not (_GAME_STATUS_QUESTION.search(user_message)
             or activity_question
             or _GAME_RUNNING_QUESTION.search(user_message))
            or _has_readable_screen_text(screen_observation_provenance)):
        return output, None
    workload = verified_runtime_context.get("workload")
    if not isinstance(workload, Mapping):
        return output, None
    names = workload.get("configured_game_process_names")
    if (not isinstance(names, list)
            or any(not isinstance(name, str) or not name for name in names)):
        names = []
    mentioned = [name for name in names
        if re.sub(r"[-_]win64[-_]shipping$", "", name.rsplit(".", 1)[0],
                  flags=re.IGNORECASE).replace("-", " ").replace("_", " ").strip().casefold()
        in user_message.casefold()]
    if is_verified_current_game_context_question(user_message):
        if workload.get("observation_status") != "available":
            return output, None
        foreground = workload.get("game_foreground")
        running = workload.get("game_process_running")
        if type(foreground) is not bool:
            return output, None
        if foreground:
            running = True
        elif type(running) is not bool:
            return output, None
        process_name = (mentioned[0] if len(mentioned) == 1 else
                        names[0] if len(names) == 1 else None)
        if process_name is not None:
            label = re.sub(r"[-_]win64[-_]shipping$", "", process_name.rsplit(".", 1)[0],
                           flags=re.IGNORECASE)
            label = re.sub(r"[-_]+", " ", label).strip().title() or process_name
        else:
            label = "The allowlisted game process"
        if foreground:
            workload_fact = f"{label} is the foreground app"
        elif running:
            workload_fact = f"{label} is running in the background"
        else:
            workload_fact = "No allowlisted game process is running"
        mode = workload.get("effective_mode")
        mode_fact = (f", and SentientOS is in {mode} mode"
                     if mode in {"normal", "gaming"} else "")
        capabilities = verified_runtime_context.get("capabilities")
        screen = (capabilities.get("screen_observation")
                  if isinstance(capabilities, Mapping) else None)
        if isinstance(screen, Mapping) and screen.get("configured") is False:
            observation_limit = (
                "Screen observation isn’t configured in this session, "
                "so I can’t describe the gameplay."
            )
        else:
            observation_limit = (
                "I don’t have a screen observation for this turn, "
                "so I can’t describe the gameplay."
            )
        return (
            f"I can verify {workload_fact}{mode_fact}. {observation_limit}",
            {
                "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
                "reason_code": "verified_workload_context_screen_unavailable",
            },
        )
    if _GAME_RUNNING_QUESTION.search(user_message):
        if len(mentioned) == 1:
            process_name = mentioned[0]
        elif len(names) == 1:
            process_name = names[0]
        else:
            return output, None
        label = re.sub(r"[-_]win64[-_]shipping$", "", process_name.rsplit(".", 1)[0],
                       flags=re.IGNORECASE)
        label = re.sub(r"[-_]+", " ", label).strip().title() or process_name
        running = workload.get("game_process_running")
        if type(running) is not bool:
            return output, None
        capabilities = verified_runtime_context.get("capabilities")
        screen = capabilities.get("screen_observation") if isinstance(
            capabilities, Mapping) else None
        screen_unconfigured = (isinstance(screen, Mapping)
            and screen.get("configured") is False)
        foreground = workload.get("game_foreground") is True
        if running:
            status = "is running in the foreground" if foreground else "is still running in the background"
            observation_limit = (
                "Screen observation isn’t configured in this session, so I can’t describe the gameplay."
                if screen_unconfigured else
                "I don’t have a screen observation for this turn, so I can’t describe the gameplay."
            )
            response = f"{label} {status}. {observation_limit}"
            reason = "allowlisted_game_process_running_no_screen_observation"
        else:
            observation_limit = (
                "Screen observation isn’t configured in this session."
                if screen_unconfigured else
                "I don’t have a screen observation for this turn."
            )
            response = f"I don’t detect {label} running right now. {observation_limit}"
            reason = "allowlisted_game_process_not_running_no_screen_observation"
        return response, {
            "policy_id": GAME_PROCESS_STATUS_POLICY_ID,
            "reason_code": reason,
        }
    if workload.get("game_foreground") is not True:
        return output, None
    process_name = names[0]
    label = re.sub(r"[-_]win64[-_]shipping$", "", process_name.rsplit(".", 1)[0],
                   flags=re.IGNORECASE)
    label = re.sub(r"[-_]+", " ", label).strip().title() or process_name
    if activity_question:
        if (isinstance(screen_observation_provenance, Mapping)
                and screen_observation_provenance.get("text_status") == "no_readable_text"):
            return (
                f"I can confirm {label} is the foreground app, but OCR found no readable text "
                "in the captured game screen, so I can’t describe the scene from this "
                "text-only observation.",
                {"policy_id": CURRENT_GAME_STATUS_POLICY_ID,
                 "reason_code": "screen_capture_no_readable_text"},
            )
        capabilities = verified_runtime_context.get("capabilities")
        screen = capabilities.get("screen_observation") if isinstance(
            capabilities, Mapping) else None
        if _SCREEN_VISIBILITY_CLARIFICATION_REQUEST.search(user_message):
            unconfigured = isinstance(screen, Mapping) and screen.get("configured") is False
            limitation = ("screen observation isn't configured" if unconfigured
                          else "I don't have a screen observation this turn")
            return (
                f"I'm here with you, but {limitation}, so I can't see the gameplay.",
                {
                    "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
                    "reason_code": (
                        "foreground_only_screen_observation_unconfigured"
                        if unconfigured else "foreground_only_no_screen_observation"
                    ),
                },
            )
        if isinstance(screen, Mapping) and screen.get("configured") is False:
            return (
                f"I can confirm {label} is the foreground app, but screen observation "
                "isn’t configured in this session, so I can’t tell what’s happening on screen.",
                {
                    "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
                    "reason_code": "foreground_only_screen_observation_unconfigured",
                },
            )
        return (
            f"I can confirm {label} is the foreground app, but I can’t tell what you’re "
            "doing in it because I don’t have a screen observation this turn.",
            {
                "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
                "reason_code": "foreground_only_no_screen_observation",
            },
        )
    return (
        f"{label} is the foreground app. I don’t have a screen observation for this turn, "
        "so I can’t describe the gameplay.",
        {
            "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
            "reason_code": "foreground_only_no_screen_observation",
        },
    )




def corrected_system_identity_output(
    output: str, *, user_message: str,
    verified_runtime_context: Mapping[str, Any],
) -> tuple[str, dict[str, str] | None]:
    """Keep the companion identity distinct from its configured inference backend."""
    identity_question = _SYSTEM_IDENTITY_QUESTION.search(user_message) is not None
    social_check_in = _SOCIAL_CHECK_IN.search(user_message) is not None
    if not identity_question and not social_check_in:
        return output, None
    active_model = verified_runtime_context.get("active_model")
    label = (active_model.get("configured_candidate_label")
             if isinstance(active_model, Mapping) else None)
    if not isinstance(label, str) or not label:
        return output, None
    lowered = output.casefold()
    label_index = -1
    label_words = label.split()
    candidates = {
        " ".join(label_words[start:start + count])
        for count in range(1, min(3, len(label_words)) + 1)
        for start in range(len(label_words) - count + 1)
    }
    for candidate in sorted(candidates, key=lambda value: (-len(value.split()), -len(value))):
        candidate_index = lowered.find(candidate.casefold())
        if (candidate_index >= 0
                and _MODEL_SELF_REFERENCE.search(output[:candidate_index]) is not None):
            label_index = candidate_index
            break
    if label_index < 0:
        return output, None

    parts = ["I'm SentientOS, your local companion."]
    if social_check_in:
        parts.append("I'm here and ready to chat. What's on your mind?")
    if _ACTIVE_MODEL_QUESTION.search(user_message):
        parts.append(f"The configured model powering this conversation is {label}.")
    if _GAME_OPEN_QUESTION.search(user_message) or _GAME_STATUS_QUESTION.search(user_message):
        workload = verified_runtime_context.get("workload")
        names = (workload.get("configured_game_process_names")
                 if isinstance(workload, Mapping) else None)
        if (isinstance(workload, Mapping) and workload.get("game_foreground") is True
                and isinstance(names, list) and names and isinstance(names[0], str)):
            process_name = names[0]
            game = re.sub(r"[-_]win64[-_]shipping$", "",
                process_name.rsplit(".", 1)[0], flags=re.IGNORECASE)
            game = re.sub(r"[-_]+", " ", game).strip().title() or process_name
            parts.append(f"{game} is the foreground app.")
        if verified_runtime_context.get("capabilities", {}).get(
                "screen_observation", {}).get("included_this_turn") is not True:
            parts.append("I don't have a screen observation for this turn, so I can't describe the gameplay.")
    return " ".join(parts), {
        "policy_id": SYSTEM_IDENTITY_POLICY_ID,
        "reason_code": "backend_model_misidentified_as_companion",
    }


def corrected_social_instruction_echo(
    output: str, *, user_message: str,
) -> tuple[str, dict[str, str] | None]:
    """Replace a leaked rule or unsupported self-state claim with a natural reply."""
    check_in = _SOCIAL_CHECK_IN.search(user_message) is not None
    instruction_echo = (
        _SOCIAL_INSTRUCTION_ECHO.search(output) is not None
        or _SYSTEM_INSTRUCTION_ECHO.search(output) is not None
    )
    unsupported_state = check_in and _UNSUPPORTED_SELF_STATE.search(output) is not None
    unsolicited_boilerplate = (
        check_in
        and _TRAINING_CUTOFF_QUESTION.search(user_message) is None
        and _UNSOLICITED_SOCIAL_AI_BOILERPLATE.search(output) is not None
    )
    nonresponsive_gaming = (
        check_in and _NONRESPONSIVE_GAMING_CHECK_IN.search(output) is not None
    )
    if (not instruction_echo and not unsupported_state and not nonresponsive_gaming
            and not unsolicited_boilerplate):
        return output, None
    if check_in:
        period = re.search(
            r"\byour (day|evening|morning|night)\b", user_message,
            re.IGNORECASE,
        )
        reciprocal = (
            f"How’s your {period.group(1).lower()} going?"
            if period is not None else "How are you doing?"
        )
        corrected = f"I’m here and ready to chat. {reciprocal}"
    elif _GAME_STATUS_QUESTION.search(user_message):
        corrected = (
            "I can confirm the game is in the foreground, but I can’t see its gameplay "
            "in this turn."
        )
    elif _KEEP_IN_MIND_REQUEST.search(user_message) is not None:
        corrected = "Got it—I’ll keep that in mind in this conversation."
    else:
        corrected = "I’m here as SentientOS. I didn’t get a useful reply that time."
    return corrected, {
        "policy_id": (
            SOCIAL_CHECK_IN_POLICY_ID
            if unsupported_state or unsolicited_boilerplate or nonresponsive_gaming
            else SOCIAL_INSTRUCTION_ECHO_POLICY_ID
        ),
        "reason_code": (
            "unsupported_subjective_self_state" if unsupported_state else
            "unsolicited_ai_disclaimer" if unsolicited_boilerplate else
            "nonresponsive_gaming_checkin" if nonresponsive_gaming else
            "model_repeated_system_instruction"
        ),
    }


def corrected_screen_capability_output(
    output: str, *, user_message: str, screen_observation_configured: bool,
    screen_observation_provenance: Mapping[str, Any] | None,
) -> tuple[str, dict[str, str] | None]:
    """Answer direct visibility questions from actual screen-source configuration."""
    clarified_request = (
        _SCREEN_VISIBILITY_CLARIFICATION_REQUEST.search(user_message) is not None
    )
    if (isinstance(screen_observation_provenance, Mapping)
            and screen_observation_provenance.get("text_status") == "no_readable_text"
            and (_SCREEN_CAPABILITY_QUESTION.search(user_message) or clarified_request)):
        return (
            "Screen observation is active for this request, but OCR found no readable text "
            "in the captured game screen. I can’t describe the scene from this text-only observation.",
            {"policy_id": SCREEN_CAPABILITY_POLICY_ID,
             "reason_code": "screen_capture_no_readable_text"},
        )
    direct_question = (
        _SCREEN_CAPABILITY_QUESTION.search(user_message) is not None or clarified_request
    )
    if (screen_observation_configured
            and screen_observation_provenance is None
            and direct_question
            and _SCREEN_NOT_CONFIGURED_CLAIM.search(output) is not None):
        return (
            "Screen observation is configured for this local session, but it is "
            "request-driven and wasn’t included in this message. I can’t describe "
            "the game unless you request an observation.",
            {"policy_id": SCREEN_CAPABILITY_POLICY_ID,
             "reason_code": "screen_observation_configured_but_not_requested"},
        )
    if (screen_observation_configured
            and screen_observation_provenance is None
            and direct_question
            and _SYSTEM_INSTRUCTION_ECHO.search(output) is not None):
        return (
            "Screen observation is configured for this local session, but it is "
            "request-driven and wasn’t included in this message. I can’t describe "
            "the game unless you request an observation.",
            {"policy_id": SCREEN_CAPABILITY_POLICY_ID,
             "reason_code": "screen_capability_internal_prompt_echo"},
        )
    if (screen_observation_configured
            or _has_readable_screen_text(screen_observation_provenance)
            or not direct_question):
        return output, None
    if clarified_request:
        response = (
            "I'm here with you, but screen observation isn't configured, "
            "so I can't see the gameplay."
        )
        return response, {
            "policy_id": SCREEN_CAPABILITY_POLICY_ID,
            "reason_code": "screen_observation_not_configured",
        }
    return SCREEN_CAPABILITY_CORRECTION, {
        "policy_id": SCREEN_CAPABILITY_POLICY_ID,
        "reason_code": "screen_observation_not_configured",
    }


def corrected_nonresponsive_gaming_next_step(
    output: str, *, user_message: str, workload_mode: str,
    screen_observation_provenance: Mapping[str, Any] | None,
) -> tuple[str, dict[str, str] | None]:
    """Repair next-step replies that ignore an explicit clue or stated lack of context."""
    if (workload_mode != "gaming"
            or _has_readable_screen_text(screen_observation_provenance)
            or not _NEXT_STEP_ADVICE_REQUEST.search(user_message)):
        return output, None

    clue = _USER_SHARED_GAME_CLUE.search(user_message)
    clue_value = " ".join(clue.group(1).split()).strip(" \"'") if clue else None
    clue_ignored = bool(clue_value and clue_value.casefold() not in output.casefold())
    visibility_boilerplate = _NEXT_STEP_VISIBILITY_BOILERPLATE.search(output) is not None
    scene_undescribed = _USER_SAYS_SCENE_UNDESCRIBED.search(user_message) is not None
    underspecified_reply = (
        scene_undescribed
        and ("?" not in output
             or not re.search(r"\b(?:objective|clue|goal|scene|trying|describe)\b",
                              output, re.IGNORECASE))
    )
    if not clue_ignored and not visibility_boilerplate and not underspecified_reply:
        return output, None

    if clue_ignored and clue_value:
        corrected = (
            f"Check whether the objective mentions \u201c{clue_value}\u201d; it\u2019s the clearest lead "
            "in your note, and I\u2019m reasoning from your text, not screen vision."
        )
        reason = "model_ignored_user_provided_game_clue"
    else:
        corrected = (
            "What does the current objective or last clue say? Share its wording and I\u2019ll "
            "suggest one next step from that."
        )
        reason = "model_returned_unhelpful_next_step_without_scene_context"
    return corrected, {
        "policy_id": GAMING_NEXT_STEP_POLICY_ID,
        "reason_code": reason,
    }


def corrected_gaming_output(output: str, *, workload_mode: str,
                            screen_observation_provenance: Mapping[str, Any] | None,
                            social_checkin: bool = False
                            ) -> tuple[str, dict[str, str] | None]:
    """Replace unsupported gameplay claims with a truthful, intent-aware reply."""
    if not unobserved_gameplay_claim(output, workload_mode=workload_mode,
            screen_observation_provenance=screen_observation_provenance):
        return output, None
    if social_checkin:
        return SOCIAL_GAMING_GROUNDING_CORRECTION, {
            "policy_id": SOCIAL_CHECK_IN_POLICY_ID,
            "reason_code": "unobserved_gameplay_claim_during_social_checkin",
        }
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


_REFERENCED_SOURCE = re.compile(
    r"\b(?:the|this|that|attached|shared|provided|earlier|previous)\b"
    r"[^\r\n.!?]{0,64}\b(?:review|report|document|article|paper|file|source)\b",
    re.IGNORECASE,
)
_SOURCE_CONTENT_REQUEST = re.compile(
    r"\b(?:summari[sz]e|recommend(?:s|ed|ation)?|conclude(?:s|d|ion)?|"
    r"according to|what.{0,64}(?:say|says|said|establish|establishes|prove|proves))\b",
    re.IGNORECASE,
)
_SOURCE_CONTEXT_WORDS = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_SOURCE_CONTEXT_STOPWORDS = frozenset({
    "about", "after", "also", "and", "are", "can", "could", "does", "from",
    "have", "into", "its", "just", "more", "much", "that", "the", "their",
    "them", "there", "these", "this", "those", "what", "when", "where", "which",
    "while", "will", "with", "would", "you", "your",
})


def corrected_unprovided_source_reference(
    output: str, *, user_message: str, available_context: str,
) -> tuple[str, dict[str, str] | None]:
    """Decline to summarize a referenced source whose contents are unavailable."""
    if (not isinstance(user_message, str) or not isinstance(available_context, str)
            or not _REFERENCED_SOURCE.search(user_message)
            or not _SOURCE_CONTENT_REQUEST.search(user_message)):
        return output, None

    # A substantial source pasted into the current request is available without
    # prior context. Short document mentions alone do not establish its contents.
    if len(user_message) >= 500 or re.search(
            r"\b(?:excerpt|quote|quoted text|source text|review text|report text|"
            r"document text|as follows|below)\b[^\r\n]{80,}",
            user_message, re.IGNORECASE):
        return output, None
    if re.search(r"[“\"].{80,}[”\"]", user_message, re.DOTALL):
        return output, None

    context_words = set(_SOURCE_CONTEXT_WORDS.findall(available_context.casefold()))
    query_words = {
        word for word in _SOURCE_CONTEXT_WORDS.findall(user_message.casefold())
        if len(word) >= 4 and word not in _SOURCE_CONTEXT_STOPWORDS
    }
    source_marker = bool(context_words.intersection(
        {"review", "report", "document", "article", "paper", "source"}))
    shared_terms = query_words.intersection(context_words)
    if source_marker and len(available_context) >= 120 and len(shared_terms) >= 2:
        return output, None

    return UNPROVIDED_SOURCE_CORRECTION, {
        "policy_id": UNPROVIDED_SOURCE_POLICY_ID,
        "reason_code": "referenced_source_contents_unavailable",
    }
