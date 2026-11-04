import pytest

from sentientos.perception.screen_text_delta import (
    MAX_DELTA_LINES,
    build_ocr_text_line_delta,
    validate_ocr_text_line_delta,
)


def test_delta_reports_literal_added_and_removed_lines_and_validates_current_text():
    delta = build_ocr_text_line_delta("Quest\nReach tower", "Quest\nFind key")

    assert delta["added_lines"] == ["Find key"]
    assert delta["removed_lines"] == ["Reach tower"]
    assert delta["truncated"] is False
    assert validate_ocr_text_line_delta(delta, current_text="Quest\nFind key") == delta
    with pytest.raises(ValueError, match="contract_invalid"):
        validate_ocr_text_line_delta(delta, current_text="Quest\nDifferent")


def test_delta_bounds_line_count_and_length():
    previous = "\n".join(f"old {index}" for index in range(12))
    current = "\n".join("x" * 200 + f" {index}" for index in range(12))
    delta = build_ocr_text_line_delta(previous, current)

    assert len(delta["added_lines"]) == MAX_DELTA_LINES
    assert len(delta["removed_lines"]) == MAX_DELTA_LINES
    assert all(len(line) <= 160 for line in delta["added_lines"])
    assert delta["truncated"] is True


def test_delta_rejects_oversized_input():
    with pytest.raises(ValueError, match="input_invalid"):
        build_ocr_text_line_delta("a" * 1201, "b")



def test_delta_is_included_in_prompt_only_as_validated_untrusted_screen_data(tmp_path):
    from sentientos.conversation_session import ConversationSessionStore, assemble_local_chat_context

    sessions = ConversationSessionStore(tmp_path / "sessions")
    session = sessions.create(model_identity={})
    history = sessions.reconstruct(session["session_id"], budget_chars=100)
    delta = build_ocr_text_line_delta("Quest\nFind the key", "Quest\nOpen the gate")
    prompt = assemble_local_chat_context(
        history=history,
        memory_snapshot={"memories": []},
        current_message="What changed?",
        screen_observation={
            "text": "Quest\nOpen the gate",
            "capture_digest": "a" * 64,
            "capture_scope": "allowlisted_foreground_game_client_area",
            "text_change_kind": "changed",
            "text_delta": delta,
        },
    )

    assert "[CURRENT_SCREEN_OBSERVATION_UNTRUSTED]" in prompt
    assert '"added_lines":["Open the gate"]' in prompt
    assert '"removed_lines":["Find the key"]' in prompt
