# Protected Mutation Baseline Policy

A **legacy covered artifact** is an artifact on a currently covered protected-mutation surface that exists from pre-contract history and lacks the now-required admission linkage.

## Verifier reporting

`python scripts/verify_kernel_admission_provenance.py` now emits machine-readable issue categories:

- `legacy_missing_admission_link`
- `malformed_current_contract`
- `unexpected_collision`
- `missing_expected_side_effect`

Default mode is **baseline-aware**:

- legacy issues are reported but non-blocking
- current-contract regressions still fail the check

`--strict` mode fails on **all** covered-scope issues, including unresolved legacy artifacts.

## Regeneration guidance

Legacy artifacts should be regenerated through the existing protected mutation write paths when operationally safe and scoped to the affected artifact class. Do not backfill synthetic provenance metadata into historical files.

## Developer interpretation

- Baseline-aware failure: treat as active regression in current contract enforcement.
- Baseline-aware success with legacy issues: historical debt is visible, but no new covered-scope breakage detected.
- Strict failure with only legacy issues: unresolved baseline debt remains.
