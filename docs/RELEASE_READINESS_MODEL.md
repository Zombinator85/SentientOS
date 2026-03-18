# Fleet Release Readiness Model

The Fleet Health Observatory computes deterministic release readiness from existing artifacts.

## Inputs

Readiness explicitly considers:

- protected corridor posture
- simulation baseline gate posture
- formal verification posture
- WAN release gate posture
- remote smoke posture
- constitutional restrictions
- evidence sufficiency posture

## Outcomes

The classifier emits one of:

- `ready`
- `ready_with_degradation`
- `not_ready`
- `indeterminate_due_to_evidence`
- `blocked_by_policy`

## Decision order

1. If constitutional/policy restrictions are active in critical surfaces, classify `blocked_by_policy`.
2. Else if any health dimension is `blocking`, classify `not_ready`.
3. Else if required evidence is missing (`missing_evidence`/`unavailable`), classify `indeterminate_due_to_evidence`.
4. Else if any dimension is degraded/warning/restricted, classify `ready_with_degradation`.
5. Else classify `ready`.

## Notes for operators

- Readiness summarizes posture and does not waive source verification.
- Use `fleet_observatory_manifest.json` to trace all source evidence.
- For blocking policy outcomes, prioritize constitutional/gate source artifacts first.
