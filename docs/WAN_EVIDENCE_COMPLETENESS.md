# WAN Evidence Completeness Contract

This contract defines deterministic evidence expectations for canonical WAN scenarios.

## Default required dimensions

Default required evidence dimensions:

- `quorum_truth`
- `digest_truth`
- `epoch_truth`
- `reanchor_truth`
- `fairness_truth`
- `cluster_health_truth`

## Optional/heavy dimension

- `replay_truth` (heavy/full replay optional, but lightweight posture is emitted by default)

## Scenario-required dimensions for fully-evidenced classification

- `wan_partition_recovery`
  - `quorum_truth`, `digest_truth`, `epoch_truth`, `fairness_truth`, `cluster_health_truth`
- `wan_asymmetric_loss`
  - `quorum_truth`, `digest_truth`, `epoch_truth`, `fairness_truth`, `cluster_health_truth`
- `wan_epoch_rotation_under_partition`
  - `quorum_truth`, `digest_truth`, `epoch_truth`, `fairness_truth`, `cluster_health_truth`
- `wan_reanchor_truth_reconciliation`
  - `quorum_truth`, `digest_truth`, `epoch_truth`, `reanchor_truth`, `fairness_truth`, `cluster_health_truth`

## Deterministic completeness states

Per-scenario completeness reports include:

- `default_complete`: no required dimensions are `missing_evidence`
- `fully_evidenced`: `default_complete` AND no required dimensions are degraded AND provenance is reconciled (`status=consistent` and `digest_match=true`)

## Artifacts

Per run (`glow/lab/wan/<run_id>/wan_truth/`):

- `scenario_evidence_completeness.json`
- `evidence_density_report.json`

Per gate (`glow/lab/wan_gate/`):

- `scenario_evidence_completeness.json`
- `evidence_density_report.json`

These are deterministic, auditable summaries used by the WAN contradiction policy/gate.
