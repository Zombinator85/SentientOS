import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.chat_response_grounding import (
    SCREEN_CAPABILITY_CORRECTION, SCREEN_CAPABILITY_POLICY_ID,
    corrected_screen_capability_output,
    GROUNDING_CORRECTION, corrected_gaming_output, corrected_output_lineage,
    CURRENT_GAME_STATUS_POLICY_ID, SOCIAL_CHECK_IN_POLICY_ID,
    SOCIAL_INSTRUCTION_ECHO_POLICY_ID, SYSTEM_IDENTITY_POLICY_ID,
    corrected_social_instruction_echo, corrected_system_identity_output,
    corrected_unobserved_game_status,
    is_direct_screen_activity_question,
    unobserved_gameplay_claim,
)


def test_unsupported_gaming_claim_gets_explicitly_attributed_correction():
    text, correction = corrected_gaming_output(
        "Sure, keeping an eye on your gaming session.", workload_mode="gaming",
        screen_observation_provenance=None)
    assert text == GROUNDING_CORRECTION
    assert correction == {
        "policy_id": "gaming_unobserved_claim_correction_v1",
        "reason_code": "unobserved_gameplay_claim",
    }
    lineage = corrected_output_lineage(
        invocation_output_digest="a" * 64, text=text, output_truncated=False)
    assert lineage["status"] == "grounding_policy_fallback"
    assert lineage["invocation_output_digest"] == "a" * 64
    assert lineage["policy_id"] == correction["policy_id"]
    assert lineage["transcript_text_digest"]


def test_live_observed_unseen_gameplay_praise_gets_grounded_correction():
    text, correction = corrected_gaming_output(
        "Your gameplay is engaging; keep up the good work!",
        workload_mode="gaming", screen_observation_provenance=None)
    assert text == GROUNDING_CORRECTION
    assert correction is not None
    assert correction["reason_code"] == "unobserved_gameplay_claim"


def test_social_checkin_with_unsupported_gameplay_claim_gets_conversational_reply():
    corrected, attribution = corrected_gaming_output(
        "Sure, keeping an eye on your gaming session.",
        workload_mode="gaming", screen_observation_provenance=None,
        social_checkin=True,
    )
    assert corrected == "I’m here with you in SentientOS. How’s the session going?"
    assert attribution == {
        "policy_id": SOCIAL_CHECK_IN_POLICY_ID,
        "reason_code": "unobserved_gameplay_claim_during_social_checkin",
    }


def test_claim_to_share_unobserved_gameplay_gets_grounded_correction():
    output = "I can share what you are experiencing in Cronos."
    assert unobserved_gameplay_claim(
        output, workload_mode="gaming", screen_observation_provenance=None)
    corrected, attribution = corrected_gaming_output(
        output, workload_mode="gaming", screen_observation_provenance=None)
    assert corrected == GROUNDING_CORRECTION
    assert attribution is not None
    assert attribution["reason_code"] == "unobserved_gameplay_claim"


def test_unseen_specific_gameplay_event_praise_gets_grounded_correction():
    assert unobserved_gameplay_claim(
        "Nice dodge!", workload_mode="gaming", screen_observation_provenance=None)


def test_grounding_guard_preserves_supported_or_non_gaming_replies():
    assert not unobserved_gameplay_claim(
        "I heard you are saving batteries; I am here with you.",
        workload_mode="gaming", screen_observation_provenance=None)
    assert not unobserved_gameplay_claim(
        "I am enjoying your game.", workload_mode="normal",
        screen_observation_provenance=None)
    assert not unobserved_gameplay_claim(
        "I am enjoying your game.", workload_mode="gaming",
        screen_observation_provenance={"capture_digest": "b" * 64})


def test_screen_capability_question_does_not_claim_a_missing_source_can_be_enabled():
    text, correction = corrected_screen_capability_output(
        "You can enable additional permissions and I will see the game.",
        user_message="Can you see my game screen in this session?",
        screen_observation_configured=False, screen_observation_provenance=None)
    assert text == SCREEN_CAPABILITY_CORRECTION
    assert "I can’t see the game" in text
    assert "suggest next checks" in text
    assert "clues you share in this conversation" in text
    assert correction == {
        "policy_id": SCREEN_CAPABILITY_POLICY_ID,
        "reason_code": "screen_observation_not_configured",
    }


