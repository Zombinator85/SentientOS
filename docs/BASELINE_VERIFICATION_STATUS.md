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
- deterministic lane-state taxonomy for incomplete/non-provisioned inputs

## Broad-lane completeness semantics

Each lane now includes a `lane_state` that distinguishes artifact and completeness posture:

- `lane_not_run`: lane artifacts are absent for this cycle (for example, no
  `glow/test_runs/test_run_provenance.json` and no digest).
- `lane_unavailable_in_environment`: lane could not execute due to
  environment/bootstrap preconditions (for example run_tests airlock/install failures).
- `lane_incomplete`: lane started but artifact payloads are unreadable or partial.
- `lane_completed_with_advisories`: lane completed without blocking findings.
- `lane_completed_with_deferred_debt`: lane completed and only deferred debt remains.
- `lane_completed_with_blocking_failure`: lane completed and found blocking failures.

## Expected broad-lane artifacts

- `run_tests` lane:
  - primary provenance: `glow/test_runs/test_run_provenance.json`
  - failure digest (when failures are grouped): `glow/test_runs/test_failure_digest.json`
- `mypy` lane:
  - primary ratchet status: `glow/contracts/typing_ratchet_status.json`
  - fallback text summary (legacy): `glow/typecheck/mypy_latest.txt`

This keeps protected corridor blocking doctrine unchanged while reducing amber
noise caused by missing broad-lane artifacts versus true deferred debt.

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

## Broad-lane latest pointers

To remove cross-file inference, broad-lane recency is emitted at:

- `glow/observatory/broad_lane/run_tests_latest_pointer.json`
- `glow/observatory/broad_lane/mypy_latest_pointer.json`
- `glow/observatory/broad_lane/broad_lane_latest_summary.json`

`emit_baseline_verification_status.py` now consumes this summary first (when present) and falls back to direct lane artifacts if pointer artifacts are absent.
