# Sequence 984: integrate PR #3063 and verify post-merge main

Sequence 983 was published through PR #3063 as candidate `26935171cb5fae6743b901f7f3781febb2f088ee`, tree `bd1ffe158cfed58a7f61429952a7dd1532f61b77`. All applicable hosted PR workflows passed, including Required Quality Gate, CI, Docker, Codex CI, Lint, Release validation, Invariant Tests, and Gradient regression. PR #3063 merged normally by squash as `0bce3a6dccec38e0012b63ef790f9d6067baedc9` with the same tree.

All exact-main post-merge workflows passed: CI including source validation, strict documentation linkcheck, self-check and Helm; Required Quality Gate; Codex CI; Docker Image; Docs Deploy; and Invariant Tests. Forge Smoke was skipped by condition. GitHub ref and file readbacks plus authenticated `git ls-remote` resolve main to the merge commit. Source preflight matched this remote main. Full continuation custody verified all 983 predecessor sequences before this append.

The strict Sphinx 8.2.3 linkcheck passed with its default five workers on both PR and main. The PR run took about 314 seconds and logged seven rate-limit waits across four existing GitHub URLs; the main run took about 14 seconds with no waits. This large difference shows substantial run-to-run variance, so it does not establish that worker concurrency causes the delay. A bounded two-worker hosted experiment remains appropriate only as a measurement; keep the setting only if exact-candidate and main runs pass with materially lower delay and no loss of URL coverage, default retries, Retry-After handling, or strict failure semantics.

This increment changes construction custody evidence only. No CI workflow, documentation configuration, URL coverage, retry policy, or error classification changed.