def test_combined_visibility_and_help_question_gets_both_parts_answered():
    text, correction = corrected_screen_capability_output(
        "I can help with that.",
        user_message=("Can you see the gameplay itself right now? If not, what help can you still give me?"),
        screen_observation_configured=False,
        screen_observation_provenance=None,
    )
    assert text == SCREEN_CAPABILITY_CORRECTION
    assert correction is not None



def test_live_game_status_uses_verified_foreground_without_inventing_scene_details():
    corrected, attribution = corrected_unobserved_game_status(
        "I'm unable to provide specific details about the current state of Cronos without observing the game screen. Let me know if you'd like to discuss gameplay strategies.",
        user_message="What can you actually tell me about Cronos right now?",
        verified_runtime_context={"workload": {
            "game_foreground": True,
            "configured_game_process_names": ["Cronos-Win64-Shipping.exe"],
        }},
        screen_observation_provenance=None,
    )
    assert corrected == (
        "Cronos is the foreground app. I don’t have a screen observation for this turn, "
        "so I can’t describe the gameplay."
    )
    assert attribution == {
        "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
        "reason_code": "foreground_only_no_screen_observation",
    }


def test_live_screen_activity_question_reports_unconfigured_source_accurately():
    corrected, attribution = corrected_unobserved_game_status(
        "Screen observation requires your permission.",
        user_message="Can you tell what's happening on screen in Cronos right now?",
        verified_runtime_context={
            "workload": {
                "game_foreground": True,
                "configured_game_process_names": ["Cronos-Win64-Shipping.exe"],
            },
            "capabilities": {"screen_observation": {"configured": False}},
        },
        screen_observation_provenance=None,
    )
    assert corrected == (
        "I can confirm Cronos is the foreground app, but screen observation "
        "isn’t configured in this session, so I can’t tell what’s happening on screen."
    )
    assert attribution == {
        "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
        "reason_code": "foreground_only_screen_observation_unconfigured",
    }


def test_visibility_clarification_request_is_grounded_without_screen_capture():
    message = (
        "Hey SentientOS, I am playing Cronos. Give me a quick friendly check-in, "
        "and be clear if you cannot see the gameplay."
    )
    assert is_direct_screen_activity_question(message)
    text, attribution = corrected_unobserved_game_status(
        "I can see that you are currently playing Cronos. Enjoy your game!",
        user_message=message,
        verified_runtime_context={
            "workload": {
                "game_foreground": True,
                "configured_game_process_names": ["Cronos-Win64-Shipping.exe"],
            },
            "capabilities": {"screen_observation": {"configured": False}},
        },
        screen_observation_provenance=None,
    )
    assert text == (
        "I\'m here with you, but screen observation isn\'t configured, "
        "so I can\'t see the gameplay."
    )
    assert attribution == {
        "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
        "reason_code": "foreground_only_screen_observation_unconfigured",
    }


def test_unconfigured_visibility_clarification_gets_a_direct_honest_reply():
    message = "Hey SentientOS, be clear if you cannot see the gameplay."
    text, attribution = corrected_screen_capability_output(
        "I can see the gameplay.",
        user_message=message,
        screen_observation_configured=False,
        screen_observation_provenance=None,
    )
    assert text == (
        "I'm here with you, but screen observation isn't configured, "
        "so I can't see the gameplay."
    )
    assert attribution == {
        "policy_id": SCREEN_CAPABILITY_POLICY_ID,
        "reason_code": "screen_observation_not_configured",
    }


def test_visibility_clarification_uses_current_observation_status():
    message = "Please be clear if you cannot see the game screen."
    text, attribution = corrected_unobserved_game_status(
        "I can see the game.",
        user_message=message,
        verified_runtime_context={
            "workload": {
                "game_foreground": True,
                "configured_game_process_names": ["Cronos-Win64-Shipping.exe"],
            },
            "capabilities": {"screen_observation": {"configured": True}},
        },
        screen_observation_provenance=None,
    )
    assert text == (
        "I\'m here with you, but I don\'t have a screen observation this turn, "
        "so I can\'t see the gameplay."
    )
    assert attribution == {
        "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
        "reason_code": "foreground_only_no_screen_observation",
    }


