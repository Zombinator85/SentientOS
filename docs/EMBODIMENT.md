# SentientOS Embodied Presence

This document covers the local perception and actuation stack used when
SentientOS operates on a single workstation.  The components are designed to be
opt-in, privacy aware, and governed by explicit budgets.

## Audio Ears (ASR Listener)

- **Config:** `audio.*`
- **Metrics:** `sos_asr_segments_total`, `sos_asr_latency_ms`, `sos_asr_dropped_total`
- **Smoke test:** `make asr-smoke`

The listener chunks microphone audio into short windows, applies RMS
voice-activity detection, and hands the samples to the configured backend
(`whisper_local`, `null`, or a custom callable).  The runtime clamps concurrent
transcriptions and enforces `max_minutes_per_hour` to avoid runaway processing.

## Voice Mouth (TTS Speaker)

- **Config:** `tts.*`
- **Metrics:** `sos_tts_lines_spoken_total`, `sos_tts_dropped_total`
- **Smoke test:** `make speak MSG="hello"`

Announcements are enqueued and deduplicated by correlation id.  The speaker
honours `max_chars_per_minute` and `cooldown_seconds` before dispatching to the
selected backend.  Queue length and active speaking state are surfaced through
`/admin/status`.

## Screen Awareness

- **Config:** `screen.*`
- **Metrics:** `sos_screen_captures_total`, `sos_screen_ocr_chars_total`
- **Smoke test:** `make screen-ocr-smoke TEXT="example"`

Periodic screen captures are hashed to avoid redundant OCR work.  Text is
redacted through the global privacy filters before appearing on dashboards or
metrics.  The `max_chars_per_minute` guard ensures OCR does not overwhelm the
system.

## GUI Control

- **Config:** `gui.*`
- **Safety modes:** `standard`, `permissive`, `locked`

The controller exposes simple intents (`move`, `click`, `type`).  Dangerous
patterns—such as typing secrets—are blocked unless the autonomy level is set to
`permissive`.  When the panic flag is raised (`AutonomyRuntime.activate_panic()`)
all GUI actions are rejected.

## Proactive Conversation

- **Config:** `conversation.*`
- **Metrics:** `sos_conversation_triggers_total{type=...}`

Triggers fire when ASR hears the configured name, when novelty spikes, or when
presence detectors activate.  Quiet hours suppress prompts entirely.  Rate
limits are enforced via `max_prompts_per_hour` and surfaced in module status.

## Memory Hygiene

Raw ASR transcripts and screen OCR snippets are stored through
`memory_manager.store_observation`.  The module keeps transcripts as text-only,
rotates daily digests under `glow/digests/`, and persists notable highlights in
`glow/highlights/<date>/`.  Storage policies are tunable via the helper functions
in `tools/storage_policy.py`.

## Dashboard Panels

When the modules are enabled, `/admin/status` shows live health for `ears`,
`voice`, `screen`, `gui`, `social`, and `conversation`.  `/admin/metrics`
exports the counters listed above and writes Prometheus text files to
`glow/metrics/*.prom` for external scraping.
