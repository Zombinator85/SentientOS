# Codex landing evidence and recovery rail

This rail hardening covers Codex process failures around late PR metadata and finalizer evidence. It is not a memory-chain advancement path and does not authorize Real Executor Invocation Gate implementation, executor invocation, prompt assembly, live-context retrieval, external disclosure, live-memory mutation, lock acquisition, or runtime flag changes.

## Failure pattern: Real Executor Invocation Gate attempts

The recurring failure pattern was procedural rather than an executor implementation success:

1. A Real Executor Invocation Gate attempt appeared to create task-owned implementation files.
2. The task failed late at PR metadata or finalizer evidence, including missing matrix output references or incomplete PR-body evidence.
3. The task was closed without a PR, commit, branch, or patch artifact that preserved those task-owned files.
4. A later recovery prompt ran in a fresh workspace where the uncommitted files were absent.
5. Recovery was impossible, so a fresh rerun consumed substantial credits and repeated landing-risk conditions.

The fix is to make landing evidence durable and repo-native before PR metadata is attempted. Future tasks should generate the PR body from canonical artifacts instead of reconstructing ad hoc text after a late guard failure.

## No-files-found recovery limit

`no-files-found` means recovery cannot find task-owned files, commits, branches, or patches in the current workspace. In a fresh workspace, uncommitted files from a closed Codex task are not present unless the previous task exported a patch, committed a branch, created a PR, or otherwise produced a durable artifact. A recovery prompt can inspect the current checkout, but it cannot reconstruct files that existed only in a previous ephemeral workspace.

When `no-files-found` is reported, the correct conclusion is that recovery of uncommitted implementation is impossible in that workspace. Do not continue as if missing files are hidden implementation contracts. Either locate a durable artifact or perform a new implementation from the current repo state.

## Canonical PR metadata evidence

PR metadata evidence must be generated from canonical artifacts because the landing gate and PR metadata guard validate concrete evidence, not intent. The durable inputs are:

- the matrix JSON written by `scripts/run_work_item_review_packet_matrix.py --output`;
- the landing supervisor JSON, when already available;
- explicit result text for targeted mypy, baseline, docs build, prompt-boundary checks, strict audit, immutability verifier, finalizer, PR metadata guard, landing gate, and unresolved risks.

Use `scripts/build_codex_landing_evidence_body.py` to produce the PR body. The script writes the required sections, preserves guard-required marker text, and fails if the matrix JSON is missing, the matrix output path marker is absent, the unresolved risks section is absent, or the body is evidence-light.

## Fresh matrix output path

The matrix output path must remain explicit because `matrix_output_reference_missing` is a late PR metadata failure class. A body that claims validation passed but does not name the `--output` artifact is not recoverable enough for reviewers or guard tooling.

The matrix path must also be fresh. The finalizer's `stale_evidence_matrix_output` behavior is correct: if cleanup or later validation changes can make earlier matrix evidence stale, the fix is to refresh matrix evidence and rerun landing gate/supervisor/finalizer in the same task. The finalizer does not need to delete `/tmp` matrix output to cause staleness; stale evidence can arise when the evidence no longer reflects the final source tree or post-cleanup state.

## Same-task recovery for late landing failures

For late PR metadata, landing gate, supervisor, or finalizer failures:

1. Keep the task open in the same workspace.
2. Preserve task-owned files and generated evidence paths.
3. Repair only the missing evidence or stale-evidence blocker.
4. Regenerate the PR body with `scripts/build_codex_landing_evidence_body.py`.
5. Rerun the landing gate with the generated body.
6. Rerun the landing supervisor with the fresh matrix JSON.
7. Rerun the two-phase finalizer sequence as required.
8. Run the PR metadata guard and call `make_pr` only after `pr_metadata_guard_ready`.

Do not close the task until a PR exists, a commit/branch/patch artifact exists, or `no-files-found` has been reported and recovery is impossible.

## Distinguishing failure classes

- **Implementation failure**: source, docs, fixtures, or tests are missing or failing. Repair task-owned implementation and rerun focused validation before the landing sequence.
- **PR metadata failure**: implementation exists, but PR title/body/evidence markers are incomplete. Regenerate the body from canonical artifacts and rerun landing gate/guard.
- **Finalizer stale-evidence failure**: validation evidence no longer reflects the final tree, often after cleanup or audit repair. Refresh matrix output, landing gate, and supervisor evidence in the same task, then rerun the finalizer.
- **Dependency setup noise**: Python or package setup warnings, such as environment bootstrap chatter, are not implementation evidence. Classify them as environment noise unless they cause a required command to fail.
- **Workspace state loss**: a fresh workspace lacks uncommitted files from a closed task. If no commit, branch, PR, or patch artifact exists, report `no-files-found`; do not claim recovery is possible.

## Using the generated PR body script

Example:

```bash
python scripts/build_codex_landing_evidence_body.py \
  --title "[codex:landing] harden evidence and recovery rail" \
  --intended-commit-title "[codex:landing] harden evidence and recovery rail" \
  --matrix-json-path /tmp/codex_landing_evidence_recovery_rail_matrix.json \
  --landing-supervisor-json-path /tmp/codex_landing_evidence_recovery_rail_supervisor.json \
  --output /tmp/codex_landing_evidence_recovery_rail_pr_body.txt \
  --targeted-mypy "passed" \
  --baseline "passed" \
  --docs-build "passed" \
  --prompt-boundary "passed" \
  --strict-audit "passed" \
  --immutability-verifier "passed" \
  --finalizer "pre-commit ready_to_commit; post-commit pending" \
  --pr-metadata-guard "pending" \
  --unresolved-risks "None known."
```

The output body includes `Matrix output path: <path>` and `Unresolved risks: <text>`, plus the marker text required by the PR metadata contract. If the landing supervisor JSON is not yet written, the script records the requested path as pending so the body can be used for the landing gate before supervisor evaluation.
