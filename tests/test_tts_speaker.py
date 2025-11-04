from __future__ import annotations

from sentientos.actuators.tts_speaker import TTSConfig, TTSSpeaker
from sentientos.metrics import MetricsRegistry


def test_tts_queue_and_rate_limit() -> None:
    spoken: list[str] = []

    def backend_factory(name: str):
        def speak(text: str) -> None:
            spoken.append(text)

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
    assert spoken == ["hello", "world"]
    assert len(spoken_records) == 2

    # Queue should now be empty and status should indicate success.
    status = speaker.status()
    assert status["queue_len"] == 0
    counters = metrics.snapshot()["counters"]
    assert counters["sos_tts_lines_spoken_total"] == 2.0
