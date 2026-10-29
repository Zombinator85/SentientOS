# Sequence 985: integrate PR #3064 and verify post-merge main

Sequence 984 was published through PR #3064 as candidate `2b4f5de993f9cf48210a6f21222915c0d4d1324e`, tree `5771f40dc679fe2e0e35a6acfeca966b0a5fa30a`. All applicable hosted PR workflows passed, including Required Quality Gate, CI, Docker, Codex CI, Lint, Release validation, Invariant Tests, and Gradient regression. PR #3064 merged normally by squash as `7e3a52b563ef3f658dcb0dbe704b2e8a3a4758e8` with the same tree.

All exact-main post-merge workflows passed: CI including source validation, strict documentation linkcheck, self-check and Helm; Required Quality Gate; Codex CI; Docker Image; Docs Deploy; Invariant Tests; and Nightly Audit Integrity. Forge Smoke was skipped by condition. GitHub ref and file readbacks plus authenticated `git ls-remote` resolve main to the merge commit. Source preflight matched this remote main. Full continuation custody verified all 984 predecessor sequences before this append.

Two default-five-worker PR linkchecks took about 314 seconds with seven waits and 375 seconds with nine waits. Exact-main checks after those merges took about 14 seconds with no waits and 254 seconds with six waits. The variation is substantial; it does not establish that worker count alone causes the delays. However, both recent PR checks were multi-minute and the latest main check was also multi-minute. A separate two-worker trial is justified to measure whether reduced request concurrency lowers latency.

The trial will preserve every URL, the strict `sphinx-build -b linkcheck -W` command, default retry count, Retry-After behavior, and warnings-as-errors. Retain `linkcheck_workers = 2` only if both the exact-candidate and main checks complete within 120 seconds with at most one rate-limit wait each. Otherwise, discard the setting and continue with the default.

This increment changes construction custody evidence only. No CI workflow, documentation configuration, URL coverage, retry policy, or error classification changed.
