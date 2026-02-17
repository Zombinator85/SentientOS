# Embodied Perception Reconnaissance Report

## Scope scanned
- Adapters: `scripts/perception/screen_adapter.py`, `audio_adapter.py`, `vision_adapter.py`, `gaze_adapter.py`.
- Contracts/specs: `docs/PERCEPTION_BUS.md`, `docs/PULSE_BUS.md`, `docs/schemas/perception_bus.schema.json`, `sentientos/streams/schema_registry.py`.
- Drift/status tooling: `scripts/contract_drift.py`, `scripts/emit_contract_status.py`, `scripts/detect_perception_schema_drift.py`, `Makefile`.
- Tests/docs touching perception, drift, and status rollups.

## A) What already exists and where?
- `perception.screen` already exists as an event type and is emitted by `scripts/perception/screen_adapter.py`.
- Existing screen payload support includes `active_app`, `window_title`, `focused_element_hint`, `text_excerpt`, `cursor_position`, `screen_geometry`, `degraded`, and `degradation_reason`.
- Existing perception schema/docs include event family coverage for `perception.screen`, `perception.audio`, `perception.vision`, and `perception.gaze` in `docs/PERCEPTION_BUS.md`, `docs/schemas/perception_bus.schema.json`, and `sentientos/streams/schema_registry.py`.
- Privacy and retention guardrails already exist in docs and in audio/vision/gaze adapters (raw-retained flags default false; quarantine reference pattern for raw artifacts).
- Contract drift/status tooling already includes perception domain (`scripts/contract_drift.py`, `scripts/emit_contract_status.py`) and required-key drift detection (`scripts/detect_perception_schema_drift.py`).

## B) What overlaps the “screen_context” idea?
- Current `perception.screen` already serves as “screen context” baseline via app/window/cursor/geometry/focus hints.
- There is no separate `perception.screen_context` type in schemas/docs/registry.
- Existing fields overlap most of the concept; missing pieces are mostly richer optional semantics (browser domain/url gating, UI context, redaction metadata, process/window class split, explicit artifact retention flag).

## C) Which missing pieces remain?
- `perception.screen` contract lacks explicit optional fields requested for richer semantics:
  - `window_class`/`process_name`, `browser_domain`, `browser_url_full` (strictly gated), `ui_context`, `redaction_applied`/`redaction_notes`, explicit `raw_artifact_retained`.
- Screen adapter lacks:
  - browser domain extraction,
  - full URL double-gating (`privacy_class=private` + explicit flag),
  - explicit include flags for domain/url/text excerpt,
  - explicit redaction metadata and retention semantics aligned with audio/vision pattern.
- `docs/PULSE_BUS.md` is stale relative to current supported perception events (still says only screen/audio).
- No obvious lightweight “perception → affect telemetry” consumer found behind `ENABLE_AFFECT_INFERENCE`.
- No umbrella `make embodied-status` target exists.

## D) Recommendation: extend `perception.screen` vs introduce `perception.screen_context`
**Recommendation: extend `perception.screen` only.**

Rationale:
1. The repository already treats `perception.screen` as the canonical screen awareness envelope.
2. Contract drift tooling and schema baselines already track this type; adding a new type would create avoidable duplication and migration burden.
3. Required improvements are additive optional fields and stricter privacy gating, which fit naturally into the existing event contract.
4. No evidence of a hard requirement that cannot be represented inside `perception.screen`.
