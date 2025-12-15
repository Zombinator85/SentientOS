from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import List, Mapping

from sentientos.metrics import MetricsRegistry
from sentientos.perception.asr_listener import ASRListener, AudioConfig, CallableASRBackend


def _build_backend(verbose: bool) -> CallableASRBackend:
    def transcribe(samples: List[float], sample_rate: int) -> Mapping[str, object]:
        rms = math.sqrt(sum(sample * sample for sample in samples) / max(len(samples), 1))
        preview = " ".join(f"{sample:.2f}" for sample in samples[:8])
        if verbose:
            print(f"[mic-test] rms={rms:.3f} samples={len(samples)} preview={preview}")
        return {
            "text": f"mic rms={rms:.3f} len={len(samples)}",
            "confidence": 0.1,
            "language": "en",
        }

    return CallableASRBackend("mic-test", transcribe)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick microphone readiness probe.")
    parser.add_argument("--seconds", type=float, default=3.0, help="Seconds to listen before exiting")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Sample rate for capture")
    parser.add_argument("--pulse-path", type=Path, default=Path("/pulse/system.json"), help="Pulse system.json path")
    parser.add_argument("--verbose", action="store_true", help="Print waveform preview per chunk")
    args = parser.parse_args()

    metrics = MetricsRegistry()
    config = AudioConfig(
        enable=True,
        sample_rate=args.sample_rate,
        frame_seconds=0.2,
        buffer_seconds=args.seconds,
        silence_hangover_s=0.3,
        silence_rms=0.01,
    )

    listener = ASRListener(
        config,
        backend_factory=lambda _: _build_backend(args.verbose),
        metrics=metrics,
    )

    status = listener.run_microphone(stop_after=args.seconds, pulse_path=args.pulse_path)
    print(f"[mic-test] capture status: {status}")
    snapshot = metrics.snapshot()
    frames = snapshot.get("counters", {}).get("sos_asr_microphone_frames_total", 0)
    print(f"[mic-test] frames seen: {frames}")


if __name__ == "__main__":
    main()
