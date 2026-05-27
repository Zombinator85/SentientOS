# Household Presence Camera Capture Denial Ledger

This subsystem provides a deterministic, metadata-only ledger for denied/blocked household camera capture authorization attempts.

## Boundaries
- No camera/microphone/hardware access.
- No raw media, base64 media, screenshots, thumbnails, audio/video, or transcripts.
- No speaker output and no external disclosure.

## Relationships
- Consumes outcomes from capture authorization envelope.
- Tracks disabled capture adapter/local shell/policy-chain proof gaps as explicit denial classifications.
- Produces auditable denial records with safe next actions and forbidden next steps.

## Future sequence
1. denial ledger
2. operator review of denial trends
3. grant renewal/dry-run proof repair
4. disabled capture boundary verification
5. future live-candidate review only
