# Sequence 962: integrate PR #3040 and verify post-merge main

Sequence 961 was published through PR #3040, candidate `105296a26a4cd5f11c39a0c87b5328fa9f6d54a2`, with tree `11b6c73696f5d20520bd9d6a3f47ad229606de5f`. Its exact-candidate Required Quality Gate, full CI, Invariant, Gradient, Release, Docker, Codex, and Lint checks passed. The separate push-triggered Invariant Tests workflow passed. PR #3040 merged normally as `07db19bd31a1236fee50d3af6aaea700255a6545` with tree `11b6c73696f5d20520bd9d6a3f47ad229606de5f`.

All post-merge CI, Codex CI, Docker, Docs Deploy, Invariant Tests, and Required Quality Gate workflows passed; Forge Smoke was skipped by condition. The strict Sphinx linkcheck passed on both the PR candidate and main, with two and one GitHub rate-limit backoffs respectively.

The PR run inventory confirms that full CI ran once for the pull request and did not run on the feature-branch push. Main-push CI remains enabled and performed strict post-merge link validation.

Remote `main` readback and tree matched the merge commit. GitHub Git-tree readbacks matched the active checkpoint, constant-size v3 head, latest immutable shard, latest segment, roadmap index, storage consent evidence map, and memory contract. Continuation custody verified all 961 predecessor sequences before this append.
