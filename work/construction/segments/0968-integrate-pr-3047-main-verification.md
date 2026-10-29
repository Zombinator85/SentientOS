# Sequence 968: integrate PR #3047 main verification and linkcheck data

PR #3047 published sequence 967 candidate `0f7351972b69577dba30ffcee778830fc5a97faf` with tree `9328199c6194c458f7ff25ae1238ab01b607d146`. It merged normally as `7d97121ebe80a7a8302b78beab5a3629e83181d8`; fresh remote main and tree readbacks match. Exact-candidate CI, Codex CI, Docker, Gradient, Invariant, Lint, Release, and Required Quality Gate passed. Post-merge CI, Codex CI, Docker, Docs Deploy, Invariant Tests, and Required Quality Gate passed; Forge Smoke was skipped by condition.

The unchanged strict linkcheck passed on the PR in about 372 seconds with four Sphinx rate-limit backoffs, and on main in about 133 seconds with two. This confirms server-directed waits contribute substantial variable latency. The default worker configuration has ranged from about 69 to 372 seconds in recent runs; the one-worker experiment took about 435 seconds with six backoffs. The workflow already avoids duplicate full-CI PR runs, and Docs Deploy does not repeat linkcheck. Sphinx 8.2.3 has no built-in link-result cache. No safe evidence supports a concurrency, retry, caching, or frequency change; strict checking remains unchanged.

The repository-supported focused custody, v3-index, and candidate-publication tests passed (53 tests). Full continuation custody verifies through sequence 968.
