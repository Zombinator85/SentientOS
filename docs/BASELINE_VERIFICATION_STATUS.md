# Baseline Verification Status

This document describes the **broad baseline** signal model and how it differs from protected corridor signals.

## Lanes

- **Protected corridor lane**: governed by `glow/contracts/protected_corridor_report.json` and should remain the strongest release gate signal.
- **Broad baseline lane**: combines repository-wide runtime and typing health:
  - `python -m scripts.run_tests -q`
  - `mypy scripts/ sentientos/`

## Machine-readable status artifact

Use:

```bash
python scripts/emit_baseline_verification_status.py
```

This writes `glow/contracts/baseline_verification_status.json` with:

- `protected_corridor_green`
- `broad_baseline_green`
- lane-level statuses (`protected_corridor`, `run_tests`, `mypy`)
- deterministic failure class totals (from `glow/test_runs/test_failure_digest.json`)
- explicit blocking vs deferred failure classes

## Failure classes

Current deterministic classes from `scripts/analyze_test_failures.py`:

- `pulse_federation_persistence`
- `pulse_persistence_signature`
- `covenant_tripwire_drift`
- `bootstrap_import_instability`
- `unclassified_runtime_failure`

## Stabilized expectation

A baseline is considered **stabilized** when:

1. protected corridor remains green,
2. broad baseline either becomes green or has bounded/non-ambiguous failure classes,
3. remaining debt is explicitly tagged as deferred and does not pollute corridor/protected gating.
