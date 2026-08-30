# Codex validation matrix lane contract

Metadata-only canonical lane registry and verifier used by Codex landing evidence checks.

## CLI

- `python -m scripts.codex_validation_matrix_lane_contract list`
- `python -m scripts.codex_validation_matrix_lane_contract verify --matrix-json-path <path>`
- `python -m scripts.codex_validation_matrix_lane_contract summary --matrix-json-path <path>`

## Contract behavior

- Required lanes must exist (alias accepted) and pass.
- Docs recovery is valid only when `docs_bootstrap`, `docs_check_deps_recheck`, and `docs_build` pass after a failed `docs_check_deps`.
- `required_failure_count` must match computed required lane failures.
- Unknown lanes are deterministic warnings by default.

## Liveness and resume custody

Every CLI invocation uses the bounded, checkpointing runner, including the common
`--output ... --summary --progress` form.  The previous routing selected the legacy
unbounded runner unless `--checkpoint` was also supplied; consequently
`--command-timeout-seconds` and `--progress` were silently ineffective and an active
`codex_landing_commit_body_binding_tests` child could remain dormant without a partial
artifact.  The lane command itself completes when run independently and does not invoke
the finalizer recursively; the demonstrated liveness defect was the CLI runner-selection
boundary, not finalizer re-entrancy.

Before each child starts, the checkpoint names its label, argv, lifecycle state, lane
index, and bounded deadline.  Each child owns a process session.  Deadline expiry or a
controlled interruption terminates and reaps that session's process tree, retains
available output tails and an explicit termination reason, and atomically records a
non-complete `matrix_timed_out` or `matrix_interrupted` artifact.  A timed-out required
lane remains a required failure.  A timed-out diagnostic lane remains non-proof evidence
and cannot make the matrix successful.  Resume accepts only an intact checkpoint bound
to the same workspace and matrix contract; completed-matrix validation continues to
require `matrix_passed`.
