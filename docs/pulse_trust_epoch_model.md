# Pulse Trust-Epoch Model

This note defines deterministic pulse signing trust continuity during key rotation and compromise response.

## Model

- Every pulse event carries `pulse_epoch_id` and optional `pulse_key_id`.
- Trust state is append-tracked under `PULSE_TRUST_EPOCH_ROOT` with:
  - `epoch_state.json` (current active epoch, revoked epochs, compromise mode, bounded counters)
  - `transitions.jsonl` (epoch transitions)
  - `revocations.jsonl` (explicit revocations)
  - `verification_decisions.jsonl` (verification/trust classification)
  - `runtime_mode.jsonl` (compromise mode changes)

## Verification classes

- `current_trusted_epoch`: signed by active trusted epoch.
- `historical_closed_epoch`: signed by an older closed but still trusted epoch.
- `revoked_epoch`: signature valid but epoch is revoked/untrusted.
- `unknown_epoch`: signature valid but epoch is not in local trust state.
- `invalid_signature`: signature invalid for known key material.

## Runtime policy integration

`RuntimeGovernor` includes pulse epoch posture in deterministic posture composition:

- Compromise mode sets `pulse_epoch_compromise_restricted` for high-impact classes (`federated_control`, `control_plane_task`, `amendment_apply`).
- Explicit untrusted classifications trigger deterministic blocking (`pulse_epoch_untrusted_federation_blocked`, `pulse_epoch_mismatch_escalation_required`).
- Posture rollups include pulse-epoch restrictions in restricted-mode totals.

## Federation behavior

- Federated events are checked against trust epoch classification before peer-key signature acceptance.
- Epoch mismatch or untrusted epoch status prevents ingest and surfaces denial path through governor metadata.

## Constraints preserved

- Pulse history remains append-only (`pulse_YYYY-MM-DD.jsonl`), with no historical rewrite.
- Trust transitions and revocations are explicit append artifacts.
- Deterministic decisioning is preserved via rule-based posture composition and bounded telemetry.
