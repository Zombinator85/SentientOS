import json
from pathlib import Path
from typing import Iterable, Sequence, Tuple

import pytest

from sentientos.metrics import MetricsRegistry
from sentientos.perception.asr_listener import (
    ASRListener,
    AudioConfig,
    CallableASRBackend,
)


pytestmark = pytest.mark.no_legacy_skip


def _backend(recorder: list[Tuple[int, int]]):
    def _fn(audio: list[float], sample_rate: int) -> dict[str, object]:
        recorder.append((len(audio), sample_rate))
        return {"text": f"len-{len(audio)}", "confidence": 0.9, "language": "en"}

    return CallableASRBackend("microphone-test", _fn)


def test_microphone_buffers_and_trims_silence(tmp_path: Path) -> None:
    processed: list[Tuple[int, int]] = []
    listener = ASRListener(
        AudioConfig(
            enable=True,
            chunk_seconds=2.0,
            max_minutes_per_hour=5.0,
            max_concurrent=1,
            sample_rate=10,
            frame_seconds=0.1,
            buffer_seconds=1.0,
            silence_rms=0.05,
            silence_hangover_s=0.2,
        ),
        backend_factory=lambda _: _backend(processed),
        metrics=MetricsRegistry(),
    )

    frames: Iterable[Tuple[Sequence[float], int]] = [
        ([0.0] * 5, 10),
        ([0.2] * 5, 10),
        ([0.25] * 5, 10),
        ([0.0] * 5, 10),
        ([0.0] * 5, 10),
    ]
    status = listener.run_microphone(audio_source=frames, pulse_path=tmp_path / "pulse" / "system.json", mode="LOCAL_OWNER")

    assert processed, "spoken frames should be forwarded to the backend"
    assert processed[0][0] <= 50  # trimmed to buffer window
    assert status["state"] == "idle"

    pulse_state = json.loads((tmp_path / "pulse" / "system.json").read_text())
    assert pulse_state["devices"]["microphone"]["state"] == "idle"


def test_microphone_silence_is_ignored(tmp_path: Path) -> None:
    processed: list[Tuple[int, int]] = []
    listener = ASRListener(
        AudioConfig(enable=True, silence_rms=0.1, sample_rate=8, frame_seconds=0.05),
        backend_factory=lambda _: _backend(processed),
        metrics=MetricsRegistry(),
    )

    frames: Iterable[Tuple[Sequence[float], int]] = [([0.0] * 8, 8), ([0.0] * 8, 8), ([0.0] * 8, 8)]
    listener.run_microphone(audio_source=frames, pulse_path=tmp_path / "pulse" / "system.json", mode="LOCAL_OWNER")

    assert not processed, "silence-only capture should not trigger ASR"


def test_microphone_permission_gating(tmp_path: Path) -> None:
    processed: list[Tuple[int, int]] = []
    listener = ASRListener(
        AudioConfig(enable=True, sample_rate=8, frame_seconds=0.05),
        backend_factory=lambda _: _backend(processed),
        metrics=MetricsRegistry(),
    )
    frames: Iterable[Tuple[Sequence[float], int]] = [([0.2] * 8, 8)]
    status = listener.run_microphone(audio_source=frames, pulse_path=tmp_path / "pulse" / "system.json", mode="DEFAULT")

    assert not processed
    assert status["state"] == "muted"
    pulse_state = json.loads((tmp_path / "pulse" / "system.json").read_text())
    assert pulse_state["devices"]["microphone"]["state"] == "muted"
