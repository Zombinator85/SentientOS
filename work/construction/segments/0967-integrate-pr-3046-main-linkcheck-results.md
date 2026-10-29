# Sequence 967: integrate PR #3046 and complete linkcheck review

PR #3046 published sequence 966 candidate `defc57869e3fc2c8443fe0c954e1678d6f2dab9c` with tree `6a7a1c40573a8d35073727692fb3f58e02617df2`. It merged normally as `78dbd5d5638198a1b987a1156f375d99efaaf476`; fresh remote main and tree readbacks match. Exact-candidate CI, Codex CI, Docker, Gradient, Invariant, Lint, Release, and Required Quality Gate passed. Post-merge CI, Codex CI, Docker, Docs Deploy, Invariant Tests, and Required Quality Gate passed; Forge Smoke was skipped by condition.

The strict Sphinx 8.2.3 linkcheck completed in about 131 seconds on the PR and 69 seconds on main. Its logs show two and one Sphinx rate-limit backoff events respectively; both builds passed. The separate one-worker experiment took about 435 seconds with six backoffs. Existing CI trigger deduplication avoids a second full-CI feature-branch push run; Docs Deploy does not repeat linkcheck. Sphinx 8.2.3's linkcheck builder has no built-in link-result cache. A custom cache would have to skip requests and would weaken external freshness. Measurements do not support safe worker, retry, cache, or frequency changes, so the strict gate remains unchanged.

The repository-supported focused custody, v3-index, and candidate-publication tests passed (53 tests). Full append-only custody verifies through sequence 967.
