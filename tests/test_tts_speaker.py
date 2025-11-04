from __future__ import annotations

from sentientos.actuators.tts_speaker import TTSConfig, TTSPersonality, TTSSpeaker
from sentientos.metrics import MetricsRegistry


def test_tts_queue_and_rate_limit() -> None:
    spoken: list[tuple[str, dict | None]] = []

    def backend_factory(name: str):
        def speak(text: str, **kwargs) -> None:
            spoken.append((text, kwargs.get("voice_params")))

        return speak

    metrics = MetricsRegistry()
    speaker = TTSSpeaker(
        TTSConfig(enable=True, max_chars_per_minute=15, cooldown_seconds=0.0),
        backend_factory=backend_factory,
        metrics=metrics,
    )

    speaker.enqueue("hello")
    speaker.enqueue("world")
    speaker.enqueue("world", dedupe=True)
    spoken_records = speaker.drain()
    assert [entry[0] for entry in spoken] == ["hello", "world"]
    assert len(spoken_records) == 2

    # Queue should now be empty and status should indicate success.
    status = speaker.status()
    assert status["queue_len"] == 0
    counters = metrics.snapshot()["counters"]
    assert counters["sos_tts_lines_spoken_total"] == 2.0


def test_tts_mood_modulation() -> None:
    captured: list[dict | None] = []

    def backend_factory(name: str):
        def speak(text: str, **kwargs) -> None:
            captured.append(kwargs.get("voice_params"))

        return speak

    metrics = MetricsRegistry()
    personality = TTSPersonality(expressiveness="high", baseline_mood="calm", dynamic_voice=True)
    moods = iter(["joyful"])
    speaker = TTSSpeaker(
        TTSConfig(enable=True, cooldown_seconds=0.0, personality=personality),
        backend_factory=backend_factory,
        metrics=metrics,
        mood_provider=lambda: next(moods, "joyful"),
    )

    speaker.enqueue("Story")
    speaker.drain()
    assert captured
    modifiers = captured[0]
    assert modifiers is not None
    assert modifiers["pitch"] > 0
    sad_params = speaker.voice_parameters_for_mood("sad")
    assert sad_params["pitch"] < 0
