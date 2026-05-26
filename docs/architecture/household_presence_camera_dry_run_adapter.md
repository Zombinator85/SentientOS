# Household Presence Camera Dry-Run Adapter

This contract provides a deterministic metadata-only rehearsal layer for future live camera adapter sessions.

## Boundaries
- Offline JSON fixture/session input only.
- Requires explicit operator confirmation metadata (`dry_run_only=true`, `live_hardware_allowed=false`, `speaker_output_allowed=false`, `external_disclosure_allowed=false`, `raw_media_allowed=false`, `policy_chain_required=true`).
- Routes every event through `household_presence_camera_policy_chain`.
- Blocks media payloads/base64/raw transcript content.
- Blocks speaker/talkback runtime requests and external-authority disclosure requests.
- No camera opening, no microphone access, no hardware discovery, no live runtime module execution.

## Relationship to existing layers
- Uses policy-chain outcomes as authoritative route decisions.
- Complements `household_presence_camera_live_adapter_readiness` by proving offline-only rehearsal readiness.

## Session report model
- Per-event stages and route output.
- Route counts, blocked reason counts, operator review counts.
- Deterministic digest for reproducible operator review artifacts.

## Future sequence
1. Dry-run adapter contract.
2. Offline adapter fixtures.
3. Operator-confirmed dry-run reports.
4. Host inventory bridge.
5. Local live adapter stub with hardware disabled by default.
6. Policy-gated live adapter only after explicit operator confirmation.
