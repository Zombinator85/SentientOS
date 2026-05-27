# Household Presence Camera Capture Authorization Envelope

Metadata-only authorization envelope for **future review** of household camera capture attempts. It never opens hardware, captures media, or executes live adapters.

## Purpose
Provides deterministic records for operator grant, scope/expiry/revocation checks, and proof bindings (disabled-capture adapter, local shell, live-adapter stub, host candidate, zone config, dry-run, policy chain).

## Boundaries
- No camera/microphone/hardware access.
- No media payload handling.
- No subprocess or provider/network authority.
- Always returns `capture_enabled=false` and related disabled flags.

## Flow
1. authorization envelope
2. operator review
3. dry-run proof renewal
4. disabled-capture boundary verification
5. future live-candidate review only
6. policy-gated live adapter only after explicit future separate task
