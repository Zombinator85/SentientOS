from __future__ import annotations

import pytest

from sentientos.gaming_workload_policy import GamingWorkloadPolicy
from sentientos.governed_local_model_invocation import LocalModelInvocationBudget

pytestmark = pytest.mark.no_legacy_skip


def test_normal_mode_preserves_the_requested_budget() -> None:
    requested = LocalModelInvocationBudget(max_input_chars=7000, max_output_chars=3000,
        max_new_tokens=256, timeout_seconds=24, max_calls_per_correlation=1)

    assert GamingWorkloadPolicy.constrain_budget("normal", requested) is requested


def test_gaming_mode_caps_each_turn_without_expanding_tighter_limits() -> None:
    requested = LocalModelInvocationBudget(max_input_chars=8000, max_output_chars=4000,
        max_new_tokens=512, timeout_seconds=30, max_calls_per_correlation=1)

    actual = GamingWorkloadPolicy.constrain_budget("gaming", requested)

    assert actual == LocalModelInvocationBudget(max_input_chars=4600, max_output_chars=1200,
        max_new_tokens=64, timeout_seconds=12, max_calls_per_correlation=1)


def test_gaming_mode_does_not_expand_an_already_tighter_budget() -> None:
    requested = LocalModelInvocationBudget(max_input_chars=1000, max_output_chars=500,
        max_new_tokens=32, timeout_seconds=5, max_calls_per_correlation=1)

    assert GamingWorkloadPolicy.constrain_budget("gaming", requested) == requested


def test_unknown_workload_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported_workload_mode"):
        GamingWorkloadPolicy.validate_mode("other")


def test_effective_mode_and_budget_are_recorded_in_invocation_lineage() -> None:
    requested = LocalModelInvocationBudget(max_new_tokens=512)

    budget, lineage = GamingWorkloadPolicy.apply_to_chat_invocation(
        "gaming", requested, {"serving_session_id": "session-1"})

    assert budget.max_new_tokens == 64
    assert lineage == {"serving_session_id": "session-1", "workload_mode": "gaming",
        "workload_evidence": {}, "workload_response_style": "gaming_chat_style_v13",
        "max_backend_threads": 2}


def test_normal_chat_does_not_receive_a_backend_thread_override() -> None:
    _, lineage = GamingWorkloadPolicy.apply_to_chat_invocation(
        "normal", LocalModelInvocationBudget(), {})

    assert "max_backend_threads" not in lineage


def test_gaming_chat_style_is_trusted_and_precedes_untrusted_history() -> None:
    prompt = ("[SYSTEM_INSTRUCTION]\nBase rules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}"
        "\n[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
    result = GamingWorkloadPolicy.apply_chat_response_style(prompt, "gaming")

    assert result.startswith("[SYSTEM_INSTRUCTION]\nBase rules.\n")
    assert result.index(GamingWorkloadPolicy.GAMING_CHAT_STYLE_INSTRUCTION) < result.index(
        "[VERIFIED_RUNTIME_CONTEXT]")
    assert result.endswith("[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
    assert "one direct sentence, about 20 words" in result
    assert "verified foreground app" in result
    assert "without screen evidence" in result
    assert "Honor corrections and rule-outs" in result
    assert "only when supported by the user's description or current screen OCR" in result
    assert "otherwise ask one concise clarifying question" in result
    assert "User-provided game details are usable conversational context" in result
    assert "Never invent map locations, objects, enemies, objectives, or events" in result
    assert "Fulfill requested form" in result
    assert "joke requests get jokes, not trivia or offers" in result
    assert "No unasked follow-up" in result
    assert GamingWorkloadPolicy.apply_chat_response_style(prompt, "normal") == prompt


def test_gaming_social_checkin_guidance_is_specific_and_precedes_history() -> None:
    prompt = ("[SYSTEM_INSTRUCTION]\nBase rules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}"
        "\n[SESSION_HISTORY_DATA]\nCURRENT_USER_MESSAGE: hi")

    result = GamingWorkloadPolicy.apply_chat_response_style(
        prompt, "gaming", social_checkin=True)

    guidance = GamingWorkloadPolicy.GAMING_SOCIAL_CHECKIN_INSTRUCTION
    assert guidance in result
    assert result.index(guidance) < result.index("[VERIFIED_RUNTIME_CONTEXT]")
    assert "answer the request first" in result
    assert "ask exactly one brief choice, e.g. 'Coffee or tea?'" in result
    assert "never an open-ended or repeated question" in result
    assert "no forced game reference, self-introduction, or helpdesk question" in result
    assert "claim gameplay sight or monitoring" in result
    assert "without CURRENT_SCREEN_OBSERVATION_UNTRUSTED" in result


def test_gaming_chat_style_rejects_an_unrecognized_prompt_layout() -> None:
    with pytest.raises(ValueError, match="gaming_chat_instruction_anchor_invalid"):
        GamingWorkloadPolicy.apply_chat_response_style("unstructured prompt", "gaming")


def test_user_text_resembling_prompt_marker_does_not_break_gaming_mode() -> None:
    prompt = ("[SYSTEM_INSTRUCTION]\nBase rules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}"
        "\n[SESSION_HISTORY_DATA]\nCURRENT_USER_MESSAGE: literal [SESSION_HISTORY_DATA]")

    result = GamingWorkloadPolicy.apply_chat_response_style(prompt, "gaming")

    assert result.count("[SESSION_HISTORY_DATA]") == 2
    assert result.index(GamingWorkloadPolicy.GAMING_CHAT_STYLE_INSTRUCTION) < result.index(
        "[VERIFIED_RUNTIME_CONTEXT]")
    assert result.endswith("CURRENT_USER_MESSAGE: literal [SESSION_HISTORY_DATA]")
