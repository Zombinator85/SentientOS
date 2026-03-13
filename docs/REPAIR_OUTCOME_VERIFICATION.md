# Repair Outcome Verification

Repair lifecycle:
`detect -> draft -> admit/preflight -> apply -> verify_outcome -> ledger -> success/quarantine/regenesis`

Verification artifacts:
- `glow/repairs/repair_outcome_report_<timestamp>.json`
- `glow/repairs/repair_outcomes.jsonl`

No successful repair status is emitted without explicit verification output.
