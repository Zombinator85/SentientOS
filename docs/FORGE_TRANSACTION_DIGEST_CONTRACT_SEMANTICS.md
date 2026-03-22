# Forge / Report Transaction Digest Contract Semantics

This pass normalizes Forge transaction snapshot contract digest semantics to the
same shared vocabulary already used by selected-surface and observatory
consumers.

## Scope

Updated surfaces:

- `sentientos.forge_transaction.capture_snapshot()`
  - `TransactionSnapshot.contract_status_digest`
- `sentientos.cathedral_forge.ForgeReport`
  - `preflight.contract_status_digest`
  - `contract_status_digest_preflight`
  - `transaction_snapshot_before.contract_status_digest`
  - `transaction_snapshot_after.contract_status_digest`
- `pulse/forge_receipts.jsonl` (`ForgeReceipt`)
  - `contract_alert_badge`
  - `contract_alert_reason`
  - `contract_alert_counts`
  - `contract_row_summary_counts`
  - compatibility mirrors: `has_drift`, `drift_domains`

This pass is intentionally bounded. It **does not** redesign:

- contract status source emitters
- latest-pointer architecture
- forge transaction enforcement/gating doctrine
- protected-corridor blocking policy

## Added digest fields

`contract_status_digest` now carries optional bounded contract alert fields:

- `contract_alert_badge`
- `contract_alert_reason`
- `contract_alert_counts`
- `contract_row_summary_counts` (compact counters only)

The digest still preserves compatibility booleans:

- `has_drift`
- `drift_domains`

## Report / receipt propagation

Forge report and receipt readers now have a compact single-hop contract digest
path without dereferencing full `contract_status.json` rows:

- `preflight.contract_status_digest` gives bounded semantics at preflight emit
  time.
- `transaction_snapshot_before/after.contract_status_digest` preserve before vs
  after semantics for transactional comparisons.
- Forge daemon receipts copy the **after** digest semantics into receipt rows so
  queue/ops/observability consumers can read badge/reason/counts directly.

This remains intentionally compact and does not inline full contract rows.

## Semantic mapping

The digest uses shared consumer normalization (`contract_status_consumer`) so
it matches existing fleet/ops vocabulary:

- freshness/completeness pressure → `freshness_issue`
- posture drift → `domain_drift`
- baseline absence/precondition gaps → `baseline_absent`
- indeterminate/missing evidence → `partial_evidence`
- nominal rows → `informational`

Badge/reason precedence remains shared and deterministic (for example:
`domain_drift` outranks `baseline_absent`, which outranks `freshness_issue`).

## Freshness vs posture separation

The digest preserves explicit separation:

- stale pointer with healthy row posture remains `freshness_issue`
- current pointer with drifted row posture remains `domain_drift`
- baseline missing remains `baseline_absent`

No generic flattening into a single drift boolean is introduced.

## Out of scope

- inlining full `contract_status.json` rows into transaction digests
- changing transaction regression policy (`contract_drift_appeared` still uses
  compatibility `has_drift`)
- introducing new blocker classes from digest metadata
- changing protected-corridor or forge gating doctrine
