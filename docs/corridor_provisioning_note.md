# Corridor Provisioning Note

Protected corridor execution depends on a test-capable editable install and targeted runtime imports.

## Canonical operator flow

1. Bootstrap deterministic dependencies:
   - `python scripts/protected_corridor.py --bootstrap`
2. Validate environment readiness:
   - `python scripts/protected_corridor.py --check-prereqs`
3. Execute release corridor:
   - `PYTHONPATH=. python scripts/protected_corridor.py --profile ci-advisory`

## Failure interpretation

- `blocking_release_corridor_failure` / `blocking_correctness_failure`: real corridor regression.
- `environment_unprovisioned`: provisioning/bootstrap gap (not a product regression).
- `policy_doctrine_skipped`: execution blocked by explicit doctrine/policy mode.

The authoritative artifact is `glow/contracts/protected_corridor_report.json`, including the
`provisioning` block for deterministic diagnostics.
