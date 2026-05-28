# Household Presence Camera Capture Review Packet

This module builds a deterministic **metadata-only** operator-review packet for household camera capture prerequisites. It never opens camera hardware, never processes media, and never upgrades review artifacts into capture authority.

It aggregates proof alignment from authorization envelope, denial ledger, disabled capture adapter, local shell/stub, host candidate, zone config, dry-run, readiness, and policy chain into a single review artifact.

## Boundaries
- Not live hardware access.
- No media payload ingestion/storage.
- No speaker output or external disclosure authority.
- Future-live requests remain operator-review only.

## Relationships
- Authorization envelope: required proof digest.
- Denial ledger: unresolved denials and denial history checks.
- Disabled capture adapter + local shell + policy chain: safety boundary proofs.

## Forbidden next steps
`open_camera_now`, `attempt_capture`, `enable_live_capture`, `enable_live_recording`, `store_raw_media`, `attach_media_payload`, `bypass_authorization_envelope`, `bypass_denial_ledger`, `bypass_policy_chain`, `bypass_zone_config`, `bypass_disabled_capture_boundary`, `bypass_dry_run`, `enable_speaker_output`, `enable_external_disclosure`.

## Future sequence
1. Build capture review packet.
2. Operator reviews alignment and denial history.
3. Grant renewal or dry-run proof repair.
4. Verify disabled-capture boundary.
5. Future live-candidate review only.
6. Separate task for policy-gated live adapter confirmation.
