# WAN Contradiction Tightening and Profiles

This document explains tightened contradiction handling once evidence density is richer.

## Profiles

- `default`
  - `max_missing_nonblocking=5`
  - `max_warning_before_block=2`
- `evidence_strict`
  - `max_missing_nonblocking=2`
  - `max_warning_before_block=1`

## Tightening behavior

Policy remains deterministic and auditable.

Additional behavior when evidence completeness is high:

- If a run is `default_complete` and still has `missing_evidence_nonblocking`, outcome ratchets to `warning`.
- If a run is `fully_evidenced` and has warning contradictions, outcome ratchets to `blocking_failure`.
- In `evidence_strict`, `fully_evidenced` runs with any missing-evidence contradictions are escalated to `warning`.

This sharpens the distinction between:

- evidence-poor warning/degradation
- evidence-rich contradiction failures

## Operator interpretation

- **Evidence-poor degradation**: improve evidence capture (see completeness artifacts) before treating as hard contradiction.
- **Evidence-rich contradiction**: treat as real policy contradiction and remediate runtime/trust posture.

## Where to inspect

- Scenario policy: `wan_truth/contradiction_policy_report.json`
- Scenario completeness: `wan_truth/scenario_evidence_completeness.json`
- Gate completeness aggregate: `wan_gate/scenario_evidence_completeness.json`
- Gate density summary: `wan_gate/evidence_density_report.json`