def test_live_game_status_fallback_requires_foreground_evidence_and_no_screen_evidence():
    output = "The game is open."
    assert corrected_unobserved_game_status(
        output, user_message="What can you tell me about Cronos right now?",
        verified_runtime_context={"workload": {"game_foreground": False}},
        screen_observation_provenance=None,
    ) == (output, None)
    assert corrected_unobserved_game_status(
        output, user_message="What can you tell me about Cronos right now?",
        verified_runtime_context={"workload": {
            "game_foreground": True,
            "configured_game_process_names": ["Cronos-Win64-Shipping.exe"],
        }},
        screen_observation_provenance={"capture_digest": "a" * 64},
    ) == (output, None)


def test_social_check_in_with_game_context_is_not_misread_as_a_screen_question():
    message = (
        "Hey SentientOS, how are you doing tonight? "
        "I am playing Cronos and could use some company."
    )
    assert not is_direct_screen_activity_question(message)
    assert corrected_unobserved_game_status(
        "", user_message=message,
        verified_runtime_context={"workload": {
            "game_foreground": True,
            "configured_game_process_names": ["Cronos-Win64-Shipping.exe"],
        }},
        screen_observation_provenance=None,
    ) == ("", None)
    assert is_direct_screen_activity_question(
        "What are you doing in Cronos right now?"
    )


def test_direct_game_activity_question_uses_foreground_only_evidence():
    corrected, attribution = corrected_unobserved_game_status(
        "I'm enjoying your gaming session with Cronos.",
        user_message="Can you tell what I am doing in Cronos right now, or only that the game is open?",
        verified_runtime_context={"workload": {
            "game_foreground": True,
            "configured_game_process_names": ["Cronos-Win64-Shipping.exe"],
        }},
        screen_observation_provenance=None,
    )
    assert corrected == (
        "I can confirm Cronos is the foreground app, but I can’t tell what you’re "
        "doing in it because I don’t have a screen observation this turn."
    )
    assert attribution == {
        "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
        "reason_code": "foreground_only_no_screen_observation",
    }


def test_social_instruction_echo_is_replaced_with_a_natural_reciprocal_greeting():
    corrected, attribution = corrected_social_instruction_echo(
        "I am here as SentientOS and ready to chat; do not claim feelings or infer user activity from a foreground app.",
        user_message="Hi, how is your evening going?",
    )
    assert corrected == "I’m here and ready to chat. How’s your evening going?"
    assert attribution == {
        "policy_id": SOCIAL_INSTRUCTION_ECHO_POLICY_ID,
        "reason_code": "model_repeated_system_instruction",
    }



def test_social_check_in_does_not_claim_an_unverified_subjective_state():
    corrected, attribution = corrected_social_instruction_echo(
        "I'm doing well, thanks for asking. How about you?",
        user_message="Hi, how is your evening going?",
    )
    assert corrected == "I’m here and ready to chat. How’s your evening going?"
    assert attribution == {
        "policy_id": SOCIAL_CHECK_IN_POLICY_ID,
        "reason_code": "unsupported_subjective_self_state",
    }


def test_social_checkin_replaces_unsolicited_ai_feelings_and_cutoff_boilerplate():
    corrected, attribution = corrected_social_instruction_echo(
        "As an AI language model, I don't have feelings, and my training cutoff is 2023.",
        user_message="Hi, how are you doing tonight?",
    )
    assert corrected == "I’m here and ready to chat. How are you doing?"
    assert attribution == {
        "policy_id": SOCIAL_CHECK_IN_POLICY_ID,
        "reason_code": "unsolicited_ai_disclaimer",
    }


