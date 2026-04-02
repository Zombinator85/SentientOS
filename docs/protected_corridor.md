# Protected Corridor (Release-Quality Validation)

The protected corridor is the bounded validation set expected to remain green together
for release quality. It intentionally focuses on mature constitutional/runtime/federation/operator
surfaces while explicitly classifying debt outside this corridor.

## Canonical commands

Provision once (deterministic editable install + test extras):

```bash
python scripts/protected_corridor.py --bootstrap
```

Verify corridor prerequisites only:

```bash
python scripts/protected_corridor.py --check-prereqs
```

Run the corridor:

```bash
PYTHONPATH=. python scripts/protected_corridor.py --profile ci-advisory
```

Artifact output:

- `glow/contracts/protected_corridor_report.json`
- `glow/contracts/baseline_verification_status.json` (consumes corridor global summary)

## Prerequisites

Blocking targeted test surfaces require:

- editable install from this repository root
- runtime test imports: `pytest`, `fastapi`, `starlette.testclient.TestClient`, `httpx`

The report includes a deterministic provisioning section:

- `provisioning.ready`
- `provisioning.check_missing_prerequisites`
- `provisioning.diagnostics`

If prerequisites are missing, profiles are not executed and the command exits with code `2`.

## Profiles

- `local-dev-relaxed`: allows expected warnings for local artifact gaps/deferred debt.
- `ci-advisory`: mandatory corridor checks should pass; deferred debt remains visible as non-blocking.
- `federation-enforce`: strict release posture; blocking corridor checks are expected green.

## Included checks

- constitution verify
- forge status + forge replay
- contract status + contract drift
- targeted contract status rollup tests
- simulation baseline gate
- formal verification
- targeted federation hardening tests
- targeted operator CLI tests
- mypy protected-scope ratchet surface
- audit immutability verifier
- strict audit verification tooling

## Classification model

- `blocking_release_corridor_failure`: release corridor blocker.
- `blocking_correctness_failure`: correctness blocker.
- `environment_unprovisioned`: bootstrap/runtime dependencies were missing.
- `policy_doctrine_skipped`: execution was blocked by explicit doctrine/policy mode.
- `non_blocking_optional_historical_runtime_state`: non-blocking operational/audit historical issue.
- `legacy_deferred_debt`: known debt outside protected blocking scope.

This separation is deterministic and auditable in the report artifact.

## Report semantics (machine + operator visibility)

The corridor report includes:

- `corridor_version`: deterministic release-corridor definition version.
- `protected_corridor.failure_taxonomy`: explicit bucket vocabulary for failures/warnings.
- `profiles[*].summary`: per-profile pass/blocking/advisory/debt counts.
- `profiles[*].deferred_debt`: known non-blocking debt items per profile.
- `corridor_relevance`: explicit touched-surface relevance for currently covered protected-mutation domains.
- `covered_protected_mutation_corridor`: machine-readable definition of the currently covered protected-mutation corridor.
- `global_summary`: cross-profile status with:
  - `status` (`green` / `amber` / `red`)
  - `blocking_profiles`
  - `advisory_profiles`
  - `debt_profiles`
  - `deferred_debt_outside_corridor`

`scripts/emit_baseline_verification_status.py` now consumes this schema directly so operator rollups
can distinguish protected-corridor blockers from advisory/deferred repo-wide debt.
