# Sequence 306 — Repair the nightly audit workflows

PR #2286 has been merged into `main` with a regular merge commit, preserving its three-commit branch history. The merge commit is `c897cc91f046592655506364f197a0b4d2e258ec`, tree `27ddb031801f1815658f90cea6e5fe4dd46543bd`. GitHub comparison against the verified PR head `1e4374bb578a461b99907a131df60e3cba7f348f` reports one merge commit ahead, zero behind, and zero changed files.

The two nightly audit workflows now make their required privilege explicit. The read-only nightly self-check keeps `contents: read` and invokes strict verification with `sudo -n`. The repair workflow keeps only its existing `contents: write` and `pull-requests: write` permissions, runs strict verification as Administrator, plans only through the safe repair planner, applies only the planner's safe repairs, and fails if strict re-verification still finds unresolved issues. It retains run-scoped evidence and opens a PR only after a successful publication step. No auto-repair switch or privilege bypass was introduced.

The exact PR head passed hosted CI, the Required Quality Gate, Docker, Codex CI, invariants, Gradient null regression, lint benchmark, and Release. The privileged QG ran strict audits and the protected immutability finalizer as UID 0; its finalizer returned `ready_for_pr_metadata` with no reasons. The merged main commit then passed CI, Required Quality Gate, Docker, Codex CI, invariants, and Docs Deploy.

The Federation Health updater still has no observable post-merge run in the Actions feed at this checkpoint. The workflow is configured for hourly execution and a manual dispatch, but no scheduled or dispatched run after the workflow fixes was returned. This checkpoint claims no successful execution. Its exact Administrator preflight and docs-only generated change remain the next dependency.

Next dependency: obtain and inspect a successful post-merge Federation Health run, confirm the hosted Administrator preflight and that any generated commit changes only `docs/FEDERATION_HEALTH.md`, then append that execution evidence.
