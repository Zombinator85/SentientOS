from sentientos.chat_response_grounding import (
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
