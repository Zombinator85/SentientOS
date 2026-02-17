from __future__ import annotations

import argparse
import json
import math
import platform
import socket
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.daemons import pulse_bus

EXTRACTOR_ID = "audio_adapter"
EXTRACTOR_VERSION = "1"
PRIVACY_CHOICES = ("public", "internal", "private")
EVENT_TYPE = "perception.audio"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_import_numpy() -> Any | None:
    try:
        import numpy as np
    except Exception:
        return None
    return np


def _capture_with_sounddevice(sample_rate_hz: int, window_ms: int, channel_count: int) -> tuple[Any | None, str | None]:
    np = _safe_import_numpy()
    if np is None:
        return None, "numpy unavailable for sounddevice capture"
    try:
        import sounddevice as sd
    except Exception:
        return None, "sounddevice unavailable"

    frames = int(sample_rate_hz * (window_ms / 1000.0))
    try:
        recording = sd.rec(frames, samplerate=sample_rate_hz, channels=channel_count, dtype="float32")
        sd.wait()
    except Exception as exc:
        return None, f"sounddevice capture failed: {exc}"

    data = np.asarray(recording, dtype=np.float64)
    if data.ndim == 2 and data.shape[1] > 1:
        data = data.mean(axis=1)
    elif data.ndim == 2:
        data = data[:, 0]
    return data, None


def _capture_with_pyaudio(sample_rate_hz: int, window_ms: int, channel_count: int) -> tuple[Any | None, str | None]:
    np = _safe_import_numpy()
    if np is None:
        return None, "numpy unavailable for pyaudio capture"
    try:
        import pyaudio
    except Exception:
        return None, "pyaudio unavailable"

    frames = int(sample_rate_hz * (window_ms / 1000.0))
    pa = pyaudio.PyAudio()
    stream = None
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=channel_count,
            rate=sample_rate_hz,
            input=True,
            frames_per_buffer=frames,
        )
        raw = stream.read(frames, exception_on_overflow=False)
    except Exception as exc:
        return None, f"pyaudio capture failed: {exc}"
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        pa.terminate()

    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if channel_count > 1 and data.size >= channel_count:
        data = data.reshape((-1, channel_count)).mean(axis=1)
    return data, None


def _capture_audio(sample_rate_hz: int, window_ms: int, channel_count: int) -> tuple[Any | None, str | None]:
    data, err = _capture_with_sounddevice(sample_rate_hz, window_ms, channel_count)
    if data is not None:
        return data, None
    sounddevice_err = err
    data, err = _capture_with_pyaudio(sample_rate_hz, window_ms, channel_count)
    if data is not None:
        return data, None
    return None, f"{sounddevice_err}; {err}"


def _estimate_pitch_hz(samples: Any, sample_rate_hz: int) -> float | None:
    np = _safe_import_numpy()
    if np is None or len(samples) < 32:
        return None
    centered = samples - np.mean(samples)
    energy = float(np.sum(centered * centered))
    if energy <= 1e-9:
        return None
    corr = np.correlate(centered, centered, mode="full")
    corr = corr[corr.size // 2 :]

    min_lag = max(1, int(sample_rate_hz / 400))
    max_lag = min(len(corr) - 1, int(sample_rate_hz / 60))
    if max_lag <= min_lag:
        return None
    window = corr[min_lag:max_lag]
    if window.size == 0:
        return None
    lag = int(np.argmax(window)) + min_lag
    peak = float(corr[lag])
    if peak <= 0.05 * float(corr[0]):
        return None
    return float(sample_rate_hz / lag)


def _feature_extract(samples: Any, sample_rate_hz: int, window_ms: int) -> tuple[dict[str, float], bool, bool]:
    np = _safe_import_numpy()
    if np is None:
        return {"rms_energy": 0.0, "zcr": 0.0, "spectral_centroid_hz": 0.0, "spectral_rolloff_hz": 0.0}, False, False

    if samples is None or len(samples) == 0:
        return {"rms_energy": 0.0, "zcr": 0.0, "spectral_centroid_hz": 0.0, "spectral_rolloff_hz": 0.0}, False, False

    samples = np.asarray(samples, dtype=np.float64)
    rms = float(np.sqrt(np.mean(samples * samples)))
    zero_crossings = float(np.mean(np.abs(np.diff(np.signbit(samples))))) if len(samples) > 1 else 0.0

    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / sample_rate_hz)
    spectral_sum = float(np.sum(spectrum))
    if spectral_sum > 0:
        centroid = float(np.sum(freqs * spectrum) / spectral_sum)
        cumulative = np.cumsum(spectrum)
        rolloff_idx = int(np.searchsorted(cumulative, 0.85 * cumulative[-1]))
        rolloff = float(freqs[min(rolloff_idx, len(freqs) - 1)])
    else:
        centroid = 0.0
        rolloff = 0.0

    pitch = _estimate_pitch_hz(samples, sample_rate_hz)
    clipping_detected = bool(np.any(np.abs(samples) >= 0.99))
    speech_prob = min(1.0, max(0.0, (rms * 2.0) * (1.0 - min(1.0, zero_crossings))))
    pauses_per_min = float(60000.0 / window_ms) if rms < 0.02 and window_ms > 0 else 0.0

    features: dict[str, float] = {
        "rms_energy": rms,
        "zcr": zero_crossings,
        "spectral_centroid_hz": centroid,
        "spectral_rolloff_hz": rolloff,
        "speech_prob": float(speech_prob),
        "pauses_per_min": pauses_per_min,
    }
    if pitch is not None and math.isfinite(pitch):
        features["f0_hz_estimate"] = float(pitch)

    return features, clipping_detected, True


