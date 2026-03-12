# State Machine Properties

This file enumerates the first-wave formal properties and their model IDs.

## runtime_governor

Model: `formal/models/runtime_governor.json`

Checked properties:

- `rg_local_safety_not_starved`
- `rg_restricted_blocks_required_classes`
- `rg_bounded_counters`
- `rg_deterministic_precedence`

## audit_reanchor

Model: `formal/models/audit_reanchor.json`

Checked properties:

- `audit_no_silent_rewrite`
- `audit_continuation_requires_anchor`
- `audit_break_visibility_persists`
- `audit_reanchor_coexists_with_preserved_break`

## federated_governance

Model: `formal/models/federated_governance.json`

Checked properties:

- `fed_high_impact_requires_quorum`
- `fed_digest_mismatch_blocks_required`
- `fed_local_posture_dominates_quorum`
- `fed_incompatible_peers_cannot_satisfy_quorum`

## pulse_trust_epoch

Model: `formal/models/pulse_trust_epoch.json`

Checked properties:

- `pulse_revoked_never_current_trusted`
- `pulse_compromise_mode_tightens`
- `pulse_historical_distinct_from_revoked_unknown`

## Determinism controls

- Bounded Cartesian exploration only.
- Stable JSON serialization + SHA256 run digest.
- Stable file manifest hashing for checked spec/model inputs.
