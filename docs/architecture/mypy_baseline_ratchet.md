# Mypy Baseline Ratchet and Typed Surface Gate

This document defines the bounded type-governance layer for repository-wide
mypy debt. It makes the existing broad mypy failure surface explicit without
suppressing errors globally, weakening targeted checks, or changing runtime
authority.

## Baseline artifact

The deterministic baseline artifact is:

```text
vow/mypy_baseline.json
```

The manifest format is JSON with sorted keys and a stable `generated_at`
placeholder. It contains:

- `schema_version`: manifest schema version.
- `generated_at`: stable placeholder for reproducible refreshes.
- `generator`: `scripts.build_mypy_baseline`.
- `mypy_command`: command used to capture the baseline.
- `mypy_version`: best-effort `python -m mypy --version` result.
- `total_error_count`: normalized error count.
- `affected_file_count`: number of files with normalized errors.
- `per_file_counts`: deterministic map of file path to error count.
- `digest`: SHA-256 digest of normalized error records.
- `errors`: sorted records with `path`, `line`, `column`, `code`, and
  normalized `message`.

The default capture command is:

```bash
python -m mypy --hide-error-context --no-color-output --show-column-numbers --show-error-codes scripts/ sentientos/
```

## Refreshing the baseline explicitly

Refresh is an explicit reviewer-visible action:

```bash
python scripts/build_mypy_baseline.py
```

The builder parses current mypy output, rewrites `vow/mypy_baseline.json`, and
prints a compact JSON summary with the new error count, affected file count, and
digest. New files do not silently enter the debt ledger during checking; they
enter only when this refresh command is run and the resulting manifest is
reviewed.

For deterministic parser reviews or tests, the builder can consume captured
output instead of invoking mypy:

```bash
python scripts/build_mypy_baseline.py --mypy-output-file /tmp/mypy-output.txt --output /tmp/mypy_baseline.json
```

## Ratchet check

Run the baseline ratchet check with:

```bash
python scripts/check_mypy_baseline.py
```

The checker validates the manifest digest and compares current normalized mypy
errors with baseline records. It allows matching existing debt, reports retired
errors as improvement, and fails on new errors. The compact reviewer summary
contains:

- `matched_existing_errors`
- `matched_with_location_drift`
- `drifted_files`
- `new_errors`
- `retired_errors`
- `affected_new_files`
- `status`


Matching is keyed by `(path, error code, normalized message)` with multiset counts. Line/column are retained as diagnostics. This keeps the ratchet strict but resilient to harmless line drift: existing debt that moves location remains matched, while additional duplicates, changed messages/codes, or new path/code/message tuples still fail as regressions.
Statuses are deterministic:

- `mypy_baseline_clean`
- `mypy_baseline_matches_existing_debt`
- `mypy_baseline_regression_detected`
- `mypy_baseline_improved`
- `mypy_baseline_missing`
- `mypy_baseline_invalid`

Regression mode exits non-zero only when new errors are present or when the
baseline is missing/invalid. Retired errors remain visible so reviewers can
choose whether to refresh the baseline downward.

## Targeted typed surface gate

The repo-wide baseline is not a substitute for focused typed-surface checks on
new bounded workspace change-set modules and CLIs. Run the targeted gate with:

```bash
python -m mypy --follow-imports=skip --hide-error-context --no-color-output --show-column-numbers --show-error-codes sentientos/workspace_change_set_admission.py scripts/admit_workspace_change_set.py sentientos/workspace_change_set_preflight.py scripts/preflight_workspace_change_set.py sentientos/workspace_change_set_execution.py scripts/run_workspace_change_set_transaction.py sentientos/workspace_change_set_execution_verification.py scripts/verify_workspace_change_set_execution.py sentientos/workspace_change_set_lifecycle_closure.py scripts/build_workspace_change_set_lifecycle_closure.py sentientos/workspace_change_set_lifecycle_orchestrator.py scripts/run_workspace_change_set_lifecycle.py
```

This targeted command stays stricter than the repo-wide baseline posture: it is
intended to remain green for the selected workspace change-set surface even
while older repository-wide debt remains ratcheted.

## Reviewer interpretation

- `mypy_baseline_matches_existing_debt`: current repo-wide debt matches the
  baseline and introduces no new normalized errors.
- `mypy_baseline_improved`: some baseline records disappeared; review may
  refresh the baseline downward.
- `mypy_baseline_regression_detected`: new errors or new files are outside the
  baseline and must be fixed or explicitly baselined through a reviewed refresh.
- `mypy_baseline_missing` / `mypy_baseline_invalid`: the governance artifact is
  absent or corrupted and the check is not authoritative.

This layer is build tooling only. It does not add runtime execution authority,
workspace orchestration, provider invocation, prompt export, network egress, or
host actuation.