def _write_raw_snippet(samples: Any, *, sample_rate_hz: int, privacy_class: str, output_dir: Path) -> str | None:
    np = _safe_import_numpy()
    if np is None or samples is None:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"{stamp}_{privacy_class}.wav"
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(pcm.tobytes())
    return str(path)


def build_perception_payload(
    *,
    privacy_class: str,
    sample_rate_hz: int,
    window_ms: int,
    channel_count: int,
    retain_raw: bool,
    raw_output_dir: Path,
    device_hint: str | None,
) -> dict[str, Any]:
    samples, capture_error = _capture_audio(sample_rate_hz, window_ms, channel_count)
    features, clipping_detected, extracted = _feature_extract(samples, sample_rate_hz, window_ms)

    confidence = 0.75 if extracted else 0.15
    degraded = capture_error is not None
    payload: dict[str, Any] = {
        "event_type": EVENT_TYPE,
        "timestamp": _iso_now(),
        "source": "local.microphone",
        "extractor_id": EXTRACTOR_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "confidence": confidence,
        "privacy_class": privacy_class,
        "provenance": {
            "extractor": EXTRACTOR_ID,
            "extractor_version": EXTRACTOR_VERSION,
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
        "sample_rate_hz": sample_rate_hz,
        "window_ms": window_ms,
        "features": features,
        "clipping_detected": clipping_detected,
        "channel_count": channel_count,
        "raw_audio_retained": bool(retain_raw),
        "redaction_applied": not retain_raw,
        "degraded": degraded,
    }
    if capture_error:
        payload["degradation_reason"] = capture_error
    if device_hint:
        payload["device_hint"] = device_hint
    if retain_raw:
        raw_ref = _write_raw_snippet(samples, sample_rate_hz=sample_rate_hz, privacy_class=privacy_class, output_dir=raw_output_dir)
        if raw_ref:
            payload["raw_audio_reference"] = raw_ref
    return payload


def emit_pulse(payload: dict[str, Any], *, output_log: Path) -> dict[str, Any]:
    event = {
        "timestamp": payload["timestamp"],
        "source_daemon": EXTRACTOR_ID,
        "event_type": EVENT_TYPE,
        "payload": payload,
        "priority": "info",
        "event_origin": "local",
        "context": {"privacy_class": payload["privacy_class"]},
    }
    try:
        published = pulse_bus.publish(event)
        return {"published": True, "event": published}
    except Exception as exc:
        output_log.parent.mkdir(parents=True, exist_ok=True)
        with output_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return {
            "published": False,
            "error": str(exc),
            "fallback_log": str(output_log),
            "event": event,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit perception.audio events from offline microphone prosody features")
    parser.add_argument("--privacy-class", default="internal", choices=PRIVACY_CHOICES)
    parser.add_argument("--sample-rate-hz", type=int, default=16000)
    parser.add_argument("--window-ms", type=int, default=500)
    parser.add_argument("--channel-count", type=int, default=1)
    parser.add_argument("--retain-raw", action="store_true", default=False)
    parser.add_argument("--raw-output-dir", default="glow/perception/quarantine/audio_raw")
    parser.add_argument("--device-hint", default=None)
    parser.add_argument("--iterations", type=int, default=1, help="number of windows to capture; 0 means run forever")
    parser.add_argument("--output-log", default="glow/perception/perception_audio_events.jsonl")
    args = parser.parse_args(argv)

    count = 0
    while True:
        payload = build_perception_payload(
            privacy_class=args.privacy_class,
            sample_rate_hz=args.sample_rate_hz,
            window_ms=args.window_ms,
            channel_count=args.channel_count,
            retain_raw=bool(args.retain_raw),
            raw_output_dir=Path(args.raw_output_dir),
            device_hint=args.device_hint,
        )
        result = emit_pulse(payload, output_log=Path(args.output_log))
        print(json.dumps(result, sort_keys=True))
        count += 1
        if args.iterations > 0 and count >= args.iterations:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
