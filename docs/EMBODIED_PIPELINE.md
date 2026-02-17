# Embodied Perception Pipeline

## Adapters

- `scripts/perception/screen_adapter.py` emits `perception.screen`.
- `scripts/perception/audio_adapter.py` emits `perception.audio`.
- `scripts/perception/vision_adapter.py` emits `perception.vision`.
- `scripts/perception/gaze_adapter.py` emits `perception.gaze`.

All adapters publish telemetry onto the pulse bus and follow the perception
schema contract in `docs/schemas/perception_bus.schema.json`.

## Privacy classes and retention

- Privacy classes: `public`, `internal`, `private`, `restricted`, `sensitive`.
- Default policy is derived telemetry only; raw artifacts are off by default.
- When raw artifacts are retained, adapters should quarantine raw material and
  emit only reference pointers in payloads.
- Screen-specific sensitive fields (`browser_url_full`, `text_excerpt`) require
  explicit operator flags and privacy gating.

## Perception → affect derivation (optional)

Affect inference is optional, off by default, and enabled only via
`ENABLE_AFFECT_INFERENCE=1`.

- Consumer reads perception prosody/geometry telemetry.
- Consumer writes bounded affect telemetry with confidence/provenance.
- Derived affect metadata is expression-only (phrasing/telemetry context).

## Non-privileged constraints

Perception and perception-derived affect are non-privileged:

- cannot grant privileges,
- cannot select or trigger actions,
- cannot override policy gates,
- may influence phrasing/telemetry only unless explicitly whitelisted in `/vow`.
