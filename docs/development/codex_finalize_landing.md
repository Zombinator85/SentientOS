# Codex Finalize Landing

Use `python scripts/codex_finalize_landing.py finalize` as landing authority.

## Phases
- `--phase pre-commit`: permits intended task files (via `--allow-current-tracked-changes` (or explicit `--changed-file` for tightly controlled tasks)) to be dirty, but still requires validation evidence and blocks unknown/generated drift unless cleanup is allowed and succeeds.
- `--phase post-commit` / `--phase pr-metadata`: requires a clean source tree and only returns PR-metadata readiness when all required validation lanes pass.

## Decisions
- `ready_to_commit`: only valid in `pre-commit` phase.
- `ready_for_pr_metadata`: only valid in `post-commit`/`pr-metadata` phase.
- `repair_required_task_caused`, `manual_review_required`, `environment_blocked`, `do_not_finalize`, `finalizer_failed`.

## Dirty-tree classes
- `intended_task_change`
- `generated_runtime_artifact`
- `versioned_audit_artifact`
- `source_change_not_declared`
- `unknown_dirty_file`
- `clean`

Pre-commit allows `intended_task_change` when declared by `--changed-file` or inferred from tracked git changes with `--allow-current-tracked-changes`. Post-commit/pr-metadata blocks all source dirty files.

## Why PR metadata is forbidden early
Focused tests, matrix, gate, or supervisor alone are insufficient. PR metadata is forbidden until the post-commit/pr-metadata finalizer returns `ready_for_pr_metadata`.

## Example flows
1. Normal feature landing: run pre-commit finalizer (`ready_to_commit`) -> commit -> run post-commit finalizer (`ready_for_pr_metadata`) -> create/update PR metadata.
2. Validation-only sealing with no changes: run post-commit/pr-metadata finalizer directly; expect `ready_for_pr_metadata` with clean tree.
3. Stabilization with generated artifact cleanup only: allow cleanup flags, clean artifacts, then rerun finalizer for phase-appropriate readiness.


## Canonical two-phase command examples
Pre-commit: run finalize with `--phase pre-commit`, `--allow-current-tracked-changes` (or explicit `--changed-file` entries), and require `ready_to_commit` before commit.
Post-commit/pr-metadata: rerun finalize with `--phase pr-metadata` and require `ready_for_pr_metadata` before `make_pr` and final reporting.

## No-change validation-only example
If repository source/doc/test files are unchanged, run the pr-metadata phase for validation evidence only and report completion without commit/`make_pr`.

## Anti-patterns
- Commit + `make_pr` after focused tests only.
- Commit + `make_pr` after partial finalizer usage (pre-commit only).
- Deferring post-commit finalizer to a later seal follow-up turn for task-caused changes.
