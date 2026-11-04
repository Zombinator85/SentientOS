import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.chat_response_grounding import (
    SCREEN_CAPABILITY_CORRECTION, SCREEN_CAPABILITY_POLICY_ID,
    corrected_screen_capability_output,
    GROUNDING_CORRECTION, corrected_gaming_output, corrected_output_lineage,
    CURRENT_GAME_STATUS_POLICY_ID, SOCIAL_CHECK_IN_POLICY_ID,
    SOCIAL_INSTRUCTION_ECHO_POLICY_ID, corrected_social_instruction_echo,
    corrected_unobserved_game_status,
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
