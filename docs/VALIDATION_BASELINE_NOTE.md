# Validation Baseline Note: Federation Simulation Release Gate

This change converts the deterministic federation simulation wing into a canonical release-gate baseline.

## What was baselined

- canonical scenario suite (5 scenarios)
- deterministic seed policy and stable manifest
- release-gating classification per scenario
- deterministic baseline summary artifact
- gate-compatible exit code behavior for CI/release surfaces

## Run command

```bash
python -m sentientos.ops simulate federation --baseline --json
```

## Blocking semantics

Release is blocked when any release-gating scenario fails baseline checks.

## Remaining blind spots

- No long-run temporal drift scenario beyond bounded replay storm windows.
- No explicit mixed-version protocol drift scenario in the baseline suite.
- No resource-exhaustion envelope (CPU/IO budget pressure) in deterministic baseline checks.
