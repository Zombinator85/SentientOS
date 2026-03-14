# Protected Corridor (Release-Quality Validation)

The protected corridor is the bounded validation set expected to remain green together
for release quality. It intentionally focuses on mature constitutional/runtime/federation/operator
surfaces while explicitly classifying debt outside this corridor.

## Corridor command

```bash
PYTHONPATH=. python scripts/protected_corridor.py
```

Artifact output:

- `glow/contracts/protected_corridor_report.json`

## Profiles

- `local-dev-relaxed`: allows expected warnings for local artifact gaps/deferred debt.
- `ci-advisory`: mandatory corridor checks should pass; deferred debt remains visible as non-blocking.
- `federation-enforce`: strict release posture; blocking corridor checks are expected green.

## Included checks

- constitution verify
- forge status + forge replay
- contract status + contract drift
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
- `non_blocking_optional_historical_runtime_state`: non-blocking operational/audit historical issue.
- `legacy_deferred_debt`: known debt outside protected blocking scope.

This separation is deterministic and auditable in the report artifact.