def test_social_checkin_preserves_cutoff_answer_when_user_asks_for_it():
    output = "I don't have feelings, and my training cutoff is 2023."
    assert corrected_social_instruction_echo(
        output,
        user_message="Hi, how are you? Also, what is your training cutoff?",
    ) == (output, None)


def test_elliptical_social_check_in_does_not_claim_enjoyment():
    corrected, attribution = corrected_social_instruction_echo(
        "Enjoying your gaming session with Cronos. How can I assist further?",
        user_message="Hey, how are you doing in there?",
    )
    assert corrected == "I’m here and ready to chat. How are you doing?"
    assert attribution == {
        "policy_id": SOCIAL_CHECK_IN_POLICY_ID,
        "reason_code": "unsupported_subjective_self_state",
    }


def test_social_checkin_does_not_deflect_into_assumed_gaming_enjoyment():
    corrected, attribution = corrected_social_instruction_echo(
        "I am here in SentientOS. How about you enjoy your gaming session with Cronos?",
        user_message="Hey, how are you doing in there?",
    )
    assert corrected == "I’m here and ready to chat. How are you doing?"
    assert attribution == {
        "policy_id": SOCIAL_CHECK_IN_POLICY_ID,
        "reason_code": "nonresponsive_gaming_checkin",
    }


def test_social_instruction_echo_answers_game_status_without_claiming_visual_access():
    corrected, attribution = corrected_social_instruction_echo(
        "I am here as SentientOS and ready to chat; do not claim feelings or infer user activity from a foreground app.",
        user_message="What can you actually tell me about Cronos right now?",
    )
    assert corrected == (
        "I can confirm the game is in the foreground, but I can’t see its gameplay "
        "in this turn."
    )
    assert attribution is not None
    assert attribution["reason_code"] == "model_repeated_system_instruction"


def test_no_readable_screen_capture_does_not_count_as_gameplay_evidence():
    provenance = {"text_status": "no_readable_text", "capture_digest": "a" * 64}
    assert unobserved_gameplay_claim(
        "That was a great dodge!", workload_mode="gaming",
        screen_observation_provenance=provenance)

    corrected, attribution = corrected_unobserved_game_status(
        "The character is fighting a boss.",
        user_message="What is happening in Cronos right now?",
        verified_runtime_context={"workload": {
            "observation_status": "available", "game_foreground": True,
            "game_process_running": True,
            "configured_game_process_names": ["Cronos-Win64-Shipping.exe"],
            "effective_mode": "gaming"}},
        screen_observation_provenance=provenance)
    assert corrected == (
        "I can confirm Cronos is the foreground app, but OCR found no readable text "
        "in the captured game screen, so I can’t describe the scene from this text-only observation."
    )
    assert attribution == {
        "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
        "reason_code": "screen_capture_no_readable_text",
    }


def test_screen_capability_reports_when_configured_capture_has_no_readable_text():
    corrected, attribution = corrected_screen_capability_output(
        "I can see the game.", user_message="Can you see my game screen?",
        screen_observation_configured=True,
        screen_observation_provenance={"text_status": "no_readable_text"})
    assert corrected == (
        "Screen observation is active for this request, but OCR found no readable text "
        "in the captured game screen. I can’t describe the scene from this text-only observation."
    )
    assert attribution == {
        "policy_id": SCREEN_CAPABILITY_POLICY_ID,
        "reason_code": "screen_capture_no_readable_text",
    }


def test_screen_capability_correction_respects_configured_source_and_current_evidence():
    model_output = "I do not have a screen observation for this turn."
    assert corrected_screen_capability_output(
        model_output, user_message="Can you see my game screen?",
        screen_observation_configured=True, screen_observation_provenance=None
    ) == (model_output, None)
    assert corrected_screen_capability_output(
        model_output, user_message="Can you see my game screen?",
        screen_observation_configured=False,
        screen_observation_provenance={"capture_digest": "a" * 64}
    ) == (model_output, None)


