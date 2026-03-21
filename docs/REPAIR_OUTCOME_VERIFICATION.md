# Repair Outcome Verification

Repair lifecycle:
`detect -> draft -> admit/preflight -> apply -> verify_outcome -> ledger -> success/quarantine/regenesis`

Repair escalation is damped deterministically:

- per-anomaly attempt counters
- deterministic exponential backoff (`SENTIENTOS_REPAIR_BACKOFF_SECONDS`)
- retry ceiling (`SENTIENTOS_REPAIR_ATTEMPT_CEILING`)
- regenesis threshold (`SENTIENTOS_REPAIR_REGENESIS_THRESHOLD`) before expensive
  fallback churn

Ledger entries include attempt/backoff/threshold metadata and `correlation_id`
for cross-surface incident forensics.

Verification artifacts:
- `glow/repairs/repair_outcome_report_<timestamp>.json`
- `glow/repairs/repair_outcomes.jsonl`

No successful repair status is emitted without explicit verification output.
