from __future__ import annotations

from sentientos.metrics import MetricsRegistry
from sentientos.perception.asr_listener import (
    ASRListener,
    AudioConfig,
    CallableASRBackend,
)


def test_asr_listener_vad_and_budget() -> None:
    metrics = MetricsRegistry()

    def backend_fn(audio: list[float], sample_rate: int) -> dict[str, object]:
        return {"text": f"heard-{len(audio)}", "confidence": 0.8, "language": "en"}

    listener = ASRListener(
        AudioConfig(
            enable=True,
            chunk_seconds=1.0,
            max_minutes_per_hour=0.05,
            max_concurrent=1,
        ),
        backend_factory=lambda _: CallableASRBackend("fake", backend_fn),
        metrics=metrics,
    )

    # Quiet audio should be ignored by the RMS VAD.
    silence = [0.0] * 1600
    assert listener.process_samples(silence, sample_rate=1600) is None

    loud = [0.2] * 1600
    observation = listener.process_samples(loud, sample_rate=1600)
    assert observation is not None
    assert observation["modality"] == "audio"
    assert observation["transcript"].startswith("heard")

    # Second loud chunk should breach the minute budget and be dropped.
    dropped = listener.process_samples(loud, sample_rate=1600)
    assert dropped is None

    snapshot = metrics.snapshot()
    counters = snapshot["counters"]
    assert counters["sos_asr_segments_total"] == 1.0
    assert counters["sos_asr_dropped_total"] >= 1.0