def test_companion_name_is_not_misidentified_as_its_backend_model():
    output = (
        "I am currently called Qwen3 1.7B Q4_K_M gaming comparison "
        "(development only), and the open game is Cronos."
    )
    corrected, attribution = corrected_system_identity_output(
        output,
        user_message="What can I call you, and what game is open right now?",
        verified_runtime_context={
            "system": {"name": "SentientOS"},
            "active_model": {"configured_candidate_label":
                "Qwen3 1.7B Q4_K_M gaming comparison (development only)"},
            "workload": {"game_foreground": True,
                "configured_game_process_names": ["Cronos-Win64-Shipping.exe"]},
            "capabilities": {"screen_observation": {"included_this_turn": False}},
        },
    )

    assert corrected == (
        "I'm SentientOS, your local companion. Cronos is the foreground app. "
        "I don't have a screen observation for this turn, so I can't describe the gameplay."
    )
    assert attribution == {
        "policy_id": SYSTEM_IDENTITY_POLICY_ID,
        "reason_code": "backend_model_misidentified_as_companion",
    }


def test_social_check_in_correction_catches_configured_model_misidentification():
    output = "I’m Hermes 4. I don’t have feelings, but my training cutoff is 2023."
    corrected, attribution = corrected_system_identity_output(
        output,
        user_message="Hey, how are you doing in there?",
        verified_runtime_context={
            "assistant_role": "the active local model providing conversation inside SentientOS",
            "active_model": {"configured_candidate_label":
                "Nous Hermes 4 14B local development model"},
        },
    )

    assert corrected == (
        "I'm SentientOS, your local companion. "
        "I'm here and ready to chat. What's on your mind?"
    )
    assert attribution == {
        "policy_id": SYSTEM_IDENTITY_POLICY_ID,
        "reason_code": "backend_model_misidentified_as_companion",
    }


def test_companion_identity_correction_names_model_only_when_model_is_asked():
    output = "I'm Qwen3 1.7B."
    corrected, attribution = corrected_system_identity_output(
        output,
        user_message="Who are you, and which model is active?",
        verified_runtime_context={"active_model": {
            "configured_candidate_label": "Qwen3 1.7B Q4_K_M"}},
    )

    assert corrected == (
        "I'm SentientOS, your local companion. "
        "The configured model powering this conversation is Qwen3 1.7B Q4_K_M."
    )
    assert attribution is not None
    assert attribution["reason_code"] == "backend_model_misidentified_as_companion"


def test_correct_identity_or_non_identity_answers_are_preserved():
    context = {"active_model": {"configured_candidate_label": "Qwen3 1.7B"}}
    assert corrected_system_identity_output(
        "I'm SentientOS, your local companion.",
        user_message="Who are you?",
        verified_runtime_context=context,
    ) == ("I'm SentientOS, your local companion.", None)
    assert corrected_system_identity_output(
        "Qwen3 1.7B is the active backend.",
        user_message="Which model is active?",
        verified_runtime_context=context,
    ) == ("Qwen3 1.7B is the active backend.", None)


def test_game_running_question_uses_verified_background_process_presence():
    from sentientos.chat_response_grounding import GAME_PROCESS_STATUS_POLICY_ID

    corrected, attribution = corrected_unobserved_game_status(
        "Cronos is not currently running while you talk to me.",
        user_message="Hey SentientOS, is Cronos still running while I talk to you?",
        verified_runtime_context={"workload": {
            "game_foreground": False,
            "game_process_running": True,
            "configured_game_process_names": ["cronos-win64-shipping.exe"],
        }},
        screen_observation_provenance=None,
    )

    assert corrected == (
        "Cronos is still running in the background. I don’t have a screen observation for "
        "this turn, so I can’t describe the gameplay."
    )
    assert attribution == {
        "policy_id": GAME_PROCESS_STATUS_POLICY_ID,
        "reason_code": "allowlisted_game_process_running_no_screen_observation",
    }


def test_game_running_question_is_not_corrected_without_process_evidence():
    output = "Cronos may be running."
    assert corrected_unobserved_game_status(
        output,
        user_message="Is Cronos still running?",
        verified_runtime_context={"workload": {
            "game_foreground": False,
            "game_process_running": None,
            "configured_game_process_names": ["cronos-win64-shipping.exe"],
        }},
        screen_observation_provenance=None,
    ) == (output, None)


