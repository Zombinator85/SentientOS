# Household Presence Camera Live Adapter Stub

This capability is a deterministic metadata-only contract for future camera live adapter work. It does **not** open camera hardware, inspect media devices, process image/audio/video, or permit runtime actuation.

## Purpose
- Enforce hardware-disabled-by-default boundary.
- Require explicit operator confirmation with stub-only constraints.
- Require host inventory candidate binding, zone config binding, policy-chain routing, and dry-run proof before any future live-mode design review.

## Relationships
- Host inventory bridge provides candidate metadata and recommendation gating.
- Live adapter readiness contributes readiness status checks.
- Dry-run adapter provides proof digest + status.
- Policy chain and zone config remain mandatory bindings.

## Confirmation and Binding Requirements
- Confirmation must keep `stub_only=true`, `live_hardware_allowed=false`, `raw_media_allowed=false`, `speaker_output_allowed=false`, `external_disclosure_allowed=false`.
- Binding must include candidate id, source metadata, zone config id, policy chain id/requirement, dry-run digest/status, readiness status, recommendation, and review metadata.

## Forbidden Next Steps
- `open_camera_now`
- `enable_live_recording`
- `store_raw_media`
- `bypass_policy_chain`
- `bypass_zone_config`
- `bypass_dry_run`
- `enable_speaker_output`
- `enable_external_disclosure`

## Future Sequence
1. Live adapter stub with hardware disabled.
2. Operator review.
3. Zone binding.
4. Dry-run proof.
5. Local adapter implementation with capture disabled by default.
6. Policy-gated live adapter only after explicit future confirmation.
