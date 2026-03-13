# Federated Enforcement Calibration

This pass unifies federation hardening rollout semantics into one explicit posture layer (`shadow`, `advisory`, `enforce`) shared across:

- pulse trust epoch handling
- subject fairness behavior
- federated quorum checks
- governance digest compatibility
- repair outcome verification
- runtime governor mode

## Unified policy source

SentientOS now resolves hardening posture from `sentientos/federated_enforcement_policy.py`.

Resolution order (deterministic):
1. profile baseline via `SENTIENTOS_ENFORCEMENT_PROFILE`
2. optional file overrides via `SENTIENTOS_ENFORCEMENT_POLICY_PATH`
3. per-subsystem env overrides (`SENTIENTOS_ENFORCEMENT_*`)
4. fallback legacy compatibility from `SENTIENTOS_GOVERNOR_MODE`

## Profiles

- `local-dev-relaxed`
  - shadow for pulse/fairness/quorum/digest/repair
  - advisory runtime governor
- `ci-advisory`
  - advisory for all calibrated subsystems
- `federation-enforce`
  - enforce for all calibrated subsystems

## Per-subsystem posture semantics

### Pulse trust epoch
- shadow: classify and ledger decisions, non-blocking for epoch posture
- advisory: same + surfaced warnings through governance/contract channels
- enforce: reject untrusted or mismatched epoch on federated ingress

### Subject fairness
- shadow: telemetry only
- advisory: warnings (`fairness_starvation_warning`) without hard fairness block
- enforce: anti-starvation fairness can block (`deferred_starvation_under_pressure`)

### Federated quorum
- shadow: compute/report quorum decisions (`quorum_warning`), no hard quorum denial
- advisory: warning classification (`quorum_warning`)
- enforce: hard denial (`quorum_failure`) for insufficient quorum where required

### Governance digest
- shadow: classify compatibility only
- advisory: `digest_mismatch_advisory`
- enforce: `digest_mismatch` blocks high-impact federated action classes

### Repair verification
- shadow: emit verification artifacts (`verification_observed` when unverified)
- advisory: warning reason (`verification_warning`)
- enforce: explicit closure requirement (`verification_required_for_closure`)

## Operator/CI bundles

Use:

- `make enforcement-profile-dev`
- `make enforcement-profile-ci`
- `make enforcement-profile-enforce`
- `make enforcement-policy-status`

These produce/reflect `glow/contracts/federated_enforcement_policy.json` and the active resolved posture map.

## Contract/status surfacing

`contract_status.json` now includes:

- top-level `federated_enforcement_policy`
- `federated_enforcement_calibration` contract domain with:
  - active profile
  - policy source
  - posture per calibrated subsystem
  - grouped shadow/advisory/enforce subsystem lists

## Rollout recommendation

Recommended immediate default: `ci-advisory` in CI + `local-dev-relaxed` for local development.

Safe progression:
1. run shadow/advisory and collect contract status + drift output
2. eliminate recurring advisory mismatches (digest/quorum/epoch/repair)
3. move to `federation-enforce` for protected branches and production federation links

