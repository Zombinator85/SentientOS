# Sequence 986: integrate PR #3065 and verify post-merge main

Sequence 985 was published through PR #3065 as candidate `03717ba3f0e364cc7b7839da589c24e21ac59bed`, tree `3da6f7c618d0bc153b2de578b5a7a956d2c9029f`. All applicable hosted PR workflows passed, including Required Quality Gate, CI, Docker, Codex CI, Lint, Release validation, Invariant Tests, and Gradient regression. PR #3065 merged normally by squash as `b308381cb86e996fe0465d544430247eec73acf4` with the same tree.

All exact-main post-merge workflows passed: CI including source validation, strict documentation linkcheck, self-check and Helm; Required Quality Gate; Codex CI; Docker Image; Docs Deploy; and Invariant Tests. Forge Smoke was skipped by condition. GitHub ref and file readbacks plus authenticated `git ls-remote` resolve main to the merge commit. Source preflight matched this remote main. Full continuation custody verified all 985 predecessor sequences before this append.

The default-five-worker strict linkcheck took about 193 seconds on the PR with four rate-limit waits and about 191 seconds on main with three. The messages came from two existing GitHub URLs; both builds succeeded. Sphinx 8.2.3's retry and Retry-After behavior remained enabled. This paired run reinforces the repeated latency observation without proving worker count is the only cause.

A separate two-worker trial is prepared. It will preserve every URL, the strict `sphinx-build -b linkcheck -W` command, default retry count, Retry-After behavior, and warnings-as-errors. Retain `linkcheck_workers = 2` only if both the exact-candidate and main checks complete within 120 seconds with at most one rate-limit wait each. Otherwise, discard the setting and continue with the default.

This increment changes construction custody evidence only. No CI workflow, documentation configuration, URL coverage, retry policy, or error classification changed.
