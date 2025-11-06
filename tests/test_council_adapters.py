import os
import time

import pytest

from council_adapters import DeepSeekVoice, LocalVoice, OpenAIVoice, VoiceRateLimitError


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "rate-key")
    monkeypatch.setenv("OPENAI_API_KEY", "open-key")


def test_voice_adapters_produce_deterministic_output():
    local = LocalVoice("mesh-local", base_limit=5)
    deepseek = DeepSeekVoice("mesh-deepseek")
    openai = OpenAIVoice("mesh-openai")

    for voice in (local, deepseek, openai):
        ask = voice.ask("Synchronise trust vectors", trust=0.8)
        critique = voice.critique(ask.content, trust=0.8)
        vote = voice.vote({"job_id": "alpha", "responses": [], "critiques": []}, trust=0.8)
        assert ask.signature
        assert "reflection" in ask.content
        assert critique.metadata["statement_hash"]
        assert "signature" in vote.metadata
        voice._limiter.reset()  # type: ignore[attr-defined]
        repeat = voice.ask("Synchronise trust vectors", trust=0.8)
        assert repeat.content == ask.content


def test_voice_rate_limit_enforced():
    limited = LocalVoice("rate-test", base_limit=1)
    limited.ask("One call allowed", trust=1.0)
    with pytest.raises(VoiceRateLimitError):
        limited.ask("Second call fails", trust=1.0)
    limited._limiter.reset()  # type: ignore[attr-defined]
    limited.ask("Allowed again", trust=1.0)
