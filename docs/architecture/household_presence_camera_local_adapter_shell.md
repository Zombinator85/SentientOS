# Household Presence Camera Local Adapter Shell

Metadata-only local adapter shell for future camera integration. It does not open hardware, process media, or enable live capture.

## Contract
- Binds live adapter stub readiness, host inventory candidate metadata, zone config, dry-run proof, and policy chain.
- Runtime intent supports `design_only`, `dry_run_only`, `capture_disabled_shell`, and `future_live_candidate`.
- `future_live_candidate` returns operator-review only.
- Successful outputs always keep capture/live hardware/raw media/speaker/external disclosure disabled.
- Forbidden next steps include `open_camera_now`, `enable_live_capture`, `enable_live_recording`, `store_raw_media`, and all bypasses.

## Boundaries
- No camera/microphone access.
- No media payload handling.
- No network/provider/github/runtime execution.

## Sequence
1. Local adapter shell with capture disabled.
2. Operator review.
3. Offline shell fixtures.
4. Future local adapter implementation still capture-disabled by default.
5. Policy-gated live adapter only after explicit future confirmation.
