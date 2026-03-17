# Default Truth Completeness Contract

The default completeness contract defines the minimum node evidence required for WAN truth derivation without optional heavy replay/full-proof steps.

## Required (default) node evidence

A node is considered default-complete when `node_truth_artifacts.json` includes:

- `quorum_state`
- `digest_state`
- `epoch_state`
- `reanchor_state`
- `fairness_state`
- `health_state`

These are reflected in:

- `completeness.required_present`
- `completeness.required_missing`

## Optional evidence

- `replay_state`

Replay remains optional/heavier overall, but default lightweight replay posture is emitted so the oracle can classify replay truth more precisely.

## Oracle impact

With default-complete node artifacts, WAN truth dimensions can more often resolve to:

- `consistent`
- `degraded_but_explained`

instead of `missing_evidence`, especially for:

- quorum
- digest
- epoch
- re-anchor
- fairness
- cluster health
- replay posture (even when full replay is not run)

## Still intentionally optional/heavy

- full replay verification on every node for every run
- deep proofs outside existing forge replay/verification paths
- unbounded retrospective history scans
