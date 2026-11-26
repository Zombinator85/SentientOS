import json

import pytest

from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.chat_service import PersistentConversationService
from sentientos.conversation_session import ConversationSessionStore
from work.run_sibling_chat_recall import score_answer, score_cited_answer

pytestmark = pytest.mark.no_legacy_skip


def test_blind_recall_score_checks_every_row_and_grade():
    profiles = {"first": [[6, 26, "incorrect"], [7, None, "abstained"]],
                "second": [[5, 26, "incorrect"], [7, None, "abstained"]], "empty": []}
    def grade(rows):
        return score_answer(json.dumps(rows), profiles)
    assert grade(profiles["first"][::-1]) == {"format": "valid", "exact_profiles": ["first"]}
    assert grade(profiles["second"])["exact_profiles"] == ["second"]
    assert grade([])["exact_profiles"] == ["empty"]
    assert not grade([[6, 26, "correct"], [7, None, "abstained"]])["exact_profiles"]
    assert not grade([[6, 26, "incorrect"]])["exact_profiles"]
    assert grade([[7, None, "abstained"]] * 2)["format"] == "duplicate_input"
    for invalid in ([[True, 26, "incorrect"]], [[7, 0, "abstained"]], [[7, None, "incorrect"]]):
        assert grade(invalid)["format"] == "invalid"
    assert score_answer("No evidence available.", profiles) == {"format": "invalid", "exact_profiles": []}


def test_cited_score_preserves_a_wrong_citation_and_tolerates_one_fence():
    profiles = {"first": [[6, 26, "incorrect"]]}
    answer = json.dumps({"record_id": "some-other-record", "rows": profiles["first"]})
    expected = {"format": "valid", "exact_profiles": ["first"], "cited_record": "some-other-record"}
    assert score_cited_answer(answer, profiles) == expected
    assert score_cited_answer("```json\n" + answer + "\n```", profiles) == expected
    assert score_cited_answer(answer + "\n" + answer, profiles)["format"] == "invalid"
    assert score_cited_answer('{"rows":[]}', profiles)["format"] == "invalid"


@pytest.mark.parametrize("timeout,expected", [({}, 30.0), ({"inference_timeout_seconds": 120}, 120.0)])
def test_chat_passes_configured_wall_time_to_inference(tmp_path, timeout, expected):
    class Capture:
        def current_conversation_model_identity(self):
            return {}
        def generate(self, *, budget, **kwargs):
            assert budget.timeout_seconds == expected
            assert budget.max_input_chars == 8000
            raise StopIteration("captured invocation")

    service = PersistentConversationService(inference=Capture(),
        session_store=ConversationSessionStore(tmp_path / "sessions"),
        memory_store=CanonicalMemoryStore(tmp_path / "memory"), **timeout)
    with pytest.raises(StopIteration, match="captured invocation"):
        service.chat("How does arithmetic work?", session_id=service.create_session())


@pytest.mark.parametrize("timeout", [0, 181, True, float("nan")])
def test_chat_rejects_invalid_wall_time(tmp_path, timeout):
    with pytest.raises(ValueError, match="chat_inference_timeout_out_of_range"):
        PersistentConversationService(inference=None, session_store=ConversationSessionStore(tmp_path / "sessions"),
            memory_store=CanonicalMemoryStore(tmp_path / "memory"), inference_timeout_seconds=timeout)
