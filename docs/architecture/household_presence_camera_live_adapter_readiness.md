# Household Presence Camera Live Adapter Readiness

Metadata-only readiness checker for future live adapter wrapping.

- Inspects repository paths only; no hardware, media, or runtime execution.
- Verifies prerequisite surfaces: sensor inventory, event bridge, redaction, zone config/resolver, policy chain, and matrix/gate/supervisor tooling.
- Emits deterministic status/digest and conservative allowed/forbidden next steps.

## Ready for stub only
`ready_for_stub_only` / `ready_for_operator_review` means interface/design work may proceed, but live camera/speaker/external authority remains forbidden.

## Future sequence
1. Design metadata-only adapter interface.
2. Add offline adapter fixtures.
3. Add operator-confirmed dry-run.
4. Add host inventory bridge.
5. Add local policy-gated live adapter only after explicit operator confirmation.
6. Keep speaker/talkback separate.
7. Keep external authority blocked.
