# Sequence 304 — Verify hosted landing integration on main

PR #2282 has been merged into `main` with a standard merge commit, preserving its commit chain. GitHub now reports `main` at `505c42ce4f80694e8b99b648eb9bdf1e1ba756b2`. An independent compare against the fully verified PR head `2031cb1421aae9ad35bba67e5aba6c881473ef0d` reports the merge commit one commit ahead, no commits behind, and zero changed files; the merged tree is exactly `8450d45dd76699b76a4102b4fadda14b5a67a4a1`.

For that exact tree, the latest Required Quality Gate run passed 23/23 acceptance nodes. The hosted privileged audit ran as UID 0, source tree `8450d45…`, and reported strict audit and immutability valid. The unchanged PR-metadata finalizer returned `ready_for_pr_metadata`; focused tests, Mypy baseline, prompt boundary, strict audits, and immutability all exited 0. CI, Docker, Invariant Tests, Codex CI, Lint Benchmark, Release, and Gradient null regression all passed on the evidence-complete PR head before merge. The exact hosted artifacts are retained below.

The candidate source and evidence were read back from GitHub after merge, including the complete sequence index in bounded chunks. Construction custody verifies 303 segments. The historical sequence-286 deleted-payload limitation remains recorded and unchanged.

Next dependency: observe the scheduled federation-health update on `main`; verify actual Administrator execution, retained authorization, and health-document-only commit scope. The sandbox cannot dispatch Actions directly, so this is checked through the scheduled hosted workflow.
