# Sequence 964: integrate PR #3042 and assess strict-linkcheck latency

Sequence 963 was published through PR #3042. Its exact-candidate Required Quality Gate, full CI, Docker, Codex, Invariant, Gradient, Release, and Lint checks passed. The separate push-triggered Invariant Tests workflow passed. PR #3042 merged normally as b5e7c5d3fad88f0bd093997bf0c37dd378178c5d with tree c2386dbeff083cd0d19285ca26f727c7396e590b.

All post-merge CI, Codex CI, Docker, Docs Deploy, Invariant Tests, and Required Quality Gate workflows passed; Forge Smoke was skipped by condition. The merged tree matches the candidate tree, and remote main was verified at b5e7c5d3fad88f0bd093997bf0c37dd378178c5d. Continuation custody verified all 963 predecessor sequences before this append.

The strict external-linkcheck investigation found the one-worker experiment on PR #3043 materially slower: the hosted docs job took about 7m15s and logged six 60-second GitHub 429 backoffs. Prior default five-worker observations took about 2m14s with two backoffs on PR #3042 and three on its main push. PR #3043 passed its gates but was closed unmerged because its performance hypothesis was not supported. The required strict linkcheck command and failure behavior remain unchanged. This comparison is limited to observed runs and does not establish concurrency as the sole cause.

Focused custody, v3 index, and candidate-publication regression tests passed (53 tests) through the repository-supported minimal test-airlock runner. The custody verifier reports all 964 records ready, and `git diff --check` passed.
