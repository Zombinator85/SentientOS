# Forge / Report Transaction Digest Contract Semantics

This pass normalizes Forge transaction snapshot contract digest semantics to the
same shared vocabulary already used by selected-surface and observatory
consumers.

## Scope

Updated surface:

- `sentientos.forge_transaction.capture_snapshot()`
  - `TransactionSnapshot.contract_status_digest`

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
