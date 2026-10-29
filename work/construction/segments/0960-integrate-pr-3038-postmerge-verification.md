# Sequence 960: integrate PR #3038 and verify post-merge main

Sequence 959 was published through PR #3037, candidate `7902b5ae9ce16624854bf03895a241ad875450e1`, and merged as `3353d7762166e1c2e6669f0c128f647e7b59a80f` with tree `6e406559f63dbda3770700faa67694f83ca39655`. Its exact candidate checks and all post-merge checks passed; Forge Smoke was skipped by condition.

PR #3038 addresses the observed duplicate full-CI trigger: the same feature-branch SHA had run CI for both push and pull_request, duplicating Sphinx linkcheck requests and GitHub 429 backoffs. The change restricts full CI push runs to main while retaining pull-request CI and main post-merge CI. On the corrected exact candidate, strict linkcheck passed with one rate-limit backoff. The post-merge main CI also passed the unchanged strict linkcheck after six backoffs.

The first PR #3038 Quality Gate run began before the PR title update matched the commit subject. Its exact-call acceptance passed, but the landing finalizer rejected the stale title. The subsequent exact-candidate run passed Required Quality Gate, and all other candidate checks passed. PR #3038 merged normally as `bbd4651288ab501849c282174e143269cf562277` with tree `c451dc9cb21e84224a795929866c1d4321ec8f19`. Required post-merge CI, Codex CI, Docker, Docs Deploy, Invariant Tests, Nightly Self Check, and Quality Gate passed; Forge Smoke was skipped by condition.

Remote `main` readback and its tree matched the merge commit. GitHub Git-tree readbacks matched the checkpoint, constant-size v3 head, latest immutable shard, latest segment, roadmap index, storage consent evidence map, and memory contract. Continuation custody verified all 959 predecessor sequences before this append.
