# Perception Bus Contract

The Perception Bus defines how external, offline adapters emit structured sensory
observations into SentientOS telemetry.

## Event Family

- `perception.*` is the canonical family for perception adapters.
- This baseline defines `perception.screen` and `perception.audio`.

## Required Common Fields

Every perception event payload **must** include:

- `event_type` (string; for this baseline: `"perception.screen"` or `"perception.audio"`)
- `timestamp` (string; ISO-8601 UTC)
- `source` (string; adapter subsystem source)
- `extractor_id` (string; adapter identifier, e.g. `"screen_adapter"`)
- `extractor_version` (string)
- `confidence` (number in `[0.0, 1.0]`)
- `privacy_class` (enum: `"public"`, `"internal"`, `"private"`, `"restricted"`, `"sensitive"`)
- `provenance` (object; model/version/host/runtime details)

`perception.screen` may also include:


- `active_app` (string)
- `window_title` (string)
- `focused_element_hint` (string)
- `text_excerpt` (string; only when privacy policy permits)
- `cursor_position` (object with optional `x`, `y` numeric members)
- `screen_geometry` (object with optional `width`, `height` numeric members)
- `degraded` (boolean)
- `degradation_reason` (string)


`perception.audio` payloads must include:

- `sample_rate_hz` (integer)
- `window_ms` (integer)
- `features` (object) with:
  - `rms_energy` (number)
  - `zcr` (number)
  - `spectral_centroid_hz` (number)
  - `spectral_rolloff_hz` (number)
  - `f0_hz_estimate` (number, optional)
  - `speech_prob` (number in `[0.0, 1.0]`, optional)
  - `tempo_bpm_estimate` (number, optional)
  - `pauses_per_min` (number, optional)
- `clipping_detected` (boolean)
- `channel_count` (integer)
- `device_hint` (string, optional)
- `raw_audio_retained` (boolean; defaults to `false`)
- `redaction_applied` (boolean)

`perception.audio` is explicitly prosodic telemetry. Semantic transcription is
not required, and raw audio must not be stored by default.

## Hard Constraints

1. Perception events are **non-privileged** signals.
2. They must **never** directly grant permissions.
3. They must **never** directly drive action selection.
4. They may influence phrasing and telemetry presentation only.
5. Any effect beyond phrasing/telemetry requires explicit whitelist coverage under
   `/vow` invariants.

## Retention Guidance

- Prefer retaining derived features over raw artifacts.
- Keep raw artifacts (e.g., screenshots, full text captures) short-lived and
  access-scoped.
- Long-term storage should bias toward low-sensitivity summaries:
  active app, window class/title hints, confidence, and provenance.
- If `privacy_class` is `restricted` or `sensitive`, redact or omit
  `text_excerpt` by default.
