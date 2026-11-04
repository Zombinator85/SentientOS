from sentientos.chat_response_grounding import (
    SCREEN_CAPABILITY_CORRECTION, SCREEN_CAPABILITY_POLICY_ID,
    corrected_screen_capability_output,
    GROUNDING_CORRECTION, corrected_gaming_output, corrected_output_lineage,
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
