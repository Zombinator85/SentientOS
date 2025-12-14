# Cathedral Codex Entry: TTS Compatibility & Fallback Strategy for SentientOS

## Summary
Coqui TTS does not provide Python 3.12 wheels. Pip installs fail with:
```
ERROR: Could not find a version that satisfies the requirement TTS<1,>=0.14
```
SentientOS now keeps Python 3.12 as the standard and skips Coqui installation by default. Text‑to‑speech falls back to `pyttsx3` or `edge-tts` while Whisper handles speech‑to‑text.

## Implementation Notes
1. `requirements.txt` comments out the Coqui dependency.
2. `.env` sets `ENABLE_TTS=true` and `TTS_ENGINE=pyttsx3` (or `edge-tts`).
3. `sentientos/tts_bridge.py` loads whichever engine is available.
4. `voice_loop.py` uses Whisper for transcription and `tts_bridge.speak` for output when enabled.
5. Python 3.10 remains an optional alternative for full Coqui support.

## Status
Cathedral Launcher runs cleanly on Python 3.12. Whisper STT is operational. TTS via `pyttsx3` or `edge-tts` is optional but recommended.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