def test_current_workload_question_reports_verified_background_game_and_mode():
    message = (
        "What can you verify about my current workload right now, and what can you "
        "not observe? Please answer briefly and do not guess about the game screen."
    )
    corrected, attribution = corrected_unobserved_game_status(
        "The game is running, but I cannot see what is on screen.",
        user_message=message,
        verified_runtime_context={
            "workload": {
                "observation_status": "available",
                "configured_game_process_names": ["cronos-win64-shipping.exe"],
                "game_foreground": False,
                "game_process_running": True,
                "effective_mode": "gaming",
            },
            "capabilities": {
                "screen_observation": {"configured": False},
            },
        },
        screen_observation_provenance=None,
    )
    assert corrected == (
        "I can verify Cronos is running in the background, and SentientOS is in gaming mode. "
        "Screen observation isn’t configured in this session, so I can’t describe the gameplay."
    )
    assert attribution == {
        "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
        "reason_code": "verified_workload_context_screen_unavailable",
    }


def test_unprovided_review_reference_does_not_receive_invented_summary():
    from sentientos.chat_response_grounding import (
        UNPROVIDED_SOURCE_CORRECTION, UNPROVIDED_SOURCE_POLICY_ID,
        corrected_unprovided_source_reference,
    )

    text, attribution = corrected_unprovided_source_reference(
        "The review recommends performance optimization and stability testing.",
        user_message=(
            "I read the measurement review. In two short sentences, tell me what it "
            "recommends for Cronos testing and what the existing data can and cannot establish."
        ),
        available_context="Cronos is the foreground app. Gaming mode is active.",
    )
    assert text == UNPROVIDED_SOURCE_CORRECTION
    assert attribution == {
        "policy_id": UNPROVIDED_SOURCE_POLICY_ID,
        "reason_code": "referenced_source_contents_unavailable",
    }


def test_review_reference_is_answerable_when_source_content_is_in_history():
    from sentientos.chat_response_grounding import corrected_unprovided_source_reference

    source = (
        "The measurement review recommends randomized paired trials in the same Cronos "
        "scene. The archived captures show Qwen3 1.7B and Qwen2.5 3B near 19 to 21 ms "
        "p95, but they were not matched, so the data cannot rank the models."
    )
    text, attribution = corrected_unprovided_source_reference(
        "Use paired trials; the captures cannot rank the models.",
        user_message="What does the measurement review recommend and what can the data establish?",
        available_context=source,
    )
    assert text == "Use paired trials; the captures cannot rank the models."
    assert attribution is None


def test_long_message_with_pasted_review_is_not_rejected_as_unprovided():
    from sentientos.chat_response_grounding import corrected_unprovided_source_reference

    message = (
        "Summarize the attached review and its recommendations: "
        + "The review calls for randomized paired Cronos trials with frame-level timing. " * 12
    )
    text, attribution = corrected_unprovided_source_reference(
        "The review recommends paired trials.", user_message=message,
        available_context="",
    )
    assert text == "The review recommends paired trials."
    assert attribution is None


def test_combined_game_status_and_visibility_reports_verified_background_process():
    message = (
        "What do you currently know about Cronos on this computer, and can you see "
        "the game screen? Be concise and distinguish running from foreground."
    )
    assert is_direct_screen_activity_question(message)
    text, attribution = corrected_unobserved_game_status(
        "I cannot see the screen.",
        user_message=message,
        verified_runtime_context={
            "workload": {
                "observation_status": "available",
                "game_foreground": False,
                "game_process_running": True,
                "effective_mode": "gaming",
                "configured_game_process_names": ["cronos-win64-shipping.exe"],
            },
            "capabilities": {"screen_observation": {"configured": False}},
        },
        screen_observation_provenance=None,
    )
    assert text == (
        "I can verify Cronos is running in the background, and SentientOS is in gaming mode. "
        "Screen observation isn’t configured in this session, so I can’t describe the gameplay."
    )
    assert attribution == {
        "policy_id": CURRENT_GAME_STATUS_POLICY_ID,
        "reason_code": "verified_workload_context_screen_unavailable",
    }
