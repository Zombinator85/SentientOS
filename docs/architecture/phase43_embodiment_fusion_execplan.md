# Phase 43 ExecPlan: Canonical Embodiment Fusion Spine

## 1) Current Phase-42 telemetry bridge state
- Legacy perception modules emit pulse-compatible telemetry through `sentientos.perception_api`.
- Canonical Phase-42 envelope includes modality, source/source_module, observation payload, privacy class, raw retention, and non-authority flags.
- Bridged modalities currently include screen, audio, vision, multimodal, and feedback.

## 2) Target fusion snapshot shape
- Introduce bounded snapshot schema `embodiment.snapshot.v1`.
- Snapshot includes deterministic `snapshot_id`, timestamp, modality coverage, source refs, privacy/retention posture, risk flags, per-modality context extracts, and explicit non-authority contract flags.

## 3) Source event fields consumed
- `event_type`, `modality`, `timestamp`, `source`, `source_module`
- `observation`
- `privacy_class`, `raw_retention`
- `can_trigger_actions`, `can_write_memory`
- `correlation_id` when present (event-level or observation-level)

## 4) Modality coverage
- Required in Phase 43: `screen`, `audio`, `vision`, `multimodal`, `feedback`.
- Optional extension point included for `gaze` events when available through telemetry-only helpers.

## 5) Privacy/retention handling
- Snapshot preserves union of observed `privacy_class` values.
- Snapshot exposes `raw_retention_present`, `raw_retention_requested`, and `raw_retention_default`.
- Sensitive modality presence is surfaced as a risk flag (`biometric_or_emotion_sensitive`).

## 6) Provenance/correlation strategy
- Generate stable source event refs by hashing normalized event provenance+payload material.
- Preserve and expose `source_modules` and `source_event_refs` in snapshots.
- Correlate by explicit `correlation_id`; fall back to `uncorrelated` grouping.

## 7) Non-authority boundaries
- Fusion module is derived-only and telemetry-only.
- It does not admit work, execute/route work, write memory, trigger feedback/actions, mutate control-plane state, or perform hardware capture.
- Contract encoded directly in snapshot flags (`non_authoritative`, `decision_power`, `does_not_*`).

## 8) Tests to add/update
- New phase tests for multimodal fusion, degradation posture, privacy/retention preservation, provenance/correlation preservation, deterministic output, and non-authority invariants.
- Architecture boundary tests extended to enforce forbidden imports for fusion surface and verify manifest registration.

## 9) Unresolved risks and deferred work
- Correlation quality still depends on upstream producers including `correlation_id` consistently.
- Contradiction-resolution heuristics remain minimal; current behavior reports partial confidence instead of arbitration.
- Full memory ingress/action gating remains deferred to subsequent phases.
