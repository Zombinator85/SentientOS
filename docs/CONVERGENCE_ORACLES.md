# Convergence Oracle Classes

The endurance wing emits explicit convergence classes from live daemon runs.

## Inputs

Oracle classification uses:

- runtime boot behavior
- quorum recovery behavior
- re-anchor continuation behavior
- epoch compatibility behavior
- fairness stabilization behavior
- corridor interpretability behavior

## Outcome classes

- `converged_expected`: all checks met.
- `converged_with_degradation`: run converged but one or more non-critical checks degraded.
- `failed_to_converge`: critical recovery checks failed.
- `blocked_by_policy`: expected policy block occurred (for policy-block scenarios).
- `indeterminate_due_to_lab_limitations`: insufficient interpretability or missing runtime evidence.

## Artifact interpretation

Key endurance artifacts:

- `staged_timeline_report.json`
- `scenario_injection_log.jsonl`
- `node_health_timeseries.json` (when sampled)
- `node_signal_timeseries.json`
- `convergence_summary.json`
- `final_cluster_state_digest.json`
- `artifact_manifest.json`

Use these to answer:

- what happened and when
- which nodes were impacted
- whether recovery occurred
- what remained degraded, blocked, or indeterminate
